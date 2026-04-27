"""Comprehensive unit tests for spicepy.config module."""

from __future__ import annotations

import os
import re
from unittest.mock import patch

from spicepy.config import (
    DEFAULT_FLIGHT_URL,
    DEFAULT_HTTP_URL,
    DEFAULT_LOCAL_FLIGHT_URL,
    DEFAULT_LOCAL_HTTP_URL,
    SPICE_USER_AGENT,
    get_user_agent,
)


class TestDefaultUrls:
    """Test default URL constants."""

    def test_default_flight_url(self) -> None:
        """Test default Flight URL value."""
        # Should be set from environment or have a default
        assert DEFAULT_FLIGHT_URL is not None
        assert isinstance(DEFAULT_FLIGHT_URL, str)

    def test_default_http_url(self) -> None:
        """Test default HTTP URL value."""
        assert DEFAULT_HTTP_URL is not None
        assert isinstance(DEFAULT_HTTP_URL, str)

    def test_default_local_flight_url(self) -> None:
        """Test default local Flight URL."""
        assert DEFAULT_LOCAL_FLIGHT_URL is not None
        assert (
            "localhost" in DEFAULT_LOCAL_FLIGHT_URL
            or "127.0.0.1" in DEFAULT_LOCAL_FLIGHT_URL
        )
        assert "50051" in DEFAULT_LOCAL_FLIGHT_URL

    def test_default_local_http_url(self) -> None:
        """Test default local HTTP URL."""
        assert DEFAULT_LOCAL_HTTP_URL is not None
        assert (
            "localhost" in DEFAULT_LOCAL_HTTP_URL
            or "127.0.0.1" in DEFAULT_LOCAL_HTTP_URL
        )
        assert "8090" in DEFAULT_LOCAL_HTTP_URL

    def test_flight_url_format(self) -> None:
        """Test Flight URL has proper gRPC format."""
        assert DEFAULT_LOCAL_FLIGHT_URL.startswith(
            "grpc://"
        ) or DEFAULT_LOCAL_FLIGHT_URL.startswith("grpc+tls://")

    def test_http_url_format(self) -> None:
        """Test HTTP URL has proper HTTP format."""
        assert DEFAULT_LOCAL_HTTP_URL.startswith(
            "http://"
        ) or DEFAULT_LOCAL_HTTP_URL.startswith("https://")


class TestGetUserAgent:
    """Test get_user_agent function."""

    def test_default_user_agent_format(self) -> None:
        """Test default user agent string format."""
        ua = get_user_agent()
        # Format: spicepy/x.y.z (System/release arch)
        pattern = r"spicepy/\d+\.\d+\.\d+ \([^)]+\)"
        assert re.match(
            pattern, ua
        ), f"User agent '{ua}' doesn't match expected pattern"

    def test_user_agent_contains_version(self) -> None:
        """Test user agent contains version number."""
        ua = get_user_agent()
        assert re.search(r"\d+\.\d+\.\d+", ua), "User agent should contain version"

    def test_user_agent_contains_system_info(self) -> None:
        """Test user agent contains system information."""
        ua = get_user_agent()
        assert (
            "(" in ua and ")" in ua
        ), "User agent should contain system info in parentheses"

    def test_custom_client_name(self) -> None:
        """Test custom client name."""
        ua = get_user_agent(client_name="my-app")
        assert ua.startswith("my-app/")
        assert "spicepy" not in ua

    def test_custom_client_version(self) -> None:
        """Test custom client version."""
        ua = get_user_agent(client_version="1.2.3")
        assert "/1.2.3" in ua

    def test_custom_client_system(self) -> None:
        """Test custom client system."""
        ua = get_user_agent(client_system="CustomOS/1.0 custom_arch")
        assert "(CustomOS/1.0 custom_arch)" in ua

    def test_all_custom_values(self) -> None:
        """Test all custom values together."""
        ua = get_user_agent(
            client_name="test-client",
            client_version="2.0.0",
            client_system="TestOS/1.0 test_arch",
        )
        assert ua == "test-client/2.0.0 (TestOS/1.0 test_arch)"

    def test_custom_name_with_default_version(self) -> None:
        """Test custom name with default version."""
        ua = get_user_agent(client_name="custom")
        assert ua.startswith("custom/")
        # Should still have a version number
        assert re.search(r"/\d+\.\d+\.\d+", ua)


class TestSpiceUserAgentConstant:
    """Test SPICE_USER_AGENT constant."""

    def test_constant_is_string(self) -> None:
        """Test SPICE_USER_AGENT is a string."""
        assert isinstance(SPICE_USER_AGENT, str)

    def test_constant_not_empty(self) -> None:
        """Test SPICE_USER_AGENT is not empty."""
        assert len(SPICE_USER_AGENT) > 0

    def test_constant_format(self) -> None:
        """Test SPICE_USER_AGENT format."""
        pattern = r"spicepy/\d+\.\d+\.\d+ \((Linux|Windows|Darwin)/[\d\w\.\-\_]+ (x86_64|aarch64|i386|arm64|AMD64)\)"
        assert re.match(
            pattern, SPICE_USER_AGENT
        ), f"SPICE_USER_AGENT '{SPICE_USER_AGENT}' doesn't match pattern"

    def test_constant_matches_get_user_agent(self) -> None:
        """Test SPICE_USER_AGENT equals get_user_agent() default."""
        assert get_user_agent() == SPICE_USER_AGENT


class TestArchitectureNormalization:
    """Test architecture string normalization."""

    def test_amd64_normalized(self) -> None:
        """Test AMD64 is normalized to x86_64."""
        # This tests the normalization logic in get_user_agent
        with patch("platform.machine", return_value="AMD64"):
            ua = get_user_agent()
            assert "x86_64" in ua
            assert "AMD64" not in ua


class TestEnvironmentVariables:
    """Test environment variable handling."""

    def test_flight_url_from_env(self) -> None:
        """Test SPICE_FLIGHT_URL environment variable."""
        # This is set at module load time, so we can only verify the mechanism works
        env_value = os.environ.get("SPICE_FLIGHT_URL")
        if env_value:
            assert env_value == DEFAULT_FLIGHT_URL

    def test_http_url_from_env(self) -> None:
        """Test SPICE_HTTP_URL environment variable."""
        env_value = os.environ.get("SPICE_HTTP_URL")
        if env_value:
            assert env_value == DEFAULT_HTTP_URL

    def test_local_flight_url_from_env(self) -> None:
        """Test SPICE_LOCAL_FLIGHT_URL environment variable."""
        env_value = os.environ.get("SPICE_LOCAL_FLIGHT_URL")
        if env_value:
            assert env_value == DEFAULT_LOCAL_FLIGHT_URL

    def test_local_http_url_from_env(self) -> None:
        """Test SPICE_LOCAL_HTTP_URL environment variable."""
        env_value = os.environ.get("SPICE_LOCAL_HTTP_URL")
        if env_value:
            assert env_value == DEFAULT_LOCAL_HTTP_URL
