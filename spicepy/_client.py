from collections.abc import Iterator
import json
import os
from pathlib import Path
import platform
import threading
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote
import uuid

import certifi
import pyarrow as pa

if TYPE_CHECKING:
    import pandas as pd
    import polars as pl

    from ._dataframe import SpiceDataFrame

# pylint: disable=E0611
from pyarrow._flight import (
    FlightCallOptions,
    FlightClient,
    Ticket,
)

from . import config
from ._active_query import ActiveQuery
from ._http import HttpRequests, RefreshOpts
from ._status import ConnectionDetails
from .error import SpiceAIError
from .params import infer_arrow_type


def is_macos_arm64() -> bool:
    return (
        platform.platform().lower().startswith("macos")
        and platform.machine() == "arm64"
    )


try:
    from pyarrow import flight
except (ImportError, ModuleNotFoundError) as error:
    if is_macos_arm64():
        raise ImportError(
            "Failed to import pyarrow. Detected Apple M1 system."
            " Installation of pyarrow on Apple M1 systems requires additional steps."
            " See https://docs.spice.ai/sdks/python-sdk#m1-macs."
        ) from error
    raise error from error

try:
    import adbc_driver_flightsql.dbapi
    import adbc_driver_manager

    ADBC_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    adbc_driver_flightsql = None  # type: ignore
    adbc_driver_manager = None  # type: ignore
    ADBC_AVAILABLE = False

DEFAULT_QUERY_TIMEOUT_SECS = 10 * 60


class _ADBCClient:
    """ADBC client for parameterized queries using FlightSQL."""

    def __init__(
        self,
        uri: str,
        api_key: str | None = None,
        user_agent: str | None = None,
    ):
        if not ADBC_AVAILABLE:
            raise ImportError(
                "ADBC driver is not available. Install it with: pip install adbc-driver-flightsql adbc-driver-manager"
            )

        self._uri = uri
        self._api_key = api_key
        self._user_agent = user_agent
        self._db: Any = None
        self._conn: Any = None
        self._init_connection()

    def _init_connection(self):
        """Initialize the ADBC connection."""
        # Build user agent string
        ua_string = config.SPICE_USER_AGENT
        if self._user_agent:
            ua_string = f"{self._user_agent} {ua_string}"

        # ADBC database options (passed to db_kwargs)
        db_kwargs: dict[str, str] = {}

        # Add user agent header
        db_kwargs["adbc.flight.sql.rpc.call_header.user-agent"] = ua_string

        # Add authentication if API key provided
        if self._api_key:
            db_kwargs[adbc_driver_manager.DatabaseOptions.USERNAME.value] = ""
            db_kwargs[adbc_driver_manager.DatabaseOptions.PASSWORD.value] = (
                self._api_key
            )

        # Create low-level database and connection (avoids dbapi autocommit warning)
        self._db = adbc_driver_flightsql.connect(self._uri, db_kwargs=db_kwargs)
        self._conn = adbc_driver_manager.AdbcConnection(self._db)

    def _create_param_batch(
        self,
        params: list[Any],
    ) -> pa.RecordBatch:
        """Create a parameter record batch for binding to a prepared statement.

        Args:
            params: List of parameter values. Each can be:
                - A plain Python value (int, str, float, etc.) - type will be inferred
                - A tuple of (value, pyarrow.DataType) for explicit type control

        Returns:
            Arrow RecordBatch containing the parameter values
        """
        param_values = []
        param_types = []

        for param in params:
            # Check if param is a tuple of (value, arrow_type)
            if (
                isinstance(param, tuple)
                and len(param) == 2
                and isinstance(param[1], pa.DataType)
            ):
                value, arrow_type = param
                param_values.append(value)
                param_types.append(arrow_type)
            else:
                param_values.append(param)
                param_types.append(infer_arrow_type(param))

        # Create parameter arrays (each with a single row)
        param_arrays = []
        for value, arrow_type in zip(param_values, param_types, strict=True):
            param_arrays.append(pa.array([value], type=arrow_type))

        # Create parameter schema with positional field names ($1, $2, etc.)
        param_fields = [
            pa.field(f"${i + 1}", param_types[i]) for i in range(len(params))
        ]
        param_schema = pa.schema(param_fields)

        return pa.record_batch(param_arrays, schema=param_schema)

    def query_with_params(
        self,
        sql: str,
        params: list[Any],
    ) -> pa.RecordBatchReader:
        """Execute a parameterized SQL query using prepared statements.

        Args:
            sql: SQL query with positional placeholders ($1, $2, etc.)
            params: List of parameter values. Each can be:
                - A plain Python value (int, str, float, etc.) - type will be inferred
                - A tuple of (value, pyarrow.DataType) for explicit type control

        Returns:
            Arrow RecordBatchReader with query results
        """
        # Create a new statement
        stmt = adbc_driver_manager.AdbcStatement(self._conn)

        try:
            # Set the SQL query
            stmt.set_sql_query(sql)

            if params:
                # Prepare the statement for parameterized execution
                stmt.prepare()

                # Create parameter batch and bind
                param_batch = self._create_param_batch(params)

                # Bind parameters
                stmt.bind(param_batch)

            # Execute and get results
            handle, _ = stmt.execute_query()

            # Read results into Arrow table using from_stream
            reader = pa.RecordBatchReader.from_stream(handle)
            # Consume reader into table, then return a new reader
            table = reader.read_all()
            return table.to_reader()
        finally:
            stmt.close()

    def close(self):
        """Close the ADBC connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
        if self._db:
            self._db.close()
            self._db = None


class _Cert:
    def __init__(
        self,
        tls_root_cert,
    ):
        if tls_root_cert is not None:
            tls_root_cert = (
                tls_root_cert
                if isinstance(tls_root_cert, Path)
                else Path(tls_root_cert)
            )
        else:
            tls_root_cert = Path(certifi.where())

        self.tls_root_certs = self.read_cert(tls_root_cert)

    def read_cert(self, tls_root_cert):
        with open(tls_root_cert, "rb") as cert_file:
            return cert_file.read()


class _SpiceFlight:
    @staticmethod
    def _user_agent(custom_user_agent=None):
        # headers kwargs claim to support Tuple[str, str], but it's actually Tuple[bytes, bytes]
        # Open issue in Arrow: https://github.com/apache/arrow/issues/35288

        # Prepend the custom user agent (if provided) to the default user agent
        if custom_user_agent:
            return (
                str.encode("user-agent"),
                str.encode(f"{custom_user_agent} {config.SPICE_USER_AGENT}"),
            )
        return (str.encode("user-agent"), str.encode(config.SPICE_USER_AGENT))

    def __init__(
        self,
        grpc: str,
        api_key: str,
        tls_root_certs,
        user_agent=None,
        tls_client_certificate: str | Path | None = None,
        tls_client_key: str | Path | None = None,
    ):
        connect_kwargs = {"tls_root_certs": tls_root_certs}
        if tls_client_certificate is not None and tls_client_key is not None:
            cert_path = (
                tls_client_certificate
                if isinstance(tls_client_certificate, Path)
                else Path(tls_client_certificate)
            )
            key_path = (
                tls_client_key
                if isinstance(tls_client_key, Path)
                else Path(tls_client_key)
            )
            with open(cert_path, "rb") as f:
                connect_kwargs["cert_chain"] = f.read()
            with open(key_path, "rb") as f:
                connect_kwargs["private_key"] = f.read()
        self._flight_client = flight.connect(grpc, **connect_kwargs)
        self._api_key = api_key
        self.headers = [_SpiceFlight._user_agent(user_agent)]
        self._flight_options = flight.FlightCallOptions(
            headers=self.headers, timeout=DEFAULT_QUERY_TIMEOUT_SECS
        )
        self._authenticate()

    def _authenticate(self):
        if self._api_key:
            self.headers = [
                self._flight_client.authenticate_basic_token("", self._api_key),
                _SpiceFlight._user_agent(),
            ]
            self._flight_options = flight.FlightCallOptions(
                headers=self.headers, timeout=DEFAULT_QUERY_TIMEOUT_SECS
            )
        else:
            self.headers = [_SpiceFlight._user_agent()]
            self._flight_options = flight.FlightCallOptions(
                headers=self.headers, timeout=DEFAULT_QUERY_TIMEOUT_SECS
            )

    def query(self, query: str, **kwargs) -> flight.FlightStreamReader:
        timeout = kwargs.get("timeout")

        if timeout is not None:
            if not isinstance(timeout, int) or timeout <= 0:
                raise ValueError("Timeout must be a positive integer")
            self._flight_options = flight.FlightCallOptions(
                headers=self.headers, timeout=timeout
            )

        flight_info = self._flight_client.get_flight_info(
            flight.FlightDescriptor.for_command(query), self._flight_options
        )

        try:
            reader = self._threaded_flight_do_get(
                ticket=flight_info.endpoints[0].ticket
            )
        except flight.FlightUnauthenticatedError:
            self._authenticate()
            reader = self._threaded_flight_do_get(
                ticket=flight_info.endpoints[0].ticket
            )
        except flight.FlightTimedOutError as exc:
            raise TimeoutError(
                f"Query timed out and was canceled after {timeout} seconds."
            ) from exc

        return reader

    def _threaded_flight_do_get(self, ticket: Ticket):
        thread = _ArrowFlightCallThread(
            ticket=ticket,
            flight_options=self._flight_options,
            flight_client=self._flight_client,
        )
        thread.start()
        while thread.is_alive():
            thread.join(1)

        return thread.reader


class Client:
    # pylint: disable=R0917
    def __init__(
        self,
        api_key: str | None = None,
        flight_url: str = config.DEFAULT_LOCAL_FLIGHT_URL,
        http_url: str = config.DEFAULT_HTTP_URL,
        tls_root_cert: str | Path | None = None,
        user_agent: str | None = None,
        tls_client_certificate: str | Path | None = None,
        tls_client_key: str | Path | None = None,
    ):  # pylint: disable=R0913
        # Validate that client cert and key are either both set or both unset
        has_cert = tls_client_certificate is not None
        has_key = tls_client_key is not None
        if has_cert != has_key:
            missing = "tls_client_key" if has_cert else "tls_client_certificate"
            raise ValueError(
                f"Both tls_client_certificate and tls_client_key must be "
                f"provided together for mTLS. {missing} is missing."
            )

        tls_root_certs = _Cert(tls_root_cert).tls_root_certs
        self._flight = _SpiceFlight(
            flight_url,
            api_key or "",
            tls_root_certs,
            user_agent,
            tls_client_certificate=tls_client_certificate,
            tls_client_key=tls_client_key,
        )

        self.api_key = api_key
        self._flight_url = flight_url
        self._user_agent = user_agent
        self._adbc_client: _ADBCClient | None = None
        self.http = HttpRequests(
            http_url,
            self._headers(user_agent),
            tls_client_certificate=tls_client_certificate,
            tls_client_key=tls_client_key,
        )

    def _headers(self, user_agent=None) -> dict[str, str]:
        headers = {
            "X-API-Key": self._api_key(),
            "Accept": "application/json",
        }
        if user_agent is not None:
            headers["user-agent"] = user_agent
        else:
            headers["user-agent"] = config.SPICE_USER_AGENT
        return headers

    def _api_key(self) -> str:
        key = self.api_key
        if key is None:
            key = os.environ.get("SPICE_API_KEY")
        return key or ""

    def _get_adbc_uri(self) -> str:
        """Convert the Flight URL to an ADBC-compatible URI."""
        # ADBC FlightSQL driver uses the same URI format as Arrow Flight
        return self._flight_url

    def _ensure_adbc_client(self) -> _ADBCClient:
        """Lazily initialize the ADBC client."""
        if self._adbc_client is None:
            self._adbc_client = _ADBCClient(
                uri=self._get_adbc_uri(),
                api_key=self._api_key(),
                user_agent=self._user_agent,
            )
        return self._adbc_client

    def query(self, query: str, **kwargs) -> flight.FlightStreamReader:
        """Execute a SQL query against Spice.

        Args:
            query: SQL query string
            **kwargs: Additional options including:
                - timeout: Query timeout in seconds

        Returns:
            FlightStreamReader with query results
        """
        return self._flight.query(query, **kwargs)

    def query_with_params(
        self,
        sql: str,
        params: list[Any],
    ) -> pa.RecordBatchReader:
        """Execute a parameterized SQL query using ADBC.

        This method is recommended for queries with user input to prevent SQL injection.
        Parameters should use positional placeholders ($1, $2, etc.) in the SQL query.

        Parameters can be:
        - Simple Python values (int, str, float, bool, etc.) - type will be inferred
        - Tuples of (value, pyarrow.DataType) for explicit type control

        Example:
            # With automatic type inference
            reader = client.query_with_params(
                "SELECT * FROM table WHERE id = $1 AND name = $2",
                [123, "test"]
            )

            # With explicit PyArrow types
            import pyarrow as pa
            reader = client.query_with_params(
                "SELECT * FROM table WHERE id = $1 AND amount = $2",
                [(123, pa.int32()), (99.99, pa.float64())]
            )

        Args:
            sql: SQL query with positional placeholders ($1, $2, etc.)
            params: List of parameter values (plain values or (value, pa.DataType) tuples)

        Returns:
            Arrow RecordBatchReader with query results

        Raises:
            ImportError: If ADBC driver is not installed
            TypeError: If a parameter type is not supported
            ValueError: If params is None
        """
        if params is None:
            raise ValueError(
                "params must be a list, not None. Use [] for queries without parameters."
            )
        adbc = self._ensure_adbc_client()
        return adbc.query_with_params(sql, params)

    def _read_table(
        self,
        sql: str,
        params: list[Any] | None,
        timeout: int | None,
    ) -> pa.Table:
        if params is not None:
            return self.query_with_params(sql, params).read_all()
        kwargs: dict[str, Any] = {}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return self.query(sql, **kwargs).read_all()

    def query_arrow(
        self,
        sql: str,
        *,
        params: list[Any] | None = None,
        timeout: int | None = None,
    ) -> pa.Table:
        """Execute a SQL query and return results as a PyArrow Table.

        Args:
            sql: SQL query string. Use $1, $2, ... placeholders if passing params.
            params: Optional list of parameter values. When provided, the query is
                executed via ADBC FlightSQL with prepared statements. See
                :meth:`query_with_params` for parameter format.
            timeout: Optional query timeout in seconds (ignored when params is set).

        Returns:
            Arrow Table with all query results materialized in memory.
        """
        return self._read_table(sql, params, timeout)

    def query_pandas(
        self,
        sql: str,
        *,
        params: list[Any] | None = None,
        timeout: int | None = None,
    ) -> "pd.DataFrame":
        """Execute a SQL query and return results as a pandas DataFrame.

        See :meth:`query_arrow` for argument semantics.
        """
        return cast("pd.DataFrame", self._read_table(sql, params, timeout).to_pandas())

    def query_polars(
        self,
        sql: str,
        *,
        params: list[Any] | None = None,
        timeout: int | None = None,
    ) -> "pl.DataFrame":
        """Execute a SQL query and return results as a polars DataFrame.

        Requires the optional ``polars`` dependency:
        ``pip install spicepy[polars]``.

        See :meth:`query_arrow` for argument semantics.
        """
        try:
            import polars as pl
        except ImportError as exc:
            raise ImportError(
                "polars is not installed. Install it with: pip install spicepy[polars]"
            ) from exc
        return cast(
            "pl.DataFrame", pl.from_arrow(self._read_table(sql, params, timeout))
        )

    def query_pylist(
        self,
        sql: str,
        *,
        params: list[Any] | None = None,
        timeout: int | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a SQL query and return results as a list of row dicts.

        See :meth:`query_arrow` for argument semantics.
        """
        return cast(
            "list[dict[str, Any]]",
            self._read_table(sql, params, timeout).to_pylist(),
        )

    def query_pydict(
        self,
        sql: str,
        *,
        params: list[Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, list[Any]]:
        """Execute a SQL query and return results as a column-oriented dict."""
        return cast(
            "dict[str, list[Any]]",
            self._read_table(sql, params, timeout).to_pydict(),
        )

    def query_batches(
        self,
        sql: str,
        *,
        timeout: int | None = None,
    ) -> Iterator[pa.RecordBatch]:
        """Execute a SQL query and yield Arrow RecordBatches as they stream in.

        Unlike :meth:`query_arrow`, this does not materialize the full result
        in memory before returning.
        """
        kwargs: dict[str, Any] = {}
        if timeout is not None:
            kwargs["timeout"] = timeout
        reader = self.query(sql, **kwargs)
        for chunk in reader:
            # FlightStreamReader yields FlightStreamChunk; pa.RecordBatchReader yields RecordBatch.
            batch = getattr(chunk, "data", chunk)
            if batch is not None:
                yield batch

    # ------------------------------------------------------------------
    # Catalog introspection
    # ------------------------------------------------------------------

    def catalogs(self) -> list[str]:
        """List catalog names visible to this connection."""
        rows = self.query_pylist(
            "SELECT DISTINCT catalog_name FROM information_schema.schemata "
            "ORDER BY catalog_name"
        )
        return [r["catalog_name"] for r in rows]

    def schemas(self, catalog: str | None = None) -> list[str]:
        """List schema names, optionally restricted to a catalog."""
        if catalog is None:
            rows = self.query_pylist(
                "SELECT schema_name FROM information_schema.schemata "
                "ORDER BY schema_name"
            )
        else:
            from ._sql import quote_literal

            rows = self.query_pylist(
                "SELECT schema_name FROM information_schema.schemata "
                f"WHERE catalog_name = {quote_literal(catalog)} "
                "ORDER BY schema_name"
            )
        return [r["schema_name"] for r in rows]

    def tables(self, schema: str | None = None) -> list[str]:
        """List table names, optionally restricted to a schema."""
        if schema is None:
            rows = self.query_pylist(
                "SELECT table_name FROM information_schema.tables "
                "ORDER BY table_schema, table_name"
            )
        else:
            from ._sql import quote_literal

            rows = self.query_pylist(
                "SELECT table_name FROM information_schema.tables "
                f"WHERE table_schema = {quote_literal(schema)} "
                "ORDER BY table_name"
            )
        return [r["table_name"] for r in rows]

    def describe(self, table: str) -> "pd.DataFrame":
        """Return column metadata (name, type, nullability) for a table."""
        from ._sql import quote_ident

        return self.query_pandas(f"DESCRIBE {quote_ident(table)}")

    def get_schema(self, sql: str) -> pa.Schema:
        """Return the Arrow schema of a query without materializing rows."""
        return self.query(f"SELECT * FROM ({sql}) LIMIT 0").read_all().schema

    def explain(
        self,
        sql: str,
        *,
        analyze: bool = False,
        verbose: bool = False,
    ) -> str:
        """Run EXPLAIN against ``sql`` and return the textual plan."""
        prefix = "EXPLAIN"
        if analyze:
            prefix += " ANALYZE"
        if verbose:
            prefix += " VERBOSE"
        rows = self.query_pylist(f"{prefix} {sql}")
        return "\n".join((r.get("plan") or r.get("plan_type") or str(r)) for r in rows)

    def show(self, sql: str, n: int = 20) -> None:
        """Pretty-print the first ``n`` rows of ``sql``."""
        df = self.query_pandas(f"SELECT * FROM ({sql}) LIMIT {int(n)}")
        print(df.to_string(index=False))  # noqa: T201

    # ------------------------------------------------------------------
    # Writers
    # ------------------------------------------------------------------

    def write_parquet(self, sql: str, path: str, **kwargs: Any) -> None:
        """Stream the result of ``sql`` to a Parquet file at ``path``."""
        import pyarrow.parquet as pq

        reader = self.query(sql)
        with pq.ParquetWriter(path, reader.schema, **kwargs) as writer:
            for chunk in reader:
                batch = getattr(chunk, "data", chunk)
                if batch is not None:
                    writer.write_batch(batch)

    def write_csv(self, sql: str, path: str, **kwargs: Any) -> None:
        """Stream the result of ``sql`` to a CSV file at ``path``."""
        import pyarrow.csv as pa_csv

        reader = self.query(sql)
        with pa_csv.CSVWriter(path, reader.schema, **kwargs) as writer:
            for chunk in reader:
                batch = getattr(chunk, "data", chunk)
                if batch is not None:
                    writer.write_batch(batch)

    def write_json(self, sql: str, path: str) -> None:
        """Write the result of ``sql`` to ``path`` as newline-delimited JSON."""
        import json as _json

        table = self.query_arrow(sql)
        with open(path, "w", encoding="utf-8") as fh:
            for row in table.to_pylist():
                fh.write(_json.dumps(row, default=str))
                fh.write("\n")

    # ------------------------------------------------------------------
    # DataFrame entry points
    # ------------------------------------------------------------------

    def table(self, name: str) -> "SpiceDataFrame":
        """Return a lazy DataFrame referencing ``name`` as a table."""
        from ._dataframe import SpiceDataFrame
        from ._sql import quote_ident

        return SpiceDataFrame(self, f"SELECT * FROM {quote_ident(name)}")

    def sql(self, query: str) -> "SpiceDataFrame":
        """Return a lazy DataFrame wrapping an arbitrary SQL query."""
        from ._dataframe import SpiceDataFrame

        return SpiceDataFrame(self, query)

    def from_arrow(self, table: pa.Table) -> "SpiceDataFrame":
        """Return a lazy DataFrame backed by an inline VALUES clause.

        Intended for small literal tables; large data should be loaded
        server-side as a dataset.
        """
        from ._dataframe import values_dataframe

        return values_dataframe(self, table.to_pylist())

    def from_pandas(self, df: "pd.DataFrame") -> "SpiceDataFrame":
        """Return a lazy DataFrame from a pandas DataFrame via inline VALUES."""
        import pyarrow as pa

        return self.from_arrow(pa.Table.from_pandas(df))

    def from_pydict(self, data: dict[str, list[Any]]) -> "SpiceDataFrame":
        """Return a lazy DataFrame from a column-oriented dict via inline VALUES."""
        import pyarrow as pa

        return self.from_arrow(pa.Table.from_pydict(data))

    def runtime_status(self) -> list[ConnectionDetails]:
        """Return the status of each runtime connection.

        Backed by ``GET /v1/status``. Where :meth:`is_ready` reports a single boolean
        for the whole runtime, this reports ``http``, ``flight``, ``metrics`` and
        ``opentelemetry`` individually, so it can say *which* component is not ready.
        """
        response = self.http.send_request("GET", "/v1/status")

        if not isinstance(response, list):
            raise SpiceAIError(
                f"Unexpected response from /v1/status: expected a list of "
                f"components, got {type(response).__name__}."
            )

        for index, item in enumerate(response):
            if not isinstance(item, dict):
                raise SpiceAIError(
                    f"Unexpected response from /v1/status: expected component "
                    f"{index} to be an object, got {type(item).__name__}."
                )

        return [ConnectionDetails.from_dict(item) for item in response]

    def is_ready(self) -> bool:
        """Return whether the runtime is ready to serve queries.

        Backed by ``GET /v1/ready``, which answers ``200`` when ready and ``503``
        when not. Any other status raises :class:`SpiceAIError`, so "not ready" and
        "could not ask" stay distinguishable.
        """
        response = self.http.send_request_raw("GET", "/v1/ready")

        if response.status_code == 200:
            return True
        if response.status_code == 503:
            return False

        raise SpiceAIError(
            f"Unexpected response from /v1/ready: HTTP {response.status_code}."
        )

    def list_active_queries(self) -> list[ActiveQuery]:
        """Return the synchronous queries running in the caller's scope.

        Backed by ``GET /v1/sql/active``. Synchronous queries are the ones started by
        :meth:`query`, :meth:`query_with_params`, FlightSQL, NSQL and search — not
        async query jobs, which the runtime only serves in cluster mode.

        The runtime does not return a query's id to the client that submitted it, so
        this is how to find the id that :meth:`cancel_active_query` needs.

        Results are scoped to the authenticated principal — an API key or a client
        certificate — not to this :class:`Client`: every client presenting the same
        credential lists the same queries, and requests for which the runtime
        establishes no principal share its ``public`` scope.

        Results also cover one runtime instance. The runtime holds active queries in
        memory per process, so behind a load balancer ``http_url`` may resolve to an
        instance that never received the query.

        Runtime releases up to and including ``v2.1.5`` do not scope these two
        endpoints at all; see the note in README.md.
        """
        response = self.http.send_request_raw("GET", "/v1/sql/active")

        if response.status_code == 403:
            raise SpiceAIError(
                "The configured API key does not allow listing queries. Use a key "
                "with write access."
            )
        if response.status_code != 200:
            raise SpiceAIError(
                f"Unexpected response from /v1/sql/active: HTTP {response.status_code}."
            )

        payload = response.json()
        if not isinstance(payload, dict):
            raise SpiceAIError(
                f"Unexpected response from /v1/sql/active: expected an object, got "
                f"{type(payload).__name__}."
            )

        queries = payload.get("queries", [])
        if not isinstance(queries, list):
            raise SpiceAIError(
                f"Unexpected response from /v1/sql/active: expected 'queries' to be a "
                f"list, got {type(queries).__name__}."
            )

        for index, item in enumerate(queries):
            if not isinstance(item, dict):
                raise SpiceAIError(
                    f"Unexpected response from /v1/sql/active: expected query {index} "
                    f"to be an object, got {type(item).__name__}."
                )

        return [ActiveQuery.from_dict(item) for item in queries]

    def cancel_active_query(self, query_id: str) -> None:
        """Cancel a running synchronous query by id.

        Backed by ``POST /v1/sql/{query_id}/cancel``. ``query_id`` comes from
        :meth:`list_active_queries`. Cancellation is scoped to the authenticated
        principal, not to this :class:`Client`: any client presenting the same
        credential can cancel the query, while an id outside that scope is reported as
        not found. Like :meth:`list_active_queries` it reaches one runtime instance and
        carries the same runtime-version caveat.

        Returns ``None`` on success and raises :class:`SpiceAIError` otherwise.
        """
        if not query_id:
            raise SpiceAIError(
                "query_id is required. Use list_active_queries() to find one."
            )

        # query_id is caller input and reaches the runtime as a path segment.
        # Reject anything that is not a UUID here rather than building a path
        # from it: "." and ".." are unreserved, so quoting leaves them intact
        # and requests then resolves them away — ".." would send this POST to
        # /v1/cancel, a route the caller never named.
        try:
            uuid.UUID(query_id)
        except ValueError as exc:
            raise SpiceAIError(
                f"Query id {query_id!r} is not a valid UUID. Use the query_id from "
                f"list_active_queries()."
            ) from exc

        quoted_query_id = quote(query_id, safe="")
        response = self.http.send_request_raw(
            "POST", f"/v1/sql/{quoted_query_id}/cancel"
        )

        if response.status_code == 200:
            return
        if response.status_code == 400:
            raise SpiceAIError(
                f"Query id {query_id!r} is not a valid UUID. Use the query_id from "
                f"list_active_queries()."
            )
        if response.status_code == 403:
            raise SpiceAIError(
                "The configured API key does not allow cancelling queries. Use a key "
                "with write access."
            )
        if response.status_code == 404:
            raise SpiceAIError(
                f"No active query {query_id!r} found. It may have already finished, "
                f"or it was submitted under a different API key."
            )

        raise SpiceAIError(
            f"Unexpected response from /v1/sql/{quoted_query_id}/cancel: "
            f"HTTP {response.status_code}."
        )

    def refresh_dataset(
        self, dataset: str, refresh_opts: RefreshOpts | None = None
    ) -> Any:
        response = self.http.send_request(
            "POST",
            f"/v1/datasets/{dataset}/acceleration/refresh",
            body=(
                json.dumps(refresh_opts.to_dict())
                if refresh_opts is not None
                else json.dumps({})
            ),
            headers={"Content-Type": "application/json"},
        )

        return response


class _ArrowFlightCallThread(threading.Thread):
    def __init__(
        self,
        flight_client: FlightClient,
        ticket: Ticket,
        flight_options: FlightCallOptions,
    ):
        super().__init__()
        self._exc = None
        self._flight_client = flight_client
        self._ticket = ticket
        self._flight_options = flight_options
        self.reader = None

    def run(self):
        try:
            self.reader = self._flight_client.do_get(self._ticket, self._flight_options)
        except BaseException as exc:  # pylint: disable=W0718
            self._exc = exc

    def join(self, timeout=None):
        super().join(timeout)
        if self._exc:
            raise self._exc
