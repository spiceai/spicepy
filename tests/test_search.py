"""Unit tests for spicepy._search and Client.search."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from spicepy._search import (
    SearchMatch,
    SearchResponse,
    build_search_body,
    search_error_message,
)
from spicepy.error import SpiceAIError


class TestBuildSearchBody:
    """Test request body construction."""

    def test_text_only_omits_optional_fields(self) -> None:
        assert build_search_body("tickets to Tokyo") == {"text": "tickets to Tokyo"}

    def test_all_options(self) -> None:
        body = build_search_body(
            "tickets to Tokyo",
            datasets=["app_messages"],
            limit=3,
            where="city = 'Tokyo'",
            additional_columns=["timestamp"],
            keywords=["plane", "tickets"],
        )
        assert body == {
            "text": "tickets to Tokyo",
            "datasets": ["app_messages"],
            "limit": 3,
            "where": "city = 'Tokyo'",
            "additional_columns": ["timestamp"],
            "keywords": ["plane", "tickets"],
        }

    def test_empty_collections_are_sent_not_dropped(self) -> None:
        """An explicit empty list is a different request from an unset option."""
        body = build_search_body("tickets", datasets=[], keywords=[])
        assert body["datasets"] == []
        assert body["keywords"] == []

    def test_limit_zero_is_preserved(self) -> None:
        """0 is falsy but explicitly supplied, so it must survive."""
        assert build_search_body("tickets", limit=0)["limit"] == 0

    def test_empty_text_raises(self) -> None:
        with pytest.raises(SpiceAIError, match="search text is required"):
            build_search_body("")


class TestSearchMatch:
    """Test decoding the runtime's wire format."""

    def test_full_match(self) -> None:
        match = SearchMatch.from_dict(
            {
                "matches": {"message": ["I booked us some tickets"]},
                "dataset": "app_messages",
                "primary_key": {"id": "6fd5a215"},
                "data": {"timestamp": 1724716542},
                "_score": 0.914321,
            }
        )
        assert match.dataset == "app_messages"
        assert match.score == 0.914321
        assert match.matches == {"message": ["I booked us some tickets"]}
        assert match.primary_key == {"id": "6fd5a215"}
        assert match.data == {"timestamp": 1724716542}
        assert match.metadata == {}

    def test_omitted_objects_default_to_empty_dicts(self) -> None:
        """The runtime omits data/primary_key/metadata when empty."""
        match = SearchMatch.from_dict({"dataset": "app_messages", "_score": 0.5})
        assert match.primary_key == {}
        assert match.data == {}
        assert match.metadata == {}
        assert match.matches == {}
        # Readable without a guard.
        assert match.data.get("timestamp") is None

    def test_score_reads_the_underscore_prefixed_wire_field(self) -> None:
        assert SearchMatch.from_dict({"_score": 0.75}).score == 0.75
        # `score` is not the wire name and must not be picked up.
        assert SearchMatch.from_dict({"score": 0.75}).score == 0.0


class TestSearchResponse:
    """Test the response wrapper."""

    def test_from_dict(self) -> None:
        response = SearchResponse.from_dict(
            {
                "results": [
                    {"dataset": "app_messages", "_score": 0.9},
                    {"dataset": "app_messages", "_score": 0.8},
                ],
                "duration_ms": 42,
            }
        )
        assert response.duration_ms == 42
        assert len(response) == 2
        assert [m.score for m in response] == [0.9, 0.8]

    def test_empty_results(self) -> None:
        response = SearchResponse.from_dict({"results": [], "duration_ms": 1})
        assert len(response) == 0
        assert list(response) == []

    def test_missing_results_key(self) -> None:
        assert len(SearchResponse.from_dict({"duration_ms": 1})) == 0

    def test_non_dict_payload_raises(self) -> None:
        with pytest.raises(SpiceAIError, match="unexpected search response"):
            SearchResponse.from_dict("not a dict")  # type: ignore[arg-type]


class TestClientSearch:
    """Test Client.search wiring."""

    def _client(self, response: dict) -> MagicMock:
        from spicepy._client import Client

        client = MagicMock(spec=Client)
        client.http = MagicMock()
        client.http.send_request.return_value = response
        client.search = Client.search.__get__(client, Client)
        return client

    def test_posts_to_v1_search(self) -> None:
        client = self._client({"results": [], "duration_ms": 3})
        client.search("tickets to Tokyo", datasets=["app_messages"], limit=3)

        args, kwargs = client.http.send_request.call_args
        assert args[0] == "POST"
        assert args[1] == "/v1/search"
        assert kwargs["headers"] == {"Content-Type": "application/json"}

        import json

        assert json.loads(kwargs["body"]) == {
            "text": "tickets to Tokyo",
            "datasets": ["app_messages"],
            "limit": 3,
        }

    def test_returns_decoded_response(self) -> None:
        client = self._client(
            {
                "results": [{"dataset": "app_messages", "_score": 0.91}],
                "duration_ms": 42,
            }
        )
        response = client.search("tickets")

        assert isinstance(response, SearchResponse)
        assert response.duration_ms == 42
        assert response.results[0].score == 0.91

    def test_empty_text_raises_before_the_request(self) -> None:
        client = self._client({})
        with pytest.raises(SpiceAIError, match="search text is required"):
            client.search("")
        client.http.send_request.assert_not_called()

    def test_options_are_keyword_only(self) -> None:
        client = self._client({"results": [], "duration_ms": 0})
        with pytest.raises(TypeError):
            client.search("tickets", ["app_messages"])  # type: ignore[misc]

    def test_http_error_carries_the_runtime_message(self) -> None:
        """A bare '400 Client Error' does not say what to fix."""
        from requests import Response
        from requests.exceptions import HTTPError

        body = (
            b"Search cannot be run on nation because it has no embeddings"
            b" or full text search indexes."
        )
        failed = Response()
        failed.status_code = 400
        failed._content = body  # pylint: disable=protected-access

        client = self._client({})
        client.http.send_request.side_effect = HTTPError(response=failed)

        with pytest.raises(SpiceAIError, match="no embeddings or full text search"):
            client.search("tickets", datasets=["nation"])


class TestSearchErrorMessage:
    """Test the message built for a failed search."""

    def test_plain_text_body(self) -> None:
        message = search_error_message(400, "No data sources provided")
        assert "400" in message
        assert "No data sources provided" in message

    def test_json_error_body_is_unwrapped(self) -> None:
        message = search_error_message(400, '{"error": "No data sources provided"}')
        assert "No data sources provided" in message
        # The JSON envelope itself should not leak into the message.
        assert '{"error"' not in message

    def test_json_without_an_error_key_is_kept_verbatim(self) -> None:
        message = search_error_message(500, '{"detail": "boom"}')
        assert '{"detail": "boom"}' in message

    def test_empty_body(self) -> None:
        assert "(no response body)" in search_error_message(500, "")
        assert "(no response body)" in search_error_message(500, None)

    def test_missing_status_code(self) -> None:
        message = search_error_message(None, "something went wrong")
        assert "something went wrong" in message


class TestDecodeRobustness:
    """Malformed responses should fail loudly, not later."""

    def test_non_dict_match_raises(self) -> None:
        with pytest.raises(SpiceAIError, match="unexpected search match"):
            SearchMatch.from_dict("not a match")

    def test_non_list_results_raises(self) -> None:
        with pytest.raises(SpiceAIError, match="unexpected search results"):
            SearchResponse.from_dict({"results": "not a list"})

    def test_non_mapping_fields_coerce_to_empty(self) -> None:
        """A malformed field must not leave a str where a dict is documented."""
        response = SearchResponse.from_dict(
            {
                "results": [{"dataset": "a", "_score": 0.5, "data": "garbage"}],
                "duration_ms": 1,
            }
        )
        assert response.results[0].data == {}

    def test_non_integer_duration_falls_back_to_zero(self) -> None:
        response = SearchResponse.from_dict({"results": [], "duration_ms": "soon"})
        assert response.duration_ms == 0

    def test_error_page_instead_of_results(self) -> None:
        """A proxy or error page reaches this decoder as readily as a result."""
        with pytest.raises(SpiceAIError, match="unexpected search response"):
            SearchResponse.from_dict("<html>502 Bad Gateway</html>")
