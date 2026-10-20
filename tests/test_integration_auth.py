"""Live-runtime tests against a Spice OSS runtime secured with an API key.

The runtime must be started with ``runtime.auth.api-key`` enabled and these
variables set (``test.yml`` does this on Linux and macOS):

- ``SPICE_AUTH_FLIGHT_URL`` / ``SPICE_AUTH_HTTP_URL``: the secured runtime.
- ``SPICE_AUTH_API_KEY``: a key the runtime accepts.

An OSS runtime accepts the key only as ``Authorization: Bearer <key>`` and
rejects the Flight Basic handshake, which is what parameterized (ADBC) queries
used to send. The module is skipped when the variables are unset.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pyarrow as pa
from pyarrow import flight
import pytest

from spicepy import Client

FLIGHT_URL = os.environ.get("SPICE_AUTH_FLIGHT_URL")
HTTP_URL = os.environ.get("SPICE_AUTH_HTTP_URL")
API_KEY = os.environ.get("SPICE_AUTH_API_KEY")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (FLIGHT_URL and HTTP_URL and API_KEY),
        reason="no API-key-secured runtime (set SPICE_AUTH_FLIGHT_URL, "
        "SPICE_AUTH_HTTP_URL, SPICE_AUTH_API_KEY)",
    ),
]

# Needs no dataset, so the secured runtime can run an empty Spicepod.
PARAM_SQL = (
    "SELECT count(*) AS n FROM (VALUES ('paid'), ('paid'), ('open')) "
    "AS t(status) WHERE status = $1"
)

try:
    import adbc_driver_manager

    ADBC_ERROR: type[Exception] = adbc_driver_manager.ProgrammingError
except ImportError:  # pragma: no cover - the test extra installs ADBC
    ADBC_ERROR = Exception

requires_adbc = pytest.mark.skipif(
    ADBC_ERROR is Exception, reason="ADBC driver not installed"
)


def _client(api_key: str | None) -> Client:
    return Client(api_key=api_key, flight_url=FLIGHT_URL, http_url=HTTP_URL)


@pytest.fixture(name="no_env_key", autouse=True)
def no_env_key_fixture():
    """Keep a stray SPICE_API_KEY from standing in for the key under test."""
    env = {k: v for k, v in os.environ.items() if k != "SPICE_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        yield


def _count(table: pa.Table) -> int:
    return int(table.column("n")[0].as_py())


# ============== Valid key ==============


def test_query_arrow_flight() -> None:
    assert _client(API_KEY).query_pylist("SELECT 1 AS a") == [{"a": 1}]


@requires_adbc
def test_sql_with_params() -> None:
    reader = _client(API_KEY).sql_with_params(PARAM_SQL, ["paid"])
    assert _count(reader.read_all()) == 2


@requires_adbc
def test_query_arrow_with_params() -> None:
    assert _count(_client(API_KEY).query_arrow(PARAM_SQL, params=["paid"])) == 2


@requires_adbc
def test_query_batches_with_params() -> None:
    batches = list(_client(API_KEY).query_batches(PARAM_SQL, params=["open"]))
    assert _count(pa.Table.from_batches(batches)) == 1


@requires_adbc
def test_flight_and_params_share_one_client() -> None:
    client = _client(API_KEY)
    for _ in range(2):
        assert client.query_pylist("SELECT 1 AS a") == [{"a": 1}]
        assert _count(client.query_arrow(PARAM_SQL, params=["paid"])) == 2


def test_custom_user_agent_still_authenticates() -> None:
    client = Client(
        api_key=API_KEY,
        flight_url=FLIGHT_URL,
        http_url=HTTP_URL,
        user_agent="spicepy-auth-test/1.0",
    )
    assert client.query_pylist("SELECT 1 AS a") == [{"a": 1}]


# ============== Wrong key ==============


def test_wrong_key_flight_is_unauthenticated() -> None:
    with pytest.raises(flight.FlightUnauthenticatedError, match="Invalid credentials"):
        _client("not-the-key").query_arrow("SELECT 1")


@requires_adbc
def test_wrong_key_params_is_unauthenticated() -> None:
    client = _client("not-the-key")
    with pytest.raises(ADBC_ERROR, match=r"UNAUTHENTICATED.*Invalid credentials"):
        client.sql_with_params(PARAM_SQL, ["paid"])
    with pytest.raises(ADBC_ERROR, match=r"UNAUTHENTICATED.*Invalid credentials"):
        client.query_arrow(PARAM_SQL, params=["paid"])
    with pytest.raises(ADBC_ERROR, match=r"UNAUTHENTICATED.*Invalid credentials"):
        list(client.query_batches(PARAM_SQL, params=["paid"]))


# ============== No key ==============


def test_no_key_flight_reports_missing_header() -> None:
    with pytest.raises(
        flight.FlightUnauthenticatedError, match="Missing authorization header"
    ):
        _client(None).query_arrow("SELECT 1")


@requires_adbc
def test_no_key_params_reports_missing_header() -> None:
    client = _client(None)
    with pytest.raises(ADBC_ERROR, match="Missing authorization header"):
        client.sql_with_params(PARAM_SQL, ["paid"])
    with pytest.raises(ADBC_ERROR, match="Missing authorization header"):
        client.query_arrow(PARAM_SQL, params=["paid"])
    with pytest.raises(ADBC_ERROR, match="Missing authorization header"):
        list(client.query_batches(PARAM_SQL, params=["paid"]))
