"""Live-runtime tests against a Spice runtime serving TLS from a private CA.

The runtime's certificate is signed by a CA that is in neither the system nor
the certifi bundle, so a call only succeeds if it verifies against
``tls_root_cert``. ``test.yml`` starts the runtime on Linux and macOS and sets:

- ``SPICE_TLS_FLIGHT_URL`` / ``SPICE_TLS_HTTP_URL``: the TLS runtime.
- ``SPICE_TLS_API_KEY``: a read-write key it accepts.
- ``SPICE_TLS_ROOT_CERT``: the CA that signed its certificate.
- ``SPICE_TLS_WRONG_CA``: an unrelated CA.

The module is skipped when the variables are unset.
"""

from __future__ import annotations

from collections.abc import Iterator
import os
import time
from unittest.mock import patch

import pytest

from spicepy import Client
from spicepy.error import SpiceAIError, SpiceTLSError

FLIGHT_URL = os.environ.get("SPICE_TLS_FLIGHT_URL")
HTTP_URL = os.environ.get("SPICE_TLS_HTTP_URL")
API_KEY = os.environ.get("SPICE_TLS_API_KEY")
ROOT_CERT = os.environ.get("SPICE_TLS_ROOT_CERT")
WRONG_CA = os.environ.get("SPICE_TLS_WRONG_CA")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (FLIGHT_URL and HTTP_URL and API_KEY and ROOT_CERT and WRONG_CA),
        reason="no private-CA TLS runtime (set SPICE_TLS_FLIGHT_URL, "
        "SPICE_TLS_HTTP_URL, SPICE_TLS_API_KEY, SPICE_TLS_ROOT_CERT, "
        "SPICE_TLS_WRONG_CA)",
    ),
]

try:
    import adbc_driver_manager  # noqa: F401  # pylint: disable=unused-import

    HAS_ADBC = True
except ImportError:  # pragma: no cover - the test extra installs ADBC
    HAS_ADBC = False

requires_adbc = pytest.mark.skipif(not HAS_ADBC, reason="ADBC driver not installed")


@pytest.fixture(name="no_ca_env", autouse=True)
def no_ca_env_fixture():
    """Keep the CA from reaching requests through the environment.

    REQUESTS_CA_BUNDLE / SSL_CERT_FILE pointing at the CA was the workaround
    for tls_root_cert being ignored; with it set these tests prove nothing.
    """
    stripped = {"REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE"}
    env = {k: v for k, v in os.environ.items() if k not in stripped}
    with patch.dict(os.environ, env, clear=True):
        yield


def _client(ca: str | None) -> Client:
    return Client(
        api_key=API_KEY, flight_url=FLIGHT_URL, http_url=HTTP_URL, tls_root_cert=ca
    )


@pytest.fixture(name="client")
def client_fixture() -> Iterator[Client]:
    client = _client(ROOT_CERT)
    yield client
    # Close the ADBC connection here rather than leaving it to interpreter
    # shutdown: a TLS ADBC (Go FlightSQL driver) connection still open at exit
    # crashed the CI pytest process after every test had passed.
    if client._adbc_client is not None:  # pylint: disable=protected-access
        client._adbc_client.close()  # pylint: disable=protected-access


# ============== Every transport verifies against tls_root_cert ==============


def test_sql(client: Client) -> None:
    assert client.query_pylist("SELECT 1 AS a") == [{"a": 1}]


@requires_adbc
def test_sql_with_params(client: Client) -> None:
    table = client.sql_with_params(
        "SELECT count(*) AS n FROM (VALUES ('a'), ('a'), ('b')) AS t(v) WHERE v = $1",
        ["a"],
    ).read_all()
    assert table.column("n")[0].as_py() == 2


def test_is_ready(client: Client) -> None:
    assert client.is_ready() is True


def test_runtime_status(client: Client) -> None:
    names = {status.name for status in client.runtime_status()}
    assert {"http", "flight"} <= names


def test_refresh_dataset(client: Client) -> None:
    # No such dataset, so the runtime answers 404. A runtime answer, rather than
    # a SpiceTLSError, is the proof the request got through TLS.
    with pytest.raises(SpiceAIError) as raised:
        client.refresh_dataset("no_such_dataset")
    assert not isinstance(raised.value, SpiceTLSError)
    assert "404" in str(raised.value)


# ============== The wrong CA fails fast, as a SpiceTLSError ==============


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.is_ready(),
        lambda c: c.runtime_status(),
        lambda c: c.refresh_dataset("tls_mem"),
    ],
    ids=["is_ready", "runtime_status", "refresh_dataset"],
)
def test_wrong_ca_fails_fast(call) -> None:
    client = _client(WRONG_CA)
    started = time.monotonic()
    with pytest.raises(SpiceTLSError, match="certificate"):
        call(client)
    assert time.monotonic() - started < 2
