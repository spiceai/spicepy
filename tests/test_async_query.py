"""Unit tests for spicepy._async_query and the Client async-query methods."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from spicepy._async_query import QueryJob, QueryStatus
from spicepy.error import SpiceAIError

pytestmark = pytest.mark.unit


def _client_with_http(http: MagicMock):
    """Build a Client without running __init__, with a stubbed http attribute."""
    from spicepy import Client

    client = object.__new__(Client)
    client.http = http
    return client


def _response(status_code: int, body=None):
    kwargs = {"status_code": status_code}
    if body is not None:
        kwargs["json.return_value"] = body
    return MagicMock(**kwargs)


class TestQuery:
    """Client.query() submits an async job."""

    def test_submits_and_returns_job(self) -> None:
        http = MagicMock()
        http.send_request_raw.return_value = _response(
            202, {"query_id": "job-1", "status": "PENDING"}
        )

        job = _client_with_http(http).query("SELECT * FROM large_table")

        assert isinstance(job, QueryJob)
        assert job.query_id == "job-1"
        method, path = http.send_request_raw.call_args.args
        assert method == "POST"
        assert path == "/v1/queries"
        body = json.loads(http.send_request_raw.call_args.kwargs["body"])
        assert body == {"sql": "SELECT * FROM large_table"}

    def test_rejects_empty_query_without_http_call(self) -> None:
        http = MagicMock()
        with pytest.raises(ValueError, match="non-empty"):
            _client_with_http(http).query("")
        http.send_request_raw.assert_not_called()

    def test_non_202_raises(self) -> None:
        http = MagicMock()
        http.send_request_raw.return_value = _response(
            503, {"error": "Async queries API requires distributed mode"}
        )
        with pytest.raises(SpiceAIError, match="distributed mode"):
            _client_with_http(http).query("SELECT 1")


class TestQueryWithParams:
    """Client.query_with_params() submits an async job with bind parameters."""

    def test_submits_with_parameters(self) -> None:
        http = MagicMock()
        http.send_request_raw.return_value = _response(
            202, {"query_id": "job-2", "status": "PENDING"}
        )

        job = _client_with_http(http).query_with_params(
            "SELECT * FROM t WHERE status = $1", ["active"]
        )

        assert job.query_id == "job-2"
        body = json.loads(http.send_request_raw.call_args.kwargs["body"])
        assert body == {
            "sql": "SELECT * FROM t WHERE status = $1",
            "parameters": ["active"],
        }

    def test_rejects_none_params(self) -> None:
        http = MagicMock()
        with pytest.raises(ValueError, match="must be a list, not None"):
            _client_with_http(http).query_with_params("SELECT 1", None)  # type: ignore[arg-type]
        http.send_request_raw.assert_not_called()


class TestQueryJobStatus:
    def test_polls_status_endpoint(self) -> None:
        http = MagicMock()
        http.send_request_raw.return_value = _response(200, {"status": "RUNNING"})

        job = QueryJob(_client_with_http(http), "job-1", QueryStatus.PENDING)
        status = job.status()

        assert status == QueryStatus.RUNNING
        http.send_request_raw.assert_called_once_with("GET", "/v1/queries/job-1/status")

    def test_unrecognized_status_is_preserved(self) -> None:
        http = MagicMock()
        http.send_request_raw.return_value = _response(200, {"status": "SOMETHING_NEW"})

        job = QueryJob(_client_with_http(http), "job-1", QueryStatus.PENDING)

        assert job.status() == "SOMETHING_NEW"

    def test_not_found_raises(self) -> None:
        http = MagicMock()
        http.send_request_raw.return_value = _response(404, {"error": "not found"})

        job = QueryJob(_client_with_http(http), "missing", QueryStatus.PENDING)

        with pytest.raises(SpiceAIError, match="not found"):
            job.status()


class TestQueryJobWait:
    def test_waits_through_pending_running_succeeded(self, monkeypatch) -> None:
        http = MagicMock()
        http.send_request_raw.side_effect = [
            _response(200, {"status": "PENDING"}),
            _response(200, {"status": "RUNNING"}),
            _response(200, {"status": "SUCCEEDED"}),
        ]
        monkeypatch.setattr("spicepy._async_query.time.sleep", lambda _: None)

        job = QueryJob(_client_with_http(http), "job-1", QueryStatus.PENDING)
        result = job.wait()

        assert result == QueryStatus.SUCCEEDED
        assert http.send_request_raw.call_count == 3

    def test_times_out(self, monkeypatch) -> None:
        http = MagicMock()
        http.send_request_raw.return_value = _response(200, {"status": "RUNNING"})

        times = iter([0.0, 0.0, 10.0, 20.0])
        monkeypatch.setattr("spicepy._async_query.time.monotonic", lambda: next(times))
        monkeypatch.setattr("spicepy._async_query.time.sleep", lambda _: None)

        job = QueryJob(_client_with_http(http), "job-1", QueryStatus.PENDING)

        with pytest.raises(SpiceAIError, match="Timed out"):
            job.wait(timeout=5)


class TestQueryJobResults:
    def test_single_chunk_success(self, monkeypatch) -> None:
        http = MagicMock()
        http.send_request_raw.side_effect = [
            _response(200, {"status": "SUCCEEDED"}),
            _response(
                200,
                {
                    "chunk_index": 0,
                    "row_offset": 0,
                    "row_count": 2,
                    "data_array": [{"id": 1}, {"id": 2}],
                },
            ),
        ]
        monkeypatch.setattr("spicepy._async_query.time.sleep", lambda _: None)

        job = QueryJob(_client_with_http(http), "job-1", QueryStatus.PENDING)
        result = job.results()

        assert result.row_count == 2
        assert list(result) == [{"id": 1}, {"id": 2}]

    def test_multi_chunk_pagination_concatenates_all_chunks(self, monkeypatch) -> None:
        """Regression coverage for the exact gap spice-rs's own tests never
        exercised: following next_chunk_index across more than one chunk."""
        http = MagicMock()
        http.send_request_raw.side_effect = [
            _response(200, {"status": "SUCCEEDED"}),  # wait()
            _response(
                200,
                {
                    "chunk_index": 0,
                    "row_count": 2,
                    "next_chunk_index": 1,
                    "data_array": [{"id": 1}, {"id": 2}],
                },
            ),
            _response(
                200,
                {
                    "chunk_index": 1,
                    "row_count": 2,
                    "next_chunk_index": 2,
                    "data_array": [{"id": 3}, {"id": 4}],
                },
            ),
            _response(
                200,
                {
                    "chunk_index": 2,
                    "row_count": 1,
                    "data_array": [{"id": 5}],
                },
            ),
        ]
        monkeypatch.setattr("spicepy._async_query.time.sleep", lambda _: None)

        job = QueryJob(_client_with_http(http), "job-1", QueryStatus.PENDING)
        result = job.results()

        assert result.row_count == 5
        assert [row["id"] for row in result] == [1, 2, 3, 4, 5]
        # wait() status poll + 3 chunk fetches
        assert http.send_request_raw.call_count == 4

    def test_empty_result(self, monkeypatch) -> None:
        http = MagicMock()
        http.send_request_raw.side_effect = [
            _response(200, {"status": "SUCCEEDED"}),
            _response(200, {"chunk_index": 0, "row_count": 0, "data_array": []}),
        ]
        monkeypatch.setattr("spicepy._async_query.time.sleep", lambda _: None)

        job = QueryJob(_client_with_http(http), "job-1", QueryStatus.PENDING)
        result = job.results()

        assert result.row_count == 0
        assert list(result) == []

    def test_failed_job_raises_with_error_message(self, monkeypatch) -> None:
        http = MagicMock()
        http.send_request_raw.side_effect = [
            _response(200, {"status": "FAILED"}),
            _response(
                200,
                {
                    "status": "FAILED",
                    "error": {
                        "error_code": "EXECUTION_FAILED",
                        "message": "table not found",
                    },
                },
            ),
        ]
        monkeypatch.setattr("spicepy._async_query.time.sleep", lambda _: None)

        job = QueryJob(_client_with_http(http), "job-1", QueryStatus.PENDING)

        with pytest.raises(SpiceAIError, match="table not found"):
            job.results()


class TestQueryJobCancel:
    def test_updates_status(self) -> None:
        http = MagicMock()
        http.send_request_raw.return_value = _response(
            200, {"query_id": "job-1", "cancelled": True, "status": "CANCELLED"}
        )

        job = QueryJob(_client_with_http(http), "job-1", QueryStatus.RUNNING)
        job.cancel()

        http.send_request_raw.assert_called_once_with(
            "POST", "/v1/queries/job-1/cancel"
        )

    def test_already_terminal_is_not_an_error(self) -> None:
        http = MagicMock()
        http.send_request_raw.return_value = _response(409)

        job = QueryJob(_client_with_http(http), "job-1", QueryStatus.SUCCEEDED)
        job.cancel()  # must not raise

    def test_not_found_raises(self) -> None:
        http = MagicMock()
        http.send_request_raw.return_value = _response(404, {"error": "not found"})

        job = QueryJob(_client_with_http(http), "job-1", QueryStatus.RUNNING)
        with pytest.raises(SpiceAIError, match="not found"):
            job.cancel()


class TestListQueries:
    def test_returns_summaries(self) -> None:
        http = MagicMock()
        http.send_request_raw.return_value = _response(
            200,
            {
                "queries": [
                    {
                        "query_id": "job-1",
                        "status": "SUCCEEDED",
                        "sql_preview": "SELECT 1",
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ],
                "total_count": 1,
            },
        )

        result = _client_with_http(http).list_queries()

        assert result.total_count == 1
        assert next(iter(result)).query_id == "job-1"
