"""``tls_root_cert`` must reach every transport, not just plain Flight queries.

Flight ``sql()`` always honored it. HTTP calls (``is_ready``, ``runtime_status``,
``refresh_dataset``, ``search``, async queries, nsql) and parameterized (ADBC)
queries ignored it, so a runtime behind a private CA failed certificate
verification on those calls, and each HTTP failure was retried for about a
minute before surfacing as a raw ``requests`` exception.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from urllib3.exceptions import MaxRetryError
from urllib3.exceptions import SSLError as Urllib3SSLError

from spicepy import Client
from spicepy._client import ADBC_AVAILABLE, _ADBCClient
from spicepy._http import HttpRequests
from spicepy.error import SpiceAIError, SpiceTLSError

PEM = b"-----BEGIN CERTIFICATE-----\nMIIBfake\n-----END CERTIFICATE-----\n"


@pytest.fixture(name="ca_file")
def ca_file_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "ca.pem"
    path.write_bytes(PEM)
    return path


def _ok_response() -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = b"[]"  # pylint: disable=protected-access
    return response


# ============== HTTP: verify against the configured CA ==============


@pytest.mark.parametrize("send", ["send_request", "send_request_raw", "post_raw"])
def test_http_verifies_with_configured_root_cert(send: str, ca_file: Path) -> None:
    http = HttpRequests("https://spice:8090", {}, tls_root_cert=ca_file)
    with patch.object(http.session, "request", return_value=_ok_response()) as req:
        if send == "post_raw":
            http.post_raw("/v1/sql", {})
        else:
            getattr(http, send)("GET", "/v1/status")
    assert req.call_args.kwargs["verify"] == str(ca_file)


def test_http_defaults_to_system_verification() -> None:
    http = HttpRequests("https://spice:8090", {})
    with patch.object(http.session, "request", return_value=_ok_response()) as req:
        http.send_request("GET", "/v1/status")
    assert req.call_args.kwargs["verify"] is True


def test_client_passes_root_cert_to_http(ca_file: Path) -> None:
    with patch("spicepy._client._SpiceFlight"):
        client = Client(http_url="https://spice:8090", tls_root_cert=ca_file)
    with patch.object(
        client.http.session, "request", return_value=_ok_response()
    ) as req:
        client.runtime_status()
    assert req.call_args.kwargs["verify"] == str(ca_file)


# ============== HTTP: certificate failures are final ==============


def test_certificate_failure_is_not_retried() -> None:
    retry = (
        HttpRequests("https://spice:8090", {})
        .session.get_adapter("https://spice:8090")
        .max_retries
    )
    with pytest.raises(MaxRetryError):
        retry.increment(
            method="GET",
            url="/v1/ready",
            error=Urllib3SSLError("certificate verify failed"),
        )


def test_transient_errors_still_retry() -> None:
    retry = (
        HttpRequests("https://spice:8090", {})
        .session.get_adapter("https://spice:8090")
        .max_retries
    )
    response = MagicMock(status=503)
    response.get_redirect_location.return_value = None
    response.headers = {}
    assert retry.increment(method="GET", url="/v1/ready", response=response)


def test_certificate_failure_raises_spice_tls_error() -> None:
    http = HttpRequests("https://spice:8090", {})
    failure = requests.exceptions.SSLError(
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
        "self-signed certificate in certificate chain"
    )
    with patch.object(http.session, "request", side_effect=failure):
        with pytest.raises(SpiceTLSError) as raised:
            http.send_request_raw("GET", "/v1/ready")

    error = raised.value
    # One exception type for SDK callers, and still the requests type for code
    # that already catches that.
    assert isinstance(error, SpiceAIError)
    assert isinstance(error, requests.exceptions.SSLError)
    assert "https://spice:8090/v1/ready" in str(error)
    assert "certificate verify failed" in str(error)
    assert "tls_root_cert" in str(error)


# ============== ADBC (parameterized queries) ==============


@pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC not installed")
@patch("spicepy._client.adbc_driver_manager", MagicMock())
@patch("spicepy._client.adbc_driver_flightsql")
def test_adbc_uses_configured_root_cert(mock_flightsql: MagicMock) -> None:
    _ADBCClient("grpc+tls://spice:50051", tls_root_certs=PEM)
    db_kwargs = mock_flightsql.connect.call_args.kwargs["db_kwargs"]
    assert db_kwargs["adbc.flight.sql.client_option.tls_root_certs"] == PEM.decode()


@pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC not installed")
@patch("spicepy._client.adbc_driver_manager", MagicMock())
@patch("spicepy._client.adbc_driver_flightsql")
def test_adbc_default_keeps_system_roots(mock_flightsql: MagicMock) -> None:
    _ADBCClient("grpc+tls://spice:50051")
    db_kwargs = mock_flightsql.connect.call_args.kwargs["db_kwargs"]
    assert "adbc.flight.sql.client_option.tls_root_certs" not in db_kwargs


@pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC not installed")
@patch("spicepy._client.adbc_driver_manager", MagicMock())
@patch("spicepy._client.adbc_driver_flightsql")
def test_adbc_presents_client_certificate(
    mock_flightsql: MagicMock, tmp_path: Path
) -> None:
    cert = tmp_path / "client.pem"
    key = tmp_path / "client.key"
    cert.write_text("CERT")
    key.write_text("KEY")
    _ADBCClient(
        "grpc+tls://spice:50051", tls_client_certificate=cert, tls_client_key=key
    )
    db_kwargs = mock_flightsql.connect.call_args.kwargs["db_kwargs"]
    assert db_kwargs["adbc.flight.sql.client_option.mtls_cert_chain"] == "CERT"
    assert db_kwargs["adbc.flight.sql.client_option.mtls_private_key"] == "KEY"


@pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC not installed")
def test_client_passes_tls_settings_to_adbc(ca_file: Path, tmp_path: Path) -> None:
    cert = tmp_path / "client.pem"
    key = tmp_path / "client.key"
    cert.write_text("CERT")
    key.write_text("KEY")
    with patch("spicepy._client._SpiceFlight"):
        client = Client(
            flight_url="grpc+tls://spice:50051",
            tls_root_cert=ca_file,
            tls_client_certificate=cert,
            tls_client_key=key,
        )
    with patch("spicepy._client._ADBCClient") as adbc:
        client._ensure_adbc_client()  # pylint: disable=protected-access
    kwargs = adbc.call_args.kwargs
    assert kwargs["tls_root_certs"] == PEM
    assert kwargs["tls_client_certificate"] == cert
    assert kwargs["tls_client_key"] == key
