"""Unit tests for spicepy._nsql and Client.nsql."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from spicepy import NsqlResult
from spicepy._nsql import (
    NSQL_JSON_MEDIA_TYPE,
    NSQL_PATH,
    NSQL_SQL_MEDIA_TYPE,
    build_nsql_body,
)
from spicepy.error import SpiceAIError


@pytest.mark.unit
class TestBuildNsqlBody:
    """Test request body construction."""

    def test_query_only(self) -> None:
        """Only the query is sent when nothing else is supplied."""
        assert build_nsql_body("how many orders") == {"query": "how many orders"}

    def test_all_options(self) -> None:
        """Every supplied option maps onto its wire field."""
        body = build_nsql_body(
            "top 5 customers by revenue",
            model="nsql-model",
            datasets=["sales"],
            sample_data_enabled=True,
            prompt_cache_key="sales-dashboard",
        )
        assert body == {
            "query": "top 5 customers by revenue",
            "model": "nsql-model",
            "datasets": ["sales"],
            "sample_data_enabled": True,
            "prompt_cache_key": "sales-dashboard",
        }

    def test_omits_unset_options(self) -> None:
        """Unset options are omitted, not sent as null, so runtime defaults apply."""
        body = build_nsql_body("how many orders", model="nsql-model")
        assert body == {"query": "how many orders", "model": "nsql-model"}
        assert "datasets" not in body
        assert "sample_data_enabled" not in body

    def test_explicit_false_sampling_is_sent(self) -> None:
        """Passing False explicitly is distinct from omitting the field."""
        body = build_nsql_body("how many orders", sample_data_enabled=False)
        assert body["sample_data_enabled"] is False

    @pytest.mark.parametrize("query", ["", "   "])
    def test_rejects_empty_query(self, query: str) -> None:
        """Empty or whitespace-only queries are rejected before the request."""
        with pytest.raises(ValueError, match="non-empty"):
            build_nsql_body(query)

    def test_rejects_empty_datasets(self) -> None:
        """An empty dataset list is meaningless as a sampling hint."""
        with pytest.raises(ValueError, match="at least one dataset"):
            build_nsql_body("how many orders", datasets=[])


@pytest.mark.unit
class TestNsqlResult:
    """Test response parsing."""

    def test_full_response(self) -> None:
        """The runtime's envelope maps onto NsqlResult."""
        result = NsqlResult.from_json(
            {
                "row_count": 2,
                "schema": {
                    "fields": [
                        {"name": "customer_id", "data_type": "Utf8", "nullable": False},
                        {
                            "name": "ts",
                            "data_type": {"Timestamp": ["Nanosecond", None]},
                            "nullable": True,
                        },
                    ]
                },
                "data": [
                    {"customer_id": "12345", "ts": 1724716542},
                    {"customer_id": "67890", "ts": 1724716543},
                ],
                "sql": "SELECT customer_id, ts FROM sales LIMIT 2",
            }
        )

        assert result.sql == "SELECT customer_id, ts FROM sales LIMIT 2"
        assert result.row_count == 2
        assert len(result) == 2
        assert result.data[0]["customer_id"] == "12345"

        assert [f.name for f in result.schema] == ["customer_id", "ts"]
        # A simple Arrow type arrives as a string, a parameterized one as a
        # dict, so data_type is left as the runtime encoded it.
        assert result.schema[0].data_type == "Utf8"
        assert result.schema[1].data_type == {"Timestamp": ["Nanosecond", None]}
        assert result.schema[1].nullable is True

    def test_empty_result_set(self) -> None:
        """The runtime sends schema as {} when the query returned no rows."""
        result = NsqlResult.from_json(
            {
                "row_count": 0,
                "schema": {},
                "data": [],
                "sql": "SELECT 1 WHERE false",
            }
        )

        assert len(result) == 0
        assert result.schema == []
        assert result.sql == "SELECT 1 WHERE false"

    def test_row_count_falls_back_to_data_length(self) -> None:
        """A response without row_count still reports how many rows arrived."""
        result = NsqlResult.from_json({"data": [{"a": 1}], "sql": "SELECT 1"})
        assert result.row_count == 1

    def test_iterates_rows(self) -> None:
        """Iterating yields the rows, so `for row in client.nsql(...)` reads well."""
        result = NsqlResult.from_json(
            {"data": [{"a": 1}, {"a": 2}], "sql": "SELECT a FROM t"}
        )
        assert list(result) == [{"a": 1}, {"a": 2}]


@pytest.mark.unit
class TestClientNsql:
    """Test Client.nsql wiring."""

    @staticmethod
    def _client(response: dict | str) -> MagicMock:
        from spicepy import Client

        client = MagicMock(spec=Client)
        client.http = MagicMock()
        client.http.post_json.return_value = response
        client.http.post_text.return_value = response
        client.nsql = Client.nsql.__get__(client, Client)
        client.nsql_generate_sql = Client.nsql_generate_sql.__get__(client, Client)
        return client

    def test_requests_the_nsql_media_type(self) -> None:
        """Without this media type the runtime drops the generated SQL."""
        client = self._client({"row_count": 0, "schema": {}, "data": [], "sql": ""})

        client.nsql("how many orders", datasets=["sales"])

        client.http.post_json.assert_called_once_with(
            NSQL_PATH,
            {"query": "how many orders", "datasets": ["sales"]},
            NSQL_JSON_MEDIA_TYPE,
        )

    def test_returns_parsed_result(self) -> None:
        """The response body is parsed into an NsqlResult."""
        client = self._client(
            {
                "row_count": 1,
                "schema": {"fields": [{"name": "n", "data_type": "Int64"}]},
                "data": [{"n": 7}],
                "sql": "SELECT count(*) AS n FROM orders",
            }
        )

        result = client.nsql("how many orders")

        assert isinstance(result, NsqlResult)
        assert result.sql == "SELECT count(*) AS n FROM orders"
        assert result.data == [{"n": 7}]

    def test_generate_sql_requests_the_sql_media_type(self) -> None:
        """SQL-only generation asks for application/sql and returns the text."""
        client = self._client("SELECT count(*) FROM orders")

        sql = client.nsql_generate_sql("how many orders")

        assert sql == "SELECT count(*) FROM orders"
        client.http.post_text.assert_called_once_with(
            NSQL_PATH,
            {"query": "how many orders"},
            NSQL_SQL_MEDIA_TYPE,
        )

    def test_validates_before_requesting(self) -> None:
        """Invalid arguments raise before any request is made."""
        client = self._client({"row_count": 0, "schema": {}, "data": [], "sql": ""})

        with pytest.raises(ValueError):
            client.nsql("")
        with pytest.raises(ValueError):
            client.nsql_generate_sql("   ")

        client.http.post_json.assert_not_called()
        client.http.post_text.assert_not_called()

    def test_propagates_runtime_error(self) -> None:
        """A missing or ambiguous model surfaces as SpiceAIError."""
        client = self._client({})
        client.http.post_json.side_effect = SpiceAIError(
            "/v1/nsql failed with status 400: No model specified and no compatible "
            "LLM model is configured."
        )

        with pytest.raises(SpiceAIError, match="No model specified"):
            client.nsql("how many orders")
