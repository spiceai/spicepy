"""Asynchronous SQL query submission via the runtime's ``/v1/queries`` API.

Async queries require the runtime to be running in distributed/scheduler mode
(``spiced --role scheduler`` with ``runtime.scheduler.state_location``
configured). Use :meth:`spicepy.Client.sql`/:meth:`spicepy.Client.sql_with_params`
for the synchronous, streaming path against a default single-node runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import json
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from .error import SpiceAIError

if TYPE_CHECKING:
    from ._client import Client

QUERIES_PATH = "/v1/queries"

# How often wait() polls the runtime for a status change.
DEFAULT_POLL_INTERVAL_SECONDS = 0.5


class QueryStatus(StrEnum):
    """The lifecycle status of an async query job, as reported by the runtime.

    A status this SDK does not recognize is preserved as-is rather than
    raising, so :meth:`from_value` never fails on a runtime that has added a
    new status this SDK predates.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"

    @classmethod
    def from_value(cls, value: str) -> QueryStatus | str:
        """Return the matching member, or ``value`` unchanged if unrecognized."""
        try:
            return cls(value)
        except ValueError:
            return value

    @property
    def is_terminal(self) -> bool:
        """Whether the job has reached a status it will not transition out of."""
        return self in (
            QueryStatus.SUCCEEDED,
            QueryStatus.FAILED,
            QueryStatus.CANCELLED,
            QueryStatus.CLOSED,
        )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class QueryJobError:
    """Error details for a job that reached :attr:`QueryStatus.FAILED`."""

    error_code: str
    message: str
    sql_state: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueryJobError:
        return cls(
            error_code=data.get("error_code", "UNKNOWN"),
            message=data.get("message", ""),
            sql_state=data.get("sql_state"),
        )

    def __str__(self) -> str:
        return f"{self.error_code}: {self.message}"


@dataclass(frozen=True)
class QueryResult:
    """The materialized results of a completed :class:`QueryJob`.

    Iterating a ``QueryResult`` yields its rows directly, each a dict keyed by
    column name — the same JSON-decoded shape :class:`~spicepy.NsqlResult`
    returns, since the runtime answers this endpoint as JSON rows rather than
    Arrow-typed data.
    """

    data: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0

    def __iter__(self):
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)


def _query_error_message(response_json: Any, status_code: int) -> str:
    """Extract the runtime's plain-text explanation from a transport-level error.

    These endpoints answer routing/availability failures (503 cluster mode
    required, 404 not found, ...) as ``{"error": "..."}`` — a different, flatter
    shape than the ``error_code``/``message``/``sql_state`` object a job's own
    ``error`` field carries once submitted.
    """
    if isinstance(response_json, dict):
        detail = response_json.get("error")
        if isinstance(detail, str) and detail:
            return detail
    return f"HTTP {status_code}"


def submit_query(client: Client, sql: str, *, parameters: list[Any] | None) -> QueryJob:
    """Submit ``sql`` for asynchronous execution and return a job handle."""
    if not sql or not sql.strip():
        raise ValueError("query must be a non-empty SQL string")

    body: dict[str, Any] = {"sql": sql}
    if parameters is not None:
        body["parameters"] = parameters

    response = client.http.send_request_raw(
        "POST",
        QUERIES_PATH,
        body=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if response.status_code != 202:
        raise SpiceAIError(
            f"Failed to submit async query: {_query_error_message(payload, response.status_code)}"
        )

    if not isinstance(payload, dict) or "query_id" not in payload:
        raise SpiceAIError(
            f"Unexpected response from POST {QUERIES_PATH}: expected an object "
            f"with a query_id, got {payload!r}."
        )

    return QueryJob(
        client,
        query_id=payload["query_id"],
        status=QueryStatus.from_value(payload.get("status", "")),
    )


class QueryJob:
    """A handle to a query submitted for asynchronous execution.

    Returned by :meth:`spicepy.Client.query`/:meth:`spicepy.Client.query_with_params`.
    Not safe for concurrent use from multiple threads.
    """

    def __init__(
        self, client: Client, query_id: str, status: QueryStatus | str
    ) -> None:
        self._client = client
        self._query_id = query_id
        self._status = status

    @property
    def query_id(self) -> str:
        """The server-assigned id for this job."""
        return self._query_id

    def status(self) -> QueryStatus | str:
        """Poll the runtime once and return the job's current status."""
        quoted = quote(self._query_id, safe="")
        response = self._client.http.send_request_raw(
            "GET", f"{QUERIES_PATH}/{quoted}/status"
        )

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if response.status_code != 200:
            raise SpiceAIError(
                f"Failed to get status for async query {self._query_id!r}: "
                f"{_query_error_message(payload, response.status_code)}"
            )
        if not isinstance(payload, dict):
            raise SpiceAIError(
                f"Unexpected response from GET {QUERIES_PATH}/{quoted}/status: "
                f"expected an object, got {payload!r}."
            )

        self._status = QueryStatus.from_value(payload.get("status", ""))
        return self._status

    def wait(
        self,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        timeout: float | None = None,
    ) -> QueryStatus | str:
        """Block, polling the runtime, until the job reaches a terminal status.

        Raises:
            SpiceAIError: If ``timeout`` elapses before the job terminates.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            status = self.status()
            if isinstance(status, QueryStatus) and status.is_terminal:
                return status
            if deadline is not None and time.monotonic() >= deadline:
                raise SpiceAIError(
                    f"Timed out waiting for async query {self._query_id!r} to "
                    f"complete (last status: {status})."
                )
            time.sleep(poll_interval)

    def results(self) -> QueryResult:
        """Wait for completion, then fetch and concatenate all result chunks.

        Raises:
            SpiceAIError: If the job does not reach :attr:`QueryStatus.SUCCEEDED`,
                or a chunk fetch fails partway through.
        """
        final_status = self.wait()
        if final_status != QueryStatus.SUCCEEDED:
            error = self._fetch_error()
            detail = f": {error}" if error is not None else ""
            raise SpiceAIError(
                f"Async query {self._query_id!r} did not succeed "
                f"(status: {final_status}){detail}"
            )

        rows: list[dict[str, Any]] = []
        chunk_index = 0
        while True:
            chunk = self._fetch_chunk(chunk_index)
            rows.extend(chunk.get("data_array") or [])
            next_index = chunk.get("next_chunk_index")
            if next_index is None:
                break
            chunk_index = next_index

        return QueryResult(data=rows, row_count=len(rows))

    def cancel(self) -> None:
        """Request cancellation of this job.

        Best-effort: a job that has already reached a terminal status is not
        reported as an error. Call :meth:`status` to observe the outcome.
        """
        quoted = quote(self._query_id, safe="")
        response = self._client.http.send_request_raw(
            "POST", f"{QUERIES_PATH}/{quoted}/cancel"
        )

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if response.status_code == 409:
            # Already terminal — not worth raising over, mirrors
            # cancel_active_query's treatment of a query that already finished.
            return
        if response.status_code != 200:
            raise SpiceAIError(
                f"Failed to cancel async query {self._query_id!r}: "
                f"{_query_error_message(payload, response.status_code)}"
            )

        if isinstance(payload, dict) and "status" in payload:
            self._status = QueryStatus.from_value(payload["status"])

    def _fetch_error(self) -> QueryJobError | None:
        quoted = quote(self._query_id, safe="")
        response = self._client.http.send_request_raw(
            "GET", f"{QUERIES_PATH}/{quoted}/status"
        )
        try:
            payload = response.json()
        except ValueError:
            return None
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            return QueryJobError.from_dict(payload["error"])
        return None

    def _fetch_chunk(self, chunk_index: int) -> dict[str, Any]:
        quoted = quote(self._query_id, safe="")
        response = self._client.http.send_request_raw(
            "GET", f"{QUERIES_PATH}/{quoted}/results/chunks/{chunk_index}"
        )

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if response.status_code != 200:
            raise SpiceAIError(
                f"Failed to fetch result chunk {chunk_index} for async query "
                f"{self._query_id!r}: "
                f"{_query_error_message(payload, response.status_code)}"
            )
        if not isinstance(payload, dict):
            raise SpiceAIError(
                f"Unexpected response fetching result chunk {chunk_index} for "
                f"async query {self._query_id!r}: expected an object, got "
                f"{payload!r}."
            )
        return payload


def list_queries(
    client: Client, status: str | None = None, limit: int | None = None
) -> ListQueriesResult:
    """Return a summary of async query jobs known to the runtime.

    Distinct from :meth:`spicepy.Client.list_active_queries`, which lists
    synchronous queries.
    """
    params: dict[str, Any] = {}
    if status is not None:
        params["status"] = status
    if limit is not None:
        params["limit"] = limit

    response = client.http.send_request_raw("GET", QUERIES_PATH, param=params or None)

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if response.status_code != 200:
        raise SpiceAIError(
            f"Failed to list async queries: "
            f"{_query_error_message(payload, response.status_code)}"
        )
    if not isinstance(payload, dict):
        raise SpiceAIError(
            f"Unexpected response from GET {QUERIES_PATH}: expected an object, "
            f"got {payload!r}."
        )

    return ListQueriesResult(
        queries=[QuerySummary.from_dict(item) for item in payload.get("queries") or []],
        total_count=payload.get("total_count", 0),
    )


@dataclass(frozen=True)
class QuerySummary:
    """A summary entry from :func:`list_queries`."""

    query_id: str
    status: QueryStatus | str
    sql_preview: str
    created_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuerySummary:
        return cls(
            query_id=data.get("query_id", ""),
            status=QueryStatus.from_value(data.get("status", "")),
            sql_preview=data.get("sql_preview", ""),
            created_at=data.get("created_at", ""),
        )


@dataclass(frozen=True)
class ListQueriesResult:
    """The result of :func:`list_queries`."""

    queries: list[QuerySummary]
    total_count: int

    def __iter__(self):
        return iter(self.queries)

    def __len__(self) -> int:
        return len(self.queries)
