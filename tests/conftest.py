"""Pytest configuration and fixtures for spicepy tests."""

from __future__ import annotations

import os
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest


# ============== Markers ==============


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests that don't require external services")
    config.addinivalue_line("markers", "integration: Integration tests that require Spice runtime")
    config.addinivalue_line("markers", "cloud: Tests that require Spice.ai cloud connection")
    config.addinivalue_line("markers", "slow: Tests that take a long time to run")


# ============== Environment Fixtures ==============


@pytest.fixture
def mock_env_api_key() -> Generator[None, None, None]:
    """Set up mock API key in environment."""
    with patch.dict(os.environ, {"SPICE_API_KEY": "test-api-key"}):
        yield


@pytest.fixture
def clean_env() -> Generator[None, None, None]:
    """Ensure clean environment without API key."""
    env_backup = os.environ.get("SPICE_API_KEY")
    if "SPICE_API_KEY" in os.environ:
        del os.environ["SPICE_API_KEY"]
    yield
    if env_backup is not None:
        os.environ["SPICE_API_KEY"] = env_backup


# ============== ADBC Availability ==============


def is_adbc_available() -> bool:
    """Check if ADBC driver is available."""
    try:
        import adbc_driver_flightsql  # noqa: F401
        import adbc_driver_manager  # noqa: F401

        return True
    except ImportError:
        return False


skip_if_no_adbc = pytest.mark.skipif(not is_adbc_available(), reason="ADBC driver not installed")


# ============== Mock Fixtures ==============


@pytest.fixture
def mock_flight_client() -> Generator[MagicMock, None, None]:
    """Create a mock Flight client."""
    with patch("spicepy._client.flight") as mock_flight:
        mock_client = MagicMock()
        mock_flight.connect.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_adbc_connection() -> Generator[MagicMock, None, None]:
    """Create a mock ADBC connection."""
    with patch("spicepy._client.adbc_driver_flightsql") as mock_adbc:
        mock_conn = MagicMock()
        mock_adbc.dbapi.connect.return_value = mock_conn
        yield mock_conn


# ============== Sample Data Fixtures ==============


@pytest.fixture
def sample_param_values() -> dict:
    """Sample parameter values for testing."""
    return {
        "int": 42,
        "float": 3.14159,
        "string": "test_value",
        "bool": True,
        "none": None,
        "bytes": b"\x00\x01\x02",
        "negative_int": -100,
        "large_int": 2**60,
        "unicode_string": "测试 🚀 тест",
        "empty_string": "",
        "zero": 0,
        "negative_float": -273.15,
        "infinity": float("inf"),
        "negative_infinity": float("-inf"),
    }


@pytest.fixture
def sample_datetime_values():
    """Sample datetime values for testing."""
    from datetime import date, datetime, time, timedelta
    from decimal import Decimal

    return {
        "date": date(2024, 1, 15),
        "datetime": datetime(2024, 1, 15, 10, 30, 45),
        "time": time(10, 30, 45),
        "timedelta": timedelta(days=1, hours=2, minutes=30),
        "decimal": Decimal("123.456"),
        "epoch_date": date(1970, 1, 1),
        "future_date": date(2099, 12, 31),
    }


# ============== HTTP Mock Fixtures ==============


@pytest.fixture
def mock_http_session() -> Generator[MagicMock, None, None]:
    """Create a mock HTTP session."""
    with patch("spicepy._http.Session") as mock_session_class:
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_session.headers = {}
        yield mock_session


# ============== Local Client Fixture ==============


@pytest.fixture
def local_flight_url() -> str:
    """Return the local Flight URL."""
    return os.environ.get("SPICE_LOCAL_FLIGHT_URL", "grpc://localhost:50051")


@pytest.fixture
def local_http_url() -> str:
    """Return the local HTTP URL."""
    return os.environ.get("SPICE_LOCAL_HTTP_URL", "http://localhost:8090")
