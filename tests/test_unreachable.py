"""An unreachable runtime raises SpiceConnectionError from every HTTP method.

The client methods document ``SpiceAIError`` for a runtime that is unreachable;
these tests point a client at a local port that refuses connections and check
that the documented type, not a raw ``requests`` exception, comes back.
"""

from __future__ import annotations

from collections.abc import Callable
import socket
import threading
from typing import Any

import pytest
import requests

from spicepy import Client
from spicepy._http import HttpRequests, _causes
from spicepy.error import SpiceAIError, SpiceConnectionError, SpiceConnectTimeoutError


@pytest.fixture(autouse=True)
def _no_env_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep requests from sending these requests to a proxy named in the
    environment, so the connection attempts and the DNS lookup happen locally.
    """
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)


@pytest.fixture(name="refused_url")
def refused_url_fixture() -> str:
    """An HTTP URL on 127.0.0.1 whose port refuses connections.

    The port is taken from the OS and released, so nothing listens on it.
    (A socket bound without listening is not enough: macOS drops the connection
    attempt instead of refusing it, and the request waits for a connect timeout.)
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


CALLS: dict[str, Callable[[Client], Any]] = {
    "is_ready": lambda c: c.is_ready(),
    "runtime_status": lambda c: c.runtime_status(),
    "list_active_queries": lambda c: c.list_active_queries(),
    "cancel_active_query": lambda c: c.cancel_active_query(
        "0b5c3f0e-6a1d-4c7b-9a43-2f6d8e1b7c90"
    ),
    "refresh_dataset": lambda c: c.refresh_dataset("taxi_trips"),
    "search": lambda c: c.search("cheap rides"),
    "nsql": lambda c: c.nsql("how many trips?"),
    "query": lambda c: c.query("SELECT 1"),
}


@pytest.mark.parametrize("call", CALLS.values(), ids=CALLS.keys())
def test_unreachable_runtime_raises_spice_connection_error(
    refused_url: str, call: Callable[[Client], Any]
) -> None:
    client = Client(flight_url="grpc://127.0.0.1:1", http_url=refused_url)

    with pytest.raises(SpiceConnectionError) as raised:
        call(client)

    error = raised.value
    # The type the methods document, and still the requests type for code that
    # already catches that.
    assert isinstance(error, SpiceAIError)
    assert isinstance(error, requests.exceptions.ConnectionError)
    assert refused_url in str(error)
    assert "http_url" in str(error)
    # The operating system's own reason, whose wording differs by platform
    # ("Connection refused" on Linux and macOS, "No connection could be made
    # because the target machine actively refused it" on Windows).
    refused = next(
        cause
        for cause in _causes(error.__cause__)
        if isinstance(cause, ConnectionRefusedError)
    )
    assert refused.strerror
    assert refused.strerror in str(error)


def test_unresolvable_host_names_the_lookup_failure() -> None:
    http = HttpRequests("http://spice-runtime.invalid:8090", {})

    with pytest.raises(SpiceConnectionError) as raised:
        http.send_request_raw("GET", "/v1/ready")

    assert "spice-runtime.invalid" in str(raised.value)
    assert isinstance(raised.value.__cause__, requests.exceptions.ConnectionError)


def test_connect_timeout_stays_a_requests_timeout() -> None:
    http = HttpRequests("http://127.0.0.1:8090", {})

    def timed_out(**_: Any) -> requests.Response:
        raise requests.exceptions.ConnectTimeout("connect timed out")

    http.session.get = timed_out  # type: ignore[method-assign]

    with pytest.raises(SpiceConnectTimeoutError) as raised:
        http.send_request_raw("GET", "/v1/ready")

    error = raised.value
    assert isinstance(error, SpiceConnectionError)
    assert isinstance(error, requests.exceptions.ConnectTimeout)
    assert isinstance(error, requests.exceptions.Timeout)
    assert "connect timed out" in str(error)


def test_error_text_leaves_out_url_credentials(refused_url: str) -> None:
    with_credentials = refused_url.replace(
        "http://", "http://review-user:review-secret@"
    )
    http = HttpRequests(with_credentials, {})

    with pytest.raises(SpiceConnectionError) as raised:
        http.send_request_raw("GET", "/v1/ready")

    text = str(raised.value)
    assert "review-user" not in text
    assert "review-secret" not in text
    assert f"{refused_url}/v1/ready" in text


def test_proxy_failure_is_raised_unchanged() -> None:
    http = HttpRequests("http://127.0.0.1:8090", {})
    proxy_error = requests.exceptions.ProxyError("Unable to connect to proxy")

    def through_proxy(**_: Any) -> requests.Response:
        raise proxy_error

    http.session.get = through_proxy  # type: ignore[method-assign]

    with pytest.raises(requests.exceptions.ProxyError) as raised:
        http.send_request_raw("GET", "/v1/ready")

    assert raised.value is proxy_error


def test_connection_dropped_after_the_request_is_raised_unchanged() -> None:
    received: list[bytes] = []
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        def accept_then_close() -> None:
            conn, _ = server.accept()
            with conn:
                received.append(conn.recv(65536))

        thread = threading.Thread(target=accept_then_close, daemon=True)
        thread.start()
        http = HttpRequests(f"http://127.0.0.1:{port}", {})

        with pytest.raises(requests.exceptions.ConnectionError) as raised:
            http.send_request_raw("POST", "/v1/queries", body="SELECT 1")
        thread.join(timeout=5)

    assert received and received[0].startswith(b"POST /v1/queries")
    assert not isinstance(raised.value, SpiceConnectionError)
