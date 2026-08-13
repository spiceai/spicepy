"""Unit tests for spicepy._active_query and the Client active-query methods."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest

from spicepy._active_query import ActiveQuery
from spicepy.error import SpiceAIError

pytestmark = pytest.mark.unit


class TestActiveQuery:
    """Test the ActiveQuery dataclass."""

    def test_from_dict(self) -> None:
        """Parses a single /v1/sql/active entry."""
        query = ActiveQuery.from_dict(
            {
                "query_id": "0198f0a1-9c3d-7c4e-8a11-2b3c4d5e6f70",
                "protocol": "flight",
                "sql_preview": "SELECT * FROM taxi_trips",
                "started_at_ms": 1750000000000,
            }
        )
        assert query.query_id == "0198f0a1-9c3d-7c4e-8a11-2b3c4d5e6f70"
        assert query.protocol == "flight"
        assert query.sql_preview == "SELECT * FROM taxi_trips"
        assert query.started_at_ms == 1750000000000

    def test_from_dict_missing_fields(self) -> None:
        """Missing fields default rather than raising."""
        query = ActiveQuery.from_dict({})
        assert query.query_id == ""
        assert query.protocol == ""
        assert query.sql_preview == ""
        assert query.started_at_ms == 0

    def test_started_at_is_timezone_aware_utc(self) -> None:
        """started_at converts the epoch milliseconds to an aware UTC datetime."""
        query = ActiveQuery.from_dict({"started_at_ms": 1750000000000})
        assert query.started_at == datetime.datetime(
            2025, 6, 15, 15, 6, 40, tzinfo=datetime.UTC
        )
        assert query.started_at.tzinfo is not None


def _client_with_http(http: MagicMock):
    """Build a Client without running __init__, with a stubbed http attribute."""
    from spicepy import Client

    client = object.__new__(Client)
    client.http = http
    return client


class TestListActiveQueries:
    """Test Client.list_active_queries."""

    def test_returns_queries(self) -> None:
        """Each entry in the response becomes an ActiveQuery."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(
            status_code=200,
            **{
                "json.return_value": {
                    "queries": [
                        {
                            "query_id": "0198f0a1-9c3d-7c4e-8a11-2b3c4d5e6f70",
                            "protocol": "flight",
                            "sql_preview": "SELECT * FROM taxi_trips",
                            "started_at_ms": 1750000000000,
                        },
                        {
                            "query_id": "0198f0a1-9c3d-7c4e-8a11-2b3c4d5e6f71",
                            "protocol": "http",
                            "sql_preview": "SELECT 1",
                            "started_at_ms": 1750000000500,
                        },
                    ],
                    "total_count": 2,
                }
            },
        )

        queries = _client_with_http(http).list_active_queries()

        http.send_request_raw.assert_called_once_with("GET", "/v1/sql/active")
        assert [q.protocol for q in queries] == ["flight", "http"]
        assert queries[0].sql_preview == "SELECT * FROM taxi_trips"

    def test_no_queries_running(self) -> None:
        """An empty list is valid and yields no queries."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(
            status_code=200, **{"json.return_value": {"queries": [], "total_count": 0}}
        )
        assert _client_with_http(http).list_active_queries() == []

    def test_missing_queries_key_yields_empty(self) -> None:
        """A response without 'queries' is treated as none running."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(
            status_code=200, **{"json.return_value": {"total_count": 0}}
        )
        assert _client_with_http(http).list_active_queries() == []

    def test_forbidden_names_the_credential_problem(self) -> None:
        """403 says what to fix rather than reporting a bare status code."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(status_code=403)

        with pytest.raises(SpiceAIError, match="write access"):
            _client_with_http(http).list_active_queries()

    def test_unexpected_status_raises(self) -> None:
        """Any other non-200 is an error naming the status."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(status_code=500)

        with pytest.raises(SpiceAIError, match="HTTP 500"):
            _client_with_http(http).list_active_queries()

    def test_non_object_response_raises(self) -> None:
        """A response that is not an object is an error, not silently empty."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(
            status_code=200, **{"json.return_value": ["not", "an", "object"]}
        )

        with pytest.raises(SpiceAIError, match="expected an object"):
            _client_with_http(http).list_active_queries()

    def test_non_list_queries_raises(self) -> None:
        """A 'queries' value that is not a list is a clear error."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(
            status_code=200, **{"json.return_value": {"queries": {"not": "a list"}}}
        )

        with pytest.raises(SpiceAIError, match="'queries' to be a list"):
            _client_with_http(http).list_active_queries()

    @pytest.mark.parametrize("entry", ["flight", 3, None, ["flight"]])
    def test_non_object_entry_raises(self, entry: object) -> None:
        """A list entry that is not an object is a clear error, not AttributeError."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(
            status_code=200,
            **{
                "json.return_value": {
                    "queries": [{"query_id": "a"}, entry],
                    "total_count": 2,
                }
            },
        )

        with pytest.raises(SpiceAIError, match="expected query 1 to be an object"):
            _client_with_http(http).list_active_queries()


class TestCancelActiveQuery:
    """Test Client.cancel_active_query."""

    query_id = "0198f0a1-9c3d-7c4e-8a11-2b3c4d5e6f70"

    def test_cancels(self) -> None:
        """200 returns None and hits the right path."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(status_code=200)

        assert _client_with_http(http).cancel_active_query(self.query_id) is None
        http.send_request_raw.assert_called_once_with(
            "POST", f"/v1/sql/{self.query_id}/cancel"
        )

    def test_empty_query_id_is_rejected_without_a_request(self) -> None:
        """An empty id fails locally rather than calling a malformed URL."""
        http = MagicMock()

        with pytest.raises(SpiceAIError, match="list_active_queries"):
            _client_with_http(http).cancel_active_query("")

        http.send_request_raw.assert_not_called()

    def test_invalid_uuid_points_at_list_active_queries(self) -> None:
        """A rejected id tells the caller where a valid one comes from."""
        http = MagicMock()

        with pytest.raises(SpiceAIError, match="list_active_queries"):
            _client_with_http(http).cancel_active_query("not-a-uuid")

    def test_a_rejected_uuid_from_the_runtime_is_reported(self) -> None:
        """400 on a well-formed id is still the runtime's answer to report."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(status_code=400)

        with pytest.raises(SpiceAIError, match="not a valid UUID"):
            _client_with_http(http).cancel_active_query(self.query_id)

    def test_forbidden_names_the_credential_problem(self) -> None:
        """403 says what to fix rather than reporting a bare status code."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(status_code=403)

        with pytest.raises(SpiceAIError, match="write access"):
            _client_with_http(http).cancel_active_query(self.query_id)

    @pytest.mark.parametrize(
        "query_id",
        [".", "..", "../queries/escape", "not-a-uuid", "0198f0a1-9c3d-7c4e-8a11"],
    )
    def test_an_id_that_could_reroute_the_request_is_rejected_locally(
        self, query_id: str
    ) -> None:
        """A non-UUID id never becomes a request path.

        "." and ".." survive quoting — they are unreserved — and requests then
        resolves them away, so ".." would turn the cancel POST into one at
        /v1/cancel.
        """
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(status_code=200)

        with pytest.raises(SpiceAIError, match="not a valid UUID"):
            _client_with_http(http).cancel_active_query(query_id)

        http.send_request_raw.assert_not_called()

    def test_not_found_explains_both_causes(self) -> None:
        """404 covers both a finished query and one outside the caller's scope."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(status_code=404)

        with pytest.raises(SpiceAIError, match="already finished"):
            _client_with_http(http).cancel_active_query(self.query_id)

    def test_unexpected_status_raises(self) -> None:
        """Any other status is an error naming the status."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(status_code=500)

        with pytest.raises(SpiceAIError, match="HTTP 500"):
            _client_with_http(http).cancel_active_query(self.query_id)
