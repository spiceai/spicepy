import json
import os
import platform
import threading
from pathlib import Path
from typing import Any, Optional, Union

import certifi
import pyarrow as pa

# pylint: disable=E0611
from pyarrow._flight import (
    FlightCallOptions,
    FlightClient,
    Ticket,
)

from . import config
from ._http import HttpRequests, RefreshOpts
from .params import infer_arrow_type


def is_macos_arm64() -> bool:
    return platform.platform().lower().startswith("macos") and platform.machine() == "arm64"


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
        api_key: Optional[str] = None,
        user_agent: Optional[str] = None,
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
            db_kwargs[adbc_driver_manager.DatabaseOptions.PASSWORD.value] = self._api_key

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
            if isinstance(param, tuple) and len(param) == 2 and isinstance(param[1], pa.DataType):
                value, arrow_type = param
                param_values.append(value)
                param_types.append(arrow_type)
            else:
                param_values.append(param)
                param_types.append(infer_arrow_type(param))

        # Create parameter arrays (each with a single row)
        param_arrays = []
        for value, arrow_type in zip(param_values, param_types):
            param_arrays.append(pa.array([value], type=arrow_type))

        # Create parameter schema with positional field names ($1, $2, etc.)
        param_fields = [pa.field(f"${i + 1}", param_types[i]) for i in range(len(params))]
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
            tls_root_cert = tls_root_cert if isinstance(tls_root_cert, Path) else Path(tls_root_cert)
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
            return (str.encode("user-agent"), str.encode(f"{custom_user_agent} {config.SPICE_USER_AGENT}"))
        return (str.encode("user-agent"), str.encode(config.SPICE_USER_AGENT))

    def __init__(self, grpc: str, api_key: str, tls_root_certs, user_agent=None):
        self._flight_client = flight.connect(grpc, tls_root_certs=tls_root_certs)
        self._api_key = api_key
        self.headers = [_SpiceFlight._user_agent(user_agent)]
        self._flight_options = flight.FlightCallOptions(headers=self.headers, timeout=DEFAULT_QUERY_TIMEOUT_SECS)
        self._authenticate()

    def _authenticate(self):
        if self._api_key is not None:
            self.headers = [
                self._flight_client.authenticate_basic_token("", self._api_key),
                _SpiceFlight._user_agent(),
            ]
            self._flight_options = flight.FlightCallOptions(headers=self.headers, timeout=DEFAULT_QUERY_TIMEOUT_SECS)
        else:
            self.headers = [_SpiceFlight._user_agent()]
            self._flight_options = flight.FlightCallOptions(headers=self.headers, timeout=DEFAULT_QUERY_TIMEOUT_SECS)

    def query(self, query: str, **kwargs) -> flight.FlightStreamReader:
        timeout = kwargs.get("timeout")

        if timeout is not None:
            if not isinstance(timeout, int) or timeout <= 0:
                raise ValueError("Timeout must be a positive integer")
            self._flight_options = flight.FlightCallOptions(headers=self.headers, timeout=timeout)

        flight_info = self._flight_client.get_flight_info(
            flight.FlightDescriptor.for_command(query), self._flight_options
        )

        try:
            reader = self._threaded_flight_do_get(ticket=flight_info.endpoints[0].ticket)
        except flight.FlightUnauthenticatedError:
            self._authenticate()
            reader = self._threaded_flight_do_get(ticket=flight_info.endpoints[0].ticket)
        except flight.FlightTimedOutError as exc:
            raise TimeoutError(f"Query timed out and was canceled after {timeout} seconds.") from exc

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
        api_key: Optional[str] = None,
        flight_url: str = config.DEFAULT_LOCAL_FLIGHT_URL,
        http_url: str = config.DEFAULT_HTTP_URL,
        tls_root_cert: Union[str, Path, None] = None,
        user_agent: Optional[str] = None,
    ):  # pylint: disable=R0913
        tls_root_certs = _Cert(tls_root_cert).tls_root_certs
        self._flight = _SpiceFlight(flight_url, api_key or "", tls_root_certs, user_agent)

        self.api_key = api_key
        self._flight_url = flight_url
        self._user_agent = user_agent
        self._adbc_client: Optional[_ADBCClient] = None
        self.http = HttpRequests(http_url, self._headers(user_agent))

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
            raise ValueError("params must be a list, not None. Use [] for queries without parameters.")
        adbc = self._ensure_adbc_client()
        return adbc.query_with_params(sql, params)

    def refresh_dataset(self, dataset: str, refresh_opts: Optional[RefreshOpts] = None) -> Any:
        response = self.http.send_request(
            "POST",
            f"/v1/datasets/{dataset}/acceleration/refresh",
            body=(json.dumps(refresh_opts.to_dict()) if refresh_opts is not None else json.dumps({})),
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
