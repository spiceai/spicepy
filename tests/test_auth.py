"""Unit tests for API key auth mode selection, user agent, and per-call timeouts."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from pyarrow._flight import FlightTimedOutError, FlightUnauthenticatedError
import pytest

from spicepy import config
from spicepy._client import (
    DEFAULT_QUERY_TIMEOUT_SECS,
    _ADBCClient,
    _cloud_app_id,
    _is_cloud_address,
    _SpiceFlight,
    _use_bearer_auth,
)

pytestmark = pytest.mark.unit

CLOUD_URL = "grpc+tls://us-east-1-prod-aws-flight.spiceai.io"
LOCAL_URL = "grpc://localhost:50051"


@pytest.mark.parametrize(
    ("key", "app_id"),
    [
        ("ro-key", None),
        ("app|secret", "app"),
        ("|secret", None),
        ("app|", None),
        ("a|b|c", None),
        ("", None),
        (None, None),
    ],
)
def test_cloud_app_id(key: str | None, app_id: str | None) -> None:
    assert _cloud_app_id(key) == app_id


@pytest.mark.parametrize(
    ("url", "is_cloud"),
    [
        (CLOUD_URL, True),
        ("grpc+tls://flight.spiceai.io", True),
        ("flight.spiceai.io:443", True),
        ("grpc+tls://FLIGHT.SPICEAI.IO.:443", True),
        ("grpc+tls://spiceai.io", True),
        (LOCAL_URL, False),
        ("grpc://127.0.0.1:50051", False),
        ("grpc+tls://spiceai.io.example.com:443", False),
        ("grpc+tls://notspiceai.io", False),
        ("grpc+tls://my-runtime.internal:443", False),
        ("", False),
        (None, False),
    ],
)
def test_is_cloud_address(url: str | None, is_cloud: bool) -> None:
    assert _is_cloud_address(url) is is_cloud


def test_flight_url_override_to_oss_still_uses_bearer() -> None:
    """SPICE_FLIGHT_URL pointing at an OSS runtime must not make it Cloud."""
    with patch.object(config, "DEFAULT_FLIGHT_URL", LOCAL_URL):
        assert not _is_cloud_address(LOCAL_URL)
        assert _use_bearer_auth("app|local-secret", LOCAL_URL)
        db_kwargs = _adbc_db_kwargs(LOCAL_URL, "app|local-secret")
        assert (
            db_kwargs["adbc.flight.sql.authorization_header"]
            == "Bearer app|local-secret"
        )
        assert "password" not in db_kwargs


@pytest.mark.parametrize(
    ("key", "url", "bearer"),
    [
        ("ro-key", LOCAL_URL, True),
        ("app|ro-key", LOCAL_URL, True),
        ("ro-key", CLOUD_URL, True),
        ("app|secret", CLOUD_URL, False),
        ("", LOCAL_URL, False),
        (None, CLOUD_URL, False),
    ],
)
def test_use_bearer_auth(key: str | None, url: str, bearer: bool) -> None:
    assert _use_bearer_auth(key, url) is bearer


# ============== ADBC ==============


def _adbc_db_kwargs(uri: str, api_key: str | None) -> dict[str, str]:
    with (
        patch("spicepy._client.adbc_driver_flightsql") as mock_flightsql,
        patch("spicepy._client.adbc_driver_manager") as mock_manager,
        patch("spicepy._client.ADBC_AVAILABLE", True),
    ):
        mock_manager.DatabaseOptions.USERNAME.value = "username"
        mock_manager.DatabaseOptions.PASSWORD.value = "password"
        _ADBCClient(uri, api_key=api_key, user_agent="my-app/1.0")
        return mock_flightsql.connect.call_args.kwargs["db_kwargs"]


def test_adbc_plain_key_uses_bearer_header() -> None:
    db_kwargs = _adbc_db_kwargs(LOCAL_URL, "ro-key")
    assert db_kwargs["adbc.flight.sql.authorization_header"] == "Bearer ro-key"
    assert "username" not in db_kwargs
    assert "password" not in db_kwargs
    assert db_kwargs["adbc.flight.sql.rpc.call_header.user-agent"].startswith(
        "my-app/1.0 spicepy/"
    )


def test_adbc_app_key_to_local_runtime_uses_bearer_header() -> None:
    db_kwargs = _adbc_db_kwargs(LOCAL_URL, "app|ro-key")
    assert db_kwargs["adbc.flight.sql.authorization_header"] == "Bearer app|ro-key"
    assert "password" not in db_kwargs


def test_adbc_cloud_key_to_cloud_keeps_basic() -> None:
    db_kwargs = _adbc_db_kwargs(CLOUD_URL, "app|secret")
    assert db_kwargs["username"] == ""
    assert db_kwargs["password"] == "app|secret"  # noqa: S105
    assert "adbc.flight.sql.authorization_header" not in db_kwargs


def test_adbc_no_key_sends_no_credentials() -> None:
    db_kwargs = _adbc_db_kwargs(LOCAL_URL, "")
    assert "adbc.flight.sql.authorization_header" not in db_kwargs
    assert "password" not in db_kwargs


# ============== Flight ==============


@pytest.fixture(name="mock_client")
def mock_client_fixture():
    with patch("spicepy._client.flight.connect") as connect:
        client = MagicMock()
        client.authenticate_basic_token.return_value = (b"authorization", b"Bearer s")
        info = MagicMock()
        info.endpoints = [MagicMock()]
        client.get_flight_info.return_value = info
        connect.return_value = client
        yield client


def _header(spice_flight: _SpiceFlight, name: bytes) -> bytes | None:
    return dict(spice_flight.headers).get(name)


def test_flight_plain_key_sends_bearer_without_handshake(mock_client) -> None:
    sf = _SpiceFlight(LOCAL_URL, "ro-key", b"cert", user_agent="my-app/1.0")
    mock_client.authenticate_basic_token.assert_not_called()
    assert _header(sf, b"authorization") == b"Bearer ro-key"
    assert _header(sf, b"user-agent").startswith(b"my-app/1.0 spicepy/")


def test_flight_cloud_key_uses_basic_handshake(mock_client) -> None:
    sf = _SpiceFlight(CLOUD_URL, "app|secret", b"cert")
    mock_client.authenticate_basic_token.assert_called_once()
    args = mock_client.authenticate_basic_token.call_args.args
    assert args[:2] == ("", "app|secret")
    # The handshake is bounded and carries the user agent.
    assert args[2].timeout == DEFAULT_QUERY_TIMEOUT_SECS
    assert _header(sf, b"authorization") == b"Bearer s"


def test_flight_reauth_keeps_custom_user_agent(mock_client) -> None:
    sf = _SpiceFlight(CLOUD_URL, "app|secret", b"cert", user_agent="my-app/1.0")
    sf._authenticate()
    assert mock_client.authenticate_basic_token.call_count == 2
    assert _header(sf, b"user-agent").startswith(b"my-app/1.0 spicepy/")


def test_flight_no_key_reauth_keeps_custom_user_agent(mock_client) -> None:
    sf = _SpiceFlight(LOCAL_URL, "", b"cert", user_agent="my-app/1.0")
    sf._authenticate()
    assert list(sf.headers) == [_SpiceFlight._user_agent("my-app/1.0")]


def test_flight_bearer_rejection_is_not_retried(mock_client) -> None:
    sf = _SpiceFlight(LOCAL_URL, "wrong-key", b"cert")
    mock_client.get_flight_info.side_effect = FlightUnauthenticatedError("nope")
    with pytest.raises(FlightUnauthenticatedError):
        sf.query("SELECT 1")
    assert mock_client.get_flight_info.call_count == 1
    mock_client.authenticate_basic_token.assert_not_called()


def test_flight_cloud_session_renewed_on_get_flight_info(mock_client) -> None:
    sf = _SpiceFlight(CLOUD_URL, "app|secret", b"cert")
    info = mock_client.get_flight_info.return_value
    mock_client.get_flight_info.side_effect = [FlightUnauthenticatedError("x"), info]
    with patch.object(sf, "_threaded_flight_do_get", return_value="reader"):
        assert sf.query("SELECT 1") == "reader"
    assert mock_client.authenticate_basic_token.call_count == 2


def test_flight_timeout_applies_to_one_call_only(mock_client) -> None:
    sf = _SpiceFlight(LOCAL_URL, "ro-key", b"cert")
    seen: list[float] = []

    def do_get(_ticket, options):
        seen.append(options.timeout)
        return "reader"

    with patch.object(sf, "_threaded_flight_do_get", side_effect=do_get):
        sf.query("SELECT 1", timeout=1)
        sf.query("SELECT 1")
        sf.query("SELECT 1", timeout=5)
        sf.query("SELECT 1")

    assert seen == [1, DEFAULT_QUERY_TIMEOUT_SECS, 5, DEFAULT_QUERY_TIMEOUT_SECS]
    info_timeouts = [
        c.args[1].timeout for c in mock_client.get_flight_info.call_args_list
    ]
    assert info_timeouts == pytest.approx(seen, abs=1)
    assert sf._flight_options.timeout == DEFAULT_QUERY_TIMEOUT_SECS


def test_flight_timeout_rejects_bool(mock_client) -> None:
    sf = _SpiceFlight(LOCAL_URL, "", b"cert")
    with pytest.raises(ValueError, match="positive integer"):
        sf.query("SELECT 1", timeout=True)


def test_flight_session_renewal_is_bounded_by_query_timeout(mock_client) -> None:
    """Renewing an expired Cloud session mid-query uses the remaining deadline."""
    sf = _SpiceFlight(CLOUD_URL, "app|secret", b"cert")
    mock_client.get_flight_info.side_effect = FlightUnauthenticatedError("expired")
    renew_timeouts: list[float] = []

    def slow_renewal(_user, _key, options):
        renew_timeouts.append(options.timeout)
        raise FlightTimedOutError("handshake deadline exceeded")

    mock_client.authenticate_basic_token.side_effect = slow_renewal
    with pytest.raises(TimeoutError, match="after 1 seconds"):
        sf.query("SELECT 1", timeout=1)
    assert len(renew_timeouts) == 1
    assert 0 < renew_timeouts[0] <= 1


def test_flight_query_past_deadline_is_not_retried(mock_client) -> None:
    sf = _SpiceFlight(CLOUD_URL, "app|secret", b"cert")
    calls = mock_client.authenticate_basic_token.call_count

    def expire(*_args):
        time.sleep(1.05)
        raise FlightUnauthenticatedError("expired")

    mock_client.get_flight_info.side_effect = expire
    with pytest.raises(TimeoutError):
        sf.query("SELECT 1", timeout=1)
    assert mock_client.authenticate_basic_token.call_count == calls
