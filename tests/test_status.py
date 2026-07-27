"""Unit tests for spicepy._status and the Client runtime status methods."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from spicepy._status import ComponentStatus, ConnectionDetails
from spicepy.error import SpiceAIError

pytestmark = pytest.mark.unit


class TestComponentStatus:
    """Test the ComponentStatus enum."""

    @pytest.mark.parametrize(
        "value",
        [
            "Initializing",
            "Ready",
            "Disabled",
            "Error",
            "Refreshing",
            "ShuttingDown",
            "NotLoaded",
        ],
    )
    def test_known_values_map_to_members(self, value: str) -> None:
        """Every runtime status maps onto an enum member."""
        status = ComponentStatus.from_value(value)
        assert isinstance(status, ComponentStatus)
        assert status.value == value
        assert str(status) == value

    def test_unknown_value_is_preserved(self) -> None:
        """A status this SDK version does not know is returned unchanged."""
        status = ComponentStatus.from_value("SomethingNew")
        assert status == "SomethingNew"
        assert not isinstance(status, ComponentStatus)

    def test_is_str_enum(self) -> None:
        """Members compare equal to their wire value."""
        assert ComponentStatus.READY == "Ready"


class TestConnectionDetails:
    """Test the ConnectionDetails dataclass."""

    def test_from_dict(self) -> None:
        """Parses a single /v1/status entry."""
        details = ConnectionDetails.from_dict(
            {"name": "flight", "endpoint": "127.0.0.1:50051", "status": "Ready"}
        )
        assert details.name == "flight"
        assert details.endpoint == "127.0.0.1:50051"
        assert details.status == ComponentStatus.READY
        assert details.is_ready

    def test_from_dict_not_ready(self) -> None:
        """A non-Ready component reports is_ready False."""
        details = ConnectionDetails.from_dict(
            {"name": "metrics", "endpoint": "N/A", "status": "Disabled"}
        )
        assert details.status == ComponentStatus.DISABLED
        assert not details.is_ready

    def test_from_dict_missing_fields(self) -> None:
        """Missing fields default rather than raising."""
        details = ConnectionDetails.from_dict({})
        assert details.name == ""
        assert details.endpoint == ""
        assert not details.is_ready

    def test_unknown_status_is_not_ready(self) -> None:
        """An unrecognized status is never treated as ready."""
        details = ConnectionDetails.from_dict(
            {"name": "flight", "endpoint": "x", "status": "SomethingNew"}
        )
        assert details.status == "SomethingNew"
        assert not details.is_ready


def _client_with_http(http: MagicMock):
    """Build a Client without running __init__, with a stubbed http attribute."""
    from spicepy import Client

    client = object.__new__(Client)
    client.http = http
    return client


class TestRuntimeStatus:
    """Test Client.runtime_status."""

    def test_returns_all_components(self) -> None:
        """Each entry in the response becomes a ConnectionDetails."""
        http = MagicMock()
        http.send_request.return_value = [
            {"name": "http", "endpoint": "127.0.0.1:8090", "status": "Ready"},
            {"name": "flight", "endpoint": "127.0.0.1:50051", "status": "Initializing"},
            {"name": "metrics", "endpoint": "N/A", "status": "Disabled"},
            {
                "name": "opentelemetry",
                "endpoint": "127.0.0.1:50051",
                "status": "Initializing",
            },
        ]

        components = _client_with_http(http).runtime_status()

        http.send_request.assert_called_once_with("GET", "/v1/status")
        assert [c.name for c in components] == [
            "http",
            "flight",
            "metrics",
            "opentelemetry",
        ]
        assert components[0].is_ready
        assert not components[1].is_ready
        assert components[1].status == ComponentStatus.INITIALIZING

    def test_empty_response(self) -> None:
        """An empty list is valid and yields no components."""
        http = MagicMock()
        http.send_request.return_value = []
        assert _client_with_http(http).runtime_status() == []

    def test_non_list_response_raises(self) -> None:
        """A response that is not a list is an error, not silently empty."""
        http = MagicMock()
        http.send_request.return_value = {"not": "a list"}

        with pytest.raises(SpiceAIError, match="expected a list of components"):
            _client_with_http(http).runtime_status()


class TestIsReady:
    """Test Client.is_ready."""

    def test_ready(self) -> None:
        """HTTP 200 means ready."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(status_code=200)

        assert _client_with_http(http).is_ready() is True
        http.send_request_raw.assert_called_once_with("GET", "/v1/ready")

    def test_not_ready(self) -> None:
        """HTTP 503 means not ready, and is not an error."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(status_code=503)

        assert _client_with_http(http).is_ready() is False

    @pytest.mark.parametrize("status_code", [400, 401, 404, 500])
    def test_unexpected_status_raises(self, status_code: int) -> None:
        """Any other status is a failed probe, distinct from 'not ready'."""
        http = MagicMock()
        http.send_request_raw.return_value = MagicMock(status_code=status_code)

        with pytest.raises(SpiceAIError, match="Unexpected response from /v1/ready"):
            _client_with_http(http).is_ready()
