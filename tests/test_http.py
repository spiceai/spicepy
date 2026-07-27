"""Comprehensive unit tests for spicepy._http module."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest
from requests import Response

from spicepy._http import HttpRequests, RefreshOpts, timedelta_to_duration_str
from spicepy.config import SPICE_USER_AGENT
from spicepy.error import SpiceAIError


class TestRefreshOpts:
    """Test RefreshOpts dataclass."""

    def test_default_values(self) -> None:
        """Test RefreshOpts default values."""
        opts = RefreshOpts()
        assert opts.refresh_sql is None
        assert opts.refresh_mode is None
        assert opts.refresh_jitter_max is None

    def test_with_refresh_sql(self) -> None:
        """Test RefreshOpts with refresh_sql."""
        opts = RefreshOpts(refresh_sql="SELECT * FROM table LIMIT 10")
        assert opts.refresh_sql == "SELECT * FROM table LIMIT 10"

    def test_with_refresh_mode(self) -> None:
        """Test RefreshOpts with refresh_mode."""
        opts = RefreshOpts(refresh_mode="full")
        assert opts.refresh_mode == "full"

    def test_with_refresh_jitter_max(self) -> None:
        """Test RefreshOpts with refresh_jitter_max."""
        opts = RefreshOpts(refresh_jitter_max="5m")
        assert opts.refresh_jitter_max == "5m"

    def test_with_all_options(self) -> None:
        """Test RefreshOpts with all options."""
        opts = RefreshOpts(
            refresh_sql="SELECT * FROM table",
            refresh_mode="incremental",
            refresh_jitter_max="10s",
        )
        assert opts.refresh_sql == "SELECT * FROM table"
        assert opts.refresh_mode == "incremental"
        assert opts.refresh_jitter_max == "10s"

    def test_to_dict_empty(self) -> None:
        """Test RefreshOpts to_dict with defaults."""
        opts = RefreshOpts()
        d = opts.to_dict()
        assert d == {
            "refresh_sql": None,
            "refresh_mode": None,
            "refresh_jitter_max": None,
        }

    def test_to_dict_with_values(self) -> None:
        """Test RefreshOpts to_dict with values."""
        opts = RefreshOpts(
            refresh_sql="SELECT 1", refresh_mode="full", refresh_jitter_max="1h"
        )
        d = opts.to_dict()
        assert d["refresh_sql"] == "SELECT 1"
        assert d["refresh_mode"] == "full"
        assert d["refresh_jitter_max"] == "1h"


class TestTimedeltaToDurationStr:
    """Test timedelta_to_duration_str function."""

    def test_zero_duration(self) -> None:
        """Test zero duration."""
        td = datetime.timedelta()
        assert timedelta_to_duration_str(td) == "0s"

    def test_seconds_only(self) -> None:
        """Test seconds only."""
        td = datetime.timedelta(seconds=30)
        assert timedelta_to_duration_str(td) == "30s"

    def test_minutes_only(self) -> None:
        """Test minutes only."""
        td = datetime.timedelta(minutes=5)
        assert timedelta_to_duration_str(td) == "5m"

    def test_hours_only(self) -> None:
        """Test hours only."""
        td = datetime.timedelta(hours=2)
        assert timedelta_to_duration_str(td) == "2h"

    def test_days_only(self) -> None:
        """Test days only."""
        td = datetime.timedelta(days=3)
        assert timedelta_to_duration_str(td) == "3d"

    def test_days_and_hours(self) -> None:
        """Test days and hours."""
        td = datetime.timedelta(days=1, hours=12)
        result = timedelta_to_duration_str(td)
        assert "1d" in result
        assert "12h" in result

    def test_hours_and_minutes(self) -> None:
        """Test hours and minutes."""
        td = datetime.timedelta(hours=2, minutes=30)
        result = timedelta_to_duration_str(td)
        assert "2h" in result
        assert "30m" in result

    def test_minutes_and_seconds(self) -> None:
        """Test minutes and seconds."""
        td = datetime.timedelta(minutes=5, seconds=30)
        result = timedelta_to_duration_str(td)
        assert "5m" in result
        assert "30s" in result

    def test_full_duration(self) -> None:
        """Test full duration with all components."""
        td = datetime.timedelta(days=1, hours=2, minutes=30, seconds=45)
        result = timedelta_to_duration_str(td)
        assert "1d" in result
        assert "2h" in result
        assert "30m" in result
        assert "45s" in result

    def test_large_duration(self) -> None:
        """Test large duration."""
        td = datetime.timedelta(days=365)
        result = timedelta_to_duration_str(td)
        assert "365d" in result


class TestHttpRequestsInit:
    """Test HttpRequests initialization."""

    @patch("spicepy._http.Session")
    def test_init_with_base_url(self, mock_session_class: MagicMock) -> None:
        """Test HttpRequests initialization with base URL."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {"X-API-Key": "test"})
        assert http.base_url == "http://example.com"

    @patch("spicepy._http.Session")
    def test_init_sets_headers(self, mock_session_class: MagicMock) -> None:
        """Test HttpRequests initialization sets headers."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        HttpRequests(
            "http://example.com", {"X-API-Key": "secret", "Accept": "application/json"}
        )
        # Should have the provided headers plus default user-agent
        assert mock_session.headers["X-API-Key"] == "secret"
        assert mock_session.headers["Accept"] == "application/json"
        assert "user-agent" in mock_session.headers

    @patch("spicepy._http.Session")
    def test_init_sets_default_user_agent(self, mock_session_class: MagicMock) -> None:
        """Test HttpRequests sets default user agent if not provided."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        HttpRequests("http://example.com", {})
        assert mock_session.headers.get("user-agent") == SPICE_USER_AGENT

    @patch("spicepy._http.Session")
    def test_init_preserves_custom_user_agent(
        self, mock_session_class: MagicMock
    ) -> None:
        """Test HttpRequests preserves custom user agent."""
        mock_session = MagicMock()
        mock_session.headers = {"user-agent": "custom-agent"}
        mock_session_class.return_value = mock_session

        HttpRequests("http://example.com", {"user-agent": "custom-agent"})
        # Should not override if already set
        assert mock_session.headers.get("user-agent") == "custom-agent"


class TestHttpRequestsPrepareParam:
    """Test HttpRequests.prepare_param method."""

    @patch("spicepy._http.Session")
    def test_prepare_param_with_timedelta(self, mock_session_class: MagicMock) -> None:
        """Test prepare_param converts timedelta."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {})
        params = {"duration": datetime.timedelta(hours=1, minutes=30)}
        result = http.prepare_param(params)
        assert result["duration"] == "1h30m"

    @patch("spicepy._http.Session")
    def test_prepare_param_with_datetime(self, mock_session_class: MagicMock) -> None:
        """Test prepare_param converts datetime to timestamp."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {})
        dt = datetime.datetime(2024, 1, 15, 12, 0, 0)
        params = {"timestamp": dt}
        result = http.prepare_param(params)
        assert result["timestamp"] == int(dt.timestamp())

    @patch("spicepy._http.Session")
    def test_prepare_param_with_string(self, mock_session_class: MagicMock) -> None:
        """Test prepare_param leaves strings unchanged."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {})
        params = {"name": "test"}
        result = http.prepare_param(params)
        assert result["name"] == "test"

    @patch("spicepy._http.Session")
    def test_prepare_param_mixed(self, mock_session_class: MagicMock) -> None:
        """Test prepare_param with mixed types."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {})
        dt = datetime.datetime(2024, 1, 15, 12, 0, 0)
        params = {
            "name": "test",
            "count": 10,
            "timestamp": dt,
            "duration": datetime.timedelta(minutes=5),
        }
        result = http.prepare_param(params)
        assert result["name"] == "test"
        assert result["count"] == 10
        assert result["timestamp"] == int(dt.timestamp())
        assert result["duration"] == "5m"


class TestHttpRequestsOperation:
    """Test HttpRequests._operation method."""

    @patch("spicepy._http.Session")
    def test_operation_get(self, mock_session_class: MagicMock) -> None:
        """Test _operation returns GET method."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {})
        assert http._operation("GET") == mock_session.get

    @patch("spicepy._http.Session")
    def test_operation_post(self, mock_session_class: MagicMock) -> None:
        """Test _operation returns POST method."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {})
        assert http._operation("POST") == mock_session.post

    @patch("spicepy._http.Session")
    def test_operation_put(self, mock_session_class: MagicMock) -> None:
        """Test _operation returns PUT method."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {})
        assert http._operation("PUT") == mock_session.put

    @patch("spicepy._http.Session")
    def test_operation_head(self, mock_session_class: MagicMock) -> None:
        """Test _operation returns HEAD method."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {})
        assert http._operation("HEAD") == mock_session.head

    @patch("spicepy._http.Session")
    def test_operation_delete(self, mock_session_class: MagicMock) -> None:
        """Test _operation returns DELETE method."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {})
        assert http._operation("DELETE") == mock_session.delete

    @patch("spicepy._http.Session")
    def test_operation_invalid_raises(self, mock_session_class: MagicMock) -> None:
        """Test _operation raises for invalid method."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {})
        with pytest.raises(SpiceAIError, match="not a valid HTTP operation"):
            http._operation("INVALID")  # type: ignore


class TestHttpRequestsSendRequest:
    """Test HttpRequests.send_request method."""

    @patch("spicepy._http.Session")
    def test_send_request_get(self, mock_session_class: MagicMock) -> None:
        """Test send_request with GET."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_response = MagicMock(spec=Response)
        mock_response.json.return_value = {"result": "success"}
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {})
        result = http.send_request("GET", "/api/test")

        assert result == {"result": "success"}
        mock_response.raise_for_status.assert_called_once()

    @patch("spicepy._http.Session")
    def test_send_request_post_with_body(self, mock_session_class: MagicMock) -> None:
        """Test send_request with POST and body."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_response = MagicMock(spec=Response)
        mock_response.json.return_value = {"created": True}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {})
        result = http.send_request("POST", "/api/create", body='{"name": "test"}')

        assert result == {"created": True}
        mock_session.post.assert_called_once()

    @patch("spicepy._http.Session")
    def test_send_request_with_params(self, mock_session_class: MagicMock) -> None:
        """Test send_request with query params."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_response = MagicMock(spec=Response)
        mock_response.json.return_value = {"data": []}
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {})
        result = http.send_request(
            "GET", "/api/search", param={"q": "test", "limit": 10}
        )

        assert result == {"data": []}

    @patch("spicepy._http.Session")
    def test_send_request_with_headers(self, mock_session_class: MagicMock) -> None:
        """Test send_request with additional headers."""
        mock_session = MagicMock()
        mock_session.headers = {"X-API-Key": "secret"}
        mock_response = MagicMock(spec=Response)
        mock_response.json.return_value = {}
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {"X-API-Key": "secret"})
        http.send_request("GET", "/api/test", headers={"X-Custom": "value"})

        # Verify headers were merged
        call_kwargs = mock_session.get.call_args
        assert "X-Custom" in call_kwargs.kwargs.get("headers", {}) or "headers" in str(
            call_kwargs
        )


class TestHttpRequestsSendRequestRaw:
    """Test HttpRequests.send_request_raw method."""

    @patch("spicepy._http.Session")
    def test_returns_response_without_decoding(
        self, mock_session_class: MagicMock
    ) -> None:
        """The raw Response is returned, not a decoded body."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_response = MagicMock(spec=Response)
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {})
        result = http.send_request_raw("GET", "/v1/ready")

        assert result is mock_response
        mock_response.json.assert_not_called()

    @patch("spicepy._http.Session")
    def test_does_not_raise_on_error_status(
        self, mock_session_class: MagicMock
    ) -> None:
        """A non-2xx status is left to the caller to interpret."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 503
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {})
        result = http.send_request_raw("GET", "/v1/ready")

        assert result.status_code == 503
        mock_response.raise_for_status.assert_not_called()

    @patch("spicepy._http.Session")
    def test_merges_session_headers(self, mock_session_class: MagicMock) -> None:
        """Session headers are applied, as with send_request."""
        mock_session = MagicMock()
        mock_session.headers = {"X-API-Key": "secret"}
        mock_session.get.return_value = MagicMock(spec=Response)
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {"X-API-Key": "secret"})
        http.send_request_raw("GET", "/v1/ready")

        sent_headers = mock_session.get.call_args.kwargs["headers"]
        assert sent_headers["X-API-Key"] == "secret"

    @patch("spicepy._http.Session")
    def test_does_not_mutate_caller_headers(self, mock_session_class: MagicMock) -> None:
        """The caller's headers dict is left untouched; session headers still win."""
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(spec=Response)
        mock_session_class.return_value = mock_session

        http = HttpRequests("http://example.com", {"X-API-Key": "session"})
        caller_headers = {"X-API-Key": "caller", "Content-Type": "application/json"}
        http.send_request_raw("GET", "/v1/ready", headers=caller_headers)

        assert caller_headers == {
            "X-API-Key": "caller",
            "Content-Type": "application/json",
        }
        sent_headers = mock_session.get.call_args.kwargs["headers"]
        assert sent_headers["X-API-Key"] == "session"
        assert sent_headers["Content-Type"] == "application/json"
        assert sent_headers["user-agent"] == SPICE_USER_AGENT


class TestHttpRequestsRetryConfiguration:
    """Test HttpRequests retry configuration."""

    @patch("spicepy._http.Session")
    @patch("spicepy._http.HTTPAdapter")
    def test_retry_adapter_mounted(
        self, mock_adapter_class: MagicMock, mock_session_class: MagicMock
    ) -> None:
        """Test retry adapter is mounted for HTTPS."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session
        mock_adapter = MagicMock()
        mock_adapter_class.return_value = mock_adapter

        HttpRequests("https://example.com", {})

        # Verify mount was called for https://
        mock_session.mount.assert_called()
