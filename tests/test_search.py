"""Unit tests for spicepy._search and Client.search."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from spicepy import SearchMatch, SearchResult
from spicepy._search import SEARCH_PATH, build_search_body
from spicepy.error import SpiceAIError


@pytest.mark.unit
class TestBuildSearchBody:
    """Test request body construction."""

    def test_text_only(self) -> None:
        """Only text is sent when nothing else is supplied."""
        assert build_search_body("tokyo") == {"text": "tokyo"}

    def test_all_options(self) -> None:
        """Every supplied option maps onto its wire field."""
        body = build_search_body(
            "tokyo",
            datasets=["app_messages"],
            limit=3,
            where="user_id = 42",
            additional_columns=["timestamp"],
            keywords=["plane", "tickets"],
        )
        assert body == {
            "text": "tokyo",
            "datasets": ["app_messages"],
            "limit": 3,
            "where": "user_id = 42",
            "additional_columns": ["timestamp"],
            "keywords": ["plane", "tickets"],
        }

    def test_omits_unset_options(self) -> None:
        """Unset options are omitted, not sent as null, so runtime defaults apply."""
        body = build_search_body("tokyo", limit=5)
        assert body == {"text": "tokyo", "limit": 5}
        assert "datasets" not in body
        assert "where" not in body

    def test_empty_additional_columns_is_sent(self) -> None:
        """An explicitly empty list is distinct from omitting the field."""
        body = build_search_body("tokyo", additional_columns=[])
        assert body["additional_columns"] == []

    @pytest.mark.parametrize("text", ["", "   "])
    def test_rejects_empty_text(self, text: str) -> None:
        """Empty or whitespace-only text is rejected before the request."""
        with pytest.raises(ValueError, match="non-empty"):
            build_search_body(text)

    def test_rejects_empty_datasets(self) -> None:
        """An empty dataset list would be a 400; catch it locally."""
        with pytest.raises(ValueError, match="at least one dataset"):
            build_search_body("tokyo", datasets=[])

    @pytest.mark.parametrize("limit", [0, -1])
    def test_rejects_non_positive_limit(self, limit: int) -> None:
        """A limit below 1 would be a 400; catch it locally."""
        with pytest.raises(ValueError, match="greater than 0"):
            build_search_body("tokyo", limit=limit)


@pytest.mark.unit
class TestSearchResultParsing:
    """Test parsing of the runtime's response body."""

    def test_full_match(self) -> None:
        """A fully populated match maps onto SearchMatch."""
        result = SearchResult.from_json(
            {
                "results": [
                    {
                        "matches": {"message": ["I booked us some tickets"]},
                        "dataset": "app_messages",
                        "primary_key": {"id": "6fd5a215"},
                        "data": {"timestamp": 1724716542},
                        "metadata": {"chunk": 2},
                        "_score": 0.914321,
                    }
                ],
                "duration_ms": 42,
            }
        )

        assert result.duration_ms == 42
        assert len(result) == 1
        match = result.results[0]
        assert match.dataset == "app_messages"
        assert match.score == pytest.approx(0.914321)
        assert match.matches == {"message": ["I booked us some tickets"]}
        assert match.primary_key == {"id": "6fd5a215"}
        assert match.data == {"timestamp": 1724716542}
        assert match.metadata == {"chunk": 2}

    def test_omitted_fields_default_to_empty(self) -> None:
        """The runtime omits data, primary_key, and metadata when empty."""
        match = SearchMatch.from_json(
            {"matches": {"message": ["hello"]}, "dataset": "d", "_score": 0.5}
        )
        assert match.data == {}
        assert match.primary_key == {}
        assert match.metadata == {}

    def test_multiple_values_per_column(self) -> None:
        """A column may contribute more than one chunk to a single match."""
        match = SearchMatch.from_json(
            {"matches": {"body": ["first chunk", "second chunk"]}, "_score": 0.1}
        )
        assert match.matches["body"] == ["first chunk", "second chunk"]

    def test_no_results(self) -> None:
        """An empty result set parses to an empty, falsy-length result."""
        result = SearchResult.from_json({"results": [], "duration_ms": 3})
        assert len(result) == 0
        assert list(result) == []

    def test_iterates_matches(self) -> None:
        """Iterating a SearchResult yields its matches."""
        result = SearchResult.from_json(
            {
                "results": [
                    {"matches": {}, "dataset": "a", "_score": 0.9},
                    {"matches": {}, "dataset": "b", "_score": 0.8},
                ],
                "duration_ms": 1,
            }
        )
        assert [m.dataset for m in result] == ["a", "b"]


@pytest.mark.unit
class TestClientSearch:
    """Test Client.search wiring."""

    @staticmethod
    def _client(response: dict) -> MagicMock:
        from spicepy import Client

        client = MagicMock(spec=Client)
        client.http = MagicMock()
        client.http.post_json.return_value = response
        client.search = Client.search.__get__(client, Client)
        return client

    def test_posts_to_search_endpoint(self) -> None:
        """The built body is posted to /v1/search."""
        client = self._client({"results": [], "duration_ms": 0})

        client.search("tokyo", datasets=["app_messages"], limit=3)

        client.http.post_json.assert_called_once_with(
            SEARCH_PATH,
            {"text": "tokyo", "datasets": ["app_messages"], "limit": 3},
        )

    def test_returns_parsed_result(self) -> None:
        """The response body is parsed into a SearchResult."""
        client = self._client(
            {
                "results": [
                    {"matches": {"m": ["hit"]}, "dataset": "d", "_score": 0.7}
                ],
                "duration_ms": 12,
            }
        )

        result = client.search("tokyo")

        assert isinstance(result, SearchResult)
        assert result.duration_ms == 12
        assert result.results[0].matches == {"m": ["hit"]}

    def test_validates_before_requesting(self) -> None:
        """Invalid arguments raise before any request is made."""
        client = self._client({"results": [], "duration_ms": 0})

        with pytest.raises(ValueError):
            client.search("")

        client.http.post_json.assert_not_called()

    def test_propagates_runtime_error(self) -> None:
        """A runtime failure surfaces as SpiceAIError."""
        client = self._client({})
        client.http.post_json.side_effect = SpiceAIError(
            "/v1/search failed with status 400: No data sources provided"
        )

        with pytest.raises(SpiceAIError, match="No data sources provided"):
            client.search("tokyo")
