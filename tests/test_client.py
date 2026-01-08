"""Comprehensive unit tests for spicepy._client module."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pytest

from spicepy import Client
from spicepy._client import ADBC_AVAILABLE, _ADBCClient, _Cert
from spicepy.config import DEFAULT_LOCAL_FLIGHT_URL


class TestCert:
    """Test _Cert class."""

    def test_cert_with_none(self) -> None:
        """Test _Cert with None uses certifi."""
        cert = _Cert(None)
        # Should not raise and should have tls_root_certs set
        assert cert.tls_root_certs is not None
        assert isinstance(cert.tls_root_certs, bytes)

    def test_cert_with_path_string(self, tmp_path: Path) -> None:
        """Test _Cert with path string."""
        cert_file = tmp_path / "test.crt"
        cert_content = b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"
        cert_file.write_bytes(cert_content)

        cert = _Cert(str(cert_file))
        assert cert.tls_root_certs == cert_content

    def test_cert_with_path_object(self, tmp_path: Path) -> None:
        """Test _Cert with Path object."""
        cert_file = tmp_path / "test.crt"
        cert_content = b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"
        cert_file.write_bytes(cert_content)

        cert = _Cert(cert_file)
        assert cert.tls_root_certs == cert_content

    def test_cert_file_not_found(self) -> None:
        """Test _Cert with non-existent file."""
        with pytest.raises(FileNotFoundError):
            _Cert("/nonexistent/path/cert.pem")


class TestClientInit:
    """Test Client initialization."""

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_client_default_init(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test Client with default parameters."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client()

        assert client.api_key is None
        assert client._flight_url == DEFAULT_LOCAL_FLIGHT_URL
        assert client._adbc_client is None

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_client_with_api_key(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test Client with API key."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client(api_key="test-key")

        assert client.api_key == "test-key"

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_client_with_custom_urls(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test Client with custom URLs."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client(flight_url="grpc+tls://custom.spiceai.io", http_url="https://custom-data.spiceai.io")

        assert client._flight_url == "grpc+tls://custom.spiceai.io"

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_client_with_user_agent(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test Client with custom user agent."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client(user_agent="my-app/1.0")

        assert client._user_agent == "my-app/1.0"


class TestClientApiKey:
    """Test Client._api_key method."""

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_api_key_from_init(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test _api_key returns value from init."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client(api_key="init-key")

        assert client._api_key() == "init-key"

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_api_key_from_env(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test _api_key returns value from environment."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        with patch.dict(os.environ, {"SPICE_API_KEY": "env-key"}):
            client = Client()
            assert client._api_key() == "env-key"

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_api_key_init_takes_precedence(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test init api_key takes precedence over environment."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        with patch.dict(os.environ, {"SPICE_API_KEY": "env-key"}):
            client = Client(api_key="init-key")
            assert client._api_key() == "init-key"


class TestClientHeaders:
    """Test Client._headers method."""

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_headers_with_api_key(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test _headers includes API key."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client(api_key="test-key")
        headers = client._headers()

        assert headers["X-API-Key"] == "test-key"
        assert headers["Accept"] == "application/json"

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_headers_with_custom_user_agent(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test _headers includes custom user agent."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client()
        headers = client._headers(user_agent="custom-agent")

        assert headers["user-agent"] == "custom-agent"


class TestClientGetAdbcUri:
    """Test Client._get_adbc_uri method."""

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_get_adbc_uri_grpc_tls(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test _get_adbc_uri with grpc+tls:// URL."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client(flight_url="grpc+tls://flight.spiceai.io")
        uri = client._get_adbc_uri()

        assert uri == "grpc+tls://flight.spiceai.io"

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_get_adbc_uri_grpc(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test _get_adbc_uri with grpc:// URL."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client(flight_url="grpc://localhost:50051")
        uri = client._get_adbc_uri()

        assert uri == "grpc://localhost:50051"


class TestClientQueryWithParams:
    """Test Client.query_with_params method."""

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_query_with_params_none_raises(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test query_with_params raises ValueError when params is None."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client()

        with pytest.raises(ValueError, match="params must be a list"):
            client.query_with_params("SELECT 1", None)  # type: ignore

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    @patch("spicepy._client._ADBCClient")
    def test_query_with_params_creates_adbc_client(
        self,
        mock_adbc_class: MagicMock,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test query_with_params creates ADBC client on first call."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_adbc = MagicMock()
        mock_reader = MagicMock()
        mock_adbc.query_with_params.return_value = mock_reader
        mock_adbc_class.return_value = mock_adbc

        client = Client()
        client.query_with_params("SELECT 1", [])

        mock_adbc_class.assert_called_once()

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    @patch("spicepy._client._ADBCClient")
    def test_query_with_params_reuses_adbc_client(
        self,
        mock_adbc_class: MagicMock,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test query_with_params reuses ADBC client on subsequent calls."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_adbc = MagicMock()
        mock_reader = MagicMock()
        mock_adbc.query_with_params.return_value = mock_reader
        mock_adbc_class.return_value = mock_adbc

        client = Client()
        client.query_with_params("SELECT 1", [])
        client.query_with_params("SELECT 2", [])

        # Should only create client once
        assert mock_adbc_class.call_count == 1

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    @patch("spicepy._client._ADBCClient")
    def test_query_with_params_passes_correct_args(
        self,
        mock_adbc_class: MagicMock,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test query_with_params passes SQL and params to ADBC client."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_adbc = MagicMock()
        mock_reader = MagicMock()
        mock_adbc.query_with_params.return_value = mock_reader
        mock_adbc_class.return_value = mock_adbc

        client = Client(flight_url="grpc://localhost:50051", api_key="test-key")
        result = client.query_with_params("SELECT * FROM t WHERE id = $1", [42])

        mock_adbc.query_with_params.assert_called_once_with("SELECT * FROM t WHERE id = $1", [42])
        assert result == mock_reader

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    @patch("spicepy._client._ADBCClient")
    def test_ensure_adbc_client_passes_user_agent(
        self,
        mock_adbc_class: MagicMock,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test _ensure_adbc_client passes user_agent to ADBC client."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_adbc = MagicMock()
        mock_adbc.query_with_params.return_value = MagicMock()
        mock_adbc_class.return_value = mock_adbc

        client = Client(flight_url="grpc://localhost:50051", user_agent="custom-agent")
        client.query_with_params("SELECT 1", [])

        mock_adbc_class.assert_called_once_with(
            uri="grpc://localhost:50051",
            api_key="",
            user_agent="custom-agent",
        )


class TestADBCClient:
    """Test _ADBCClient class."""

    def test_adbc_client_not_available_raises(self) -> None:
        """Test _ADBCClient raises ImportError when ADBC not available."""
        with patch("spicepy._client.ADBC_AVAILABLE", False):
            with pytest.raises(ImportError, match="ADBC driver is not available"):
                _ADBCClient("grpc://localhost:50051")

    @pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC not installed")
    @patch("spicepy._client.adbc_driver_flightsql")
    @patch("spicepy._client.adbc_driver_manager")
    def test_adbc_client_init(
        self,
        mock_manager: MagicMock,
        mock_flightsql: MagicMock,
    ) -> None:
        """Test _ADBCClient initialization."""
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_flightsql.connect.return_value = mock_db
        mock_manager.AdbcConnection.return_value = mock_conn
        mock_manager.DatabaseOptions.URI.value = "adbc.driver.uri"
        mock_manager.DatabaseOptions.USERNAME.value = "adbc.driver.username"
        mock_manager.DatabaseOptions.PASSWORD.value = "adbc.driver.password"

        client = _ADBCClient("grpc://localhost:50051", api_key="test-key")

        assert client._db == mock_db
        assert client._conn == mock_conn
        mock_flightsql.connect.assert_called_once()
        mock_manager.AdbcConnection.assert_called_once_with(mock_db)

    @pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC not installed")
    @patch("spicepy._client.adbc_driver_flightsql")
    @patch("spicepy._client.adbc_driver_manager")
    def test_adbc_client_close(
        self,
        mock_manager: MagicMock,
        mock_flightsql: MagicMock,
    ) -> None:
        """Test _ADBCClient close."""
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_flightsql.connect.return_value = mock_db
        mock_manager.AdbcConnection.return_value = mock_conn
        mock_manager.DatabaseOptions.URI.value = "uri"
        mock_manager.DatabaseOptions.USERNAME.value = "username"
        mock_manager.DatabaseOptions.PASSWORD.value = "password"

        client = _ADBCClient("grpc://localhost:50051")
        client.close()

        mock_conn.close.assert_called_once()
        mock_db.close.assert_called_once()
        assert client._db is None
        assert client._conn is None


class TestADBCClientCreateParamBatch:
    """Test _ADBCClient._create_param_batch method."""

    @pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC not installed")
    @patch("spicepy._client.adbc_driver_flightsql")
    @patch("spicepy._client.adbc_driver_manager")
    def test_create_param_batch_single_int(
        self,
        mock_manager: MagicMock,
        mock_flightsql: MagicMock,
    ) -> None:
        """Test _create_param_batch with single integer."""
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_flightsql.connect.return_value = mock_db
        mock_manager.AdbcConnection.return_value = mock_conn
        mock_manager.DatabaseOptions.URI.value = "uri"
        mock_manager.DatabaseOptions.USERNAME.value = "username"
        mock_manager.DatabaseOptions.PASSWORD.value = "password"

        client = _ADBCClient("grpc://localhost:50051")
        batch = client._create_param_batch([42])

        assert isinstance(batch, pa.RecordBatch)
        assert batch.num_rows == 1
        assert batch.num_columns == 1
        assert batch.schema.field(0).name == "$1"

    @pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC not installed")
    @patch("spicepy._client.adbc_driver_flightsql")
    @patch("spicepy._client.adbc_driver_manager")
    def test_create_param_batch_multiple_params(
        self,
        mock_manager: MagicMock,
        mock_flightsql: MagicMock,
    ) -> None:
        """Test _create_param_batch with multiple parameters."""
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_flightsql.connect.return_value = mock_db
        mock_manager.AdbcConnection.return_value = mock_conn
        mock_manager.DatabaseOptions.URI.value = "uri"
        mock_manager.DatabaseOptions.USERNAME.value = "username"
        mock_manager.DatabaseOptions.PASSWORD.value = "password"

        client = _ADBCClient("grpc://localhost:50051")
        batch = client._create_param_batch([42, "test", 3.14])

        assert batch.num_columns == 3
        assert batch.schema.field(0).name == "$1"
        assert batch.schema.field(1).name == "$2"
        assert batch.schema.field(2).name == "$3"

    @pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC not installed")
    @patch("spicepy._client.adbc_driver_flightsql")
    @patch("spicepy._client.adbc_driver_manager")
    def test_create_param_batch_with_explicit_param(
        self,
        mock_manager: MagicMock,
        mock_flightsql: MagicMock,
    ) -> None:
        """Test _create_param_batch with explicit Param type."""
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_flightsql.connect.return_value = mock_db
        mock_manager.AdbcConnection.return_value = mock_conn
        mock_manager.DatabaseOptions.URI.value = "uri"
        mock_manager.DatabaseOptions.USERNAME.value = "username"
        mock_manager.DatabaseOptions.PASSWORD.value = "password"

        client = _ADBCClient("grpc://localhost:50051")
        batch = client._create_param_batch([(42, pa.int32())])

        assert batch.schema.field(0).type == pa.int32()

    @pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC not installed")
    @patch("spicepy._client.adbc_driver_flightsql")
    @patch("spicepy._client.adbc_driver_manager")
    def test_create_param_batch_mixed_types(
        self,
        mock_manager: MagicMock,
        mock_flightsql: MagicMock,
    ) -> None:
        """Test _create_param_batch with mixed inferred and explicit types."""
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_flightsql.connect.return_value = mock_db
        mock_manager.AdbcConnection.return_value = mock_conn
        mock_manager.DatabaseOptions.URI.value = "uri"
        mock_manager.DatabaseOptions.USERNAME.value = "username"
        mock_manager.DatabaseOptions.PASSWORD.value = "password"

        client = _ADBCClient("grpc://localhost:50051")
        batch = client._create_param_batch([42, (3.14, pa.float32())])

        assert batch.schema.field(0).type == pa.int64()  # Inferred
        assert batch.schema.field(1).type == pa.float32()  # Explicit


class TestClientQuery:
    """Test Client.query method."""

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_query_delegates_to_flight(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test query delegates to _SpiceFlight."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_flight = MagicMock()
        mock_reader = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        result = client.query("SELECT 1")

        assert result == mock_reader
        mock_flight.query.assert_called_once_with("SELECT 1")

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_query_with_timeout(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test query with timeout parameter."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_flight = MagicMock()
        mock_flight_class.return_value = mock_flight

        client = Client()
        client.query("SELECT 1", timeout=60)

        mock_flight.query.assert_called_once_with("SELECT 1", timeout=60)


class TestClientRefreshDataset:
    """Test Client.refresh_dataset method."""

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_refresh_dataset_basic(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test refresh_dataset basic call."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client()
        client.http = MagicMock()
        client.http.send_request.return_value = {"message": "success"}

        result = client.refresh_dataset("my_dataset")

        assert result == {"message": "success"}
        client.http.send_request.assert_called_once()

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_refresh_dataset_with_opts(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test refresh_dataset with RefreshOpts."""
        from spicepy import RefreshOpts

        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client()
        client.http = MagicMock()
        client.http.send_request.return_value = {"message": "success"}

        opts = RefreshOpts(refresh_sql="SELECT 1")
        result = client.refresh_dataset("my_dataset", opts)

        assert result == {"message": "success"}


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_client_with_empty_api_key(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test Client with empty string API key."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client(api_key="")
        assert client.api_key == ""

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_client_with_special_chars_in_url(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test Client with special characters in URL."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        # Should not raise
        Client(flight_url="grpc://host-with-dash.example.com:50051")

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_query_with_params_empty_list(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Test query_with_params with empty list."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        with patch("spicepy._client._ADBCClient") as mock_adbc_class:
            mock_adbc = MagicMock()
            mock_adbc.query_with_params.return_value = MagicMock()
            mock_adbc_class.return_value = mock_adbc

            client = Client()
            client.query_with_params("SELECT 1", [])

            mock_adbc.query_with_params.assert_called_once_with("SELECT 1", [])


class TestSpiceFlight:
    """Test _SpiceFlight class."""

    @patch("spicepy._client.flight")
    def test_user_agent_default(
        self,
        mock_flight: MagicMock,
    ) -> None:
        """Test _user_agent static method with default user agent."""
        from spicepy._client import _SpiceFlight
        from spicepy.config import SPICE_USER_AGENT

        result = _SpiceFlight._user_agent()

        assert result[0] == b"user-agent"
        assert result[1] == SPICE_USER_AGENT.encode()

    @patch("spicepy._client.flight")
    def test_user_agent_custom(
        self,
        mock_flight: MagicMock,
    ) -> None:
        """Test _user_agent static method with custom user agent."""
        from spicepy._client import _SpiceFlight
        from spicepy.config import SPICE_USER_AGENT

        result = _SpiceFlight._user_agent("custom-agent")

        assert result[0] == b"user-agent"
        assert result[1] == f"custom-agent {SPICE_USER_AGENT}".encode()

    @patch("spicepy._client.flight")
    def test_spice_flight_init(
        self,
        mock_flight: MagicMock,
    ) -> None:
        """Test _SpiceFlight initialization."""
        from spicepy._client import _SpiceFlight

        mock_client = MagicMock()
        mock_flight.connect.return_value = mock_client
        mock_client.authenticate_basic_token.return_value = ("bearer", b"token")

        flight_instance = _SpiceFlight(
            grpc="grpc://localhost:50051",
            api_key="",
            tls_root_certs=b"cert",
            user_agent=None,
        )

        mock_flight.connect.assert_called_once()
        assert flight_instance._flight_client == mock_client

    @patch("spicepy._client.flight")
    def test_spice_flight_authenticate_with_api_key(
        self,
        mock_flight: MagicMock,
    ) -> None:
        """Test _SpiceFlight authentication with API key."""
        from spicepy._client import _SpiceFlight

        mock_client = MagicMock()
        mock_flight.connect.return_value = mock_client
        mock_client.authenticate_basic_token.return_value = ("bearer", b"token")

        flight_instance = _SpiceFlight(
            grpc="grpc://localhost:50051",
            api_key="test-api-key",
            tls_root_certs=b"cert",
        )

        assert flight_instance is not None
        mock_client.authenticate_basic_token.assert_called_with("", "test-api-key")

    @patch("spicepy._client.flight")
    def test_spice_flight_query_basic(
        self,
        mock_flight: MagicMock,
    ) -> None:
        """Test _SpiceFlight.query method."""
        from spicepy._client import _SpiceFlight

        mock_client = MagicMock()
        mock_flight.connect.return_value = mock_client

        mock_flight_info = MagicMock()
        mock_endpoint = MagicMock()
        mock_ticket = MagicMock()
        mock_endpoint.ticket = mock_ticket
        mock_flight_info.endpoints = [mock_endpoint]
        mock_client.get_flight_info.return_value = mock_flight_info

        mock_reader = MagicMock()

        flight_instance = _SpiceFlight(
            grpc="grpc://localhost:50051",
            api_key="",
            tls_root_certs=b"cert",
        )

        # Mock the _threaded_flight_do_get method directly
        with patch.object(flight_instance, "_threaded_flight_do_get", return_value=mock_reader):
            result = flight_instance.query("SELECT 1")

        assert result is mock_reader
        mock_client.get_flight_info.assert_called_once()

    @patch("spicepy._client.flight")
    def test_spice_flight_query_with_timeout(
        self,
        mock_flight: MagicMock,
    ) -> None:
        """Test _SpiceFlight.query with timeout parameter."""
        from spicepy._client import _SpiceFlight

        mock_client = MagicMock()
        mock_flight.connect.return_value = mock_client

        mock_flight_info = MagicMock()
        mock_endpoint = MagicMock()
        mock_ticket = MagicMock()
        mock_endpoint.ticket = mock_ticket
        mock_flight_info.endpoints = [mock_endpoint]
        mock_client.get_flight_info.return_value = mock_flight_info

        mock_reader = MagicMock()

        flight_instance = _SpiceFlight(
            grpc="grpc://localhost:50051",
            api_key="",
            tls_root_certs=b"cert",
        )

        # Mock the _threaded_flight_do_get method directly
        with patch.object(flight_instance, "_threaded_flight_do_get", return_value=mock_reader):
            flight_instance.query("SELECT 1", timeout=60)

    @patch("spicepy._client.flight")
    def test_spice_flight_query_invalid_timeout_raises(
        self,
        mock_flight: MagicMock,
    ) -> None:
        """Test _SpiceFlight.query with invalid timeout raises ValueError."""
        from spicepy._client import _SpiceFlight

        mock_client = MagicMock()
        mock_flight.connect.return_value = mock_client

        flight_instance = _SpiceFlight(
            grpc="grpc://localhost:50051",
            api_key="",
            tls_root_certs=b"cert",
        )

        with pytest.raises(ValueError, match="Timeout must be a positive integer"):
            flight_instance.query("SELECT 1", timeout=-1)

        with pytest.raises(ValueError, match="Timeout must be a positive integer"):
            flight_instance.query("SELECT 1", timeout=0)

    @patch("spicepy._client.flight")
    def test_spice_flight_query_reauthenticate_on_unauthenticated(
        self,
        mock_flight: MagicMock,
    ) -> None:
        """Test _SpiceFlight.query re-authenticates on FlightUnauthenticatedError."""
        from pyarrow._flight import FlightUnauthenticatedError

        from spicepy._client import _SpiceFlight

        mock_client = MagicMock()
        mock_flight.connect.return_value = mock_client
        mock_flight.FlightUnauthenticatedError = FlightUnauthenticatedError

        mock_flight_info = MagicMock()
        mock_endpoint = MagicMock()
        mock_ticket = MagicMock()
        mock_endpoint.ticket = mock_ticket
        mock_flight_info.endpoints = [mock_endpoint]
        mock_client.get_flight_info.return_value = mock_flight_info
        mock_client.authenticate_basic_token.return_value = ("bearer", b"token")

        flight_instance = _SpiceFlight(
            grpc="grpc://localhost:50051",
            api_key="test-key",
            tls_root_certs=b"cert",
        )

        # First call raises unauthenticated, second succeeds
        call_count = [0]
        mock_reader = MagicMock()

        def mock_threaded_do_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise FlightUnauthenticatedError("")
            return mock_reader

        with patch.object(flight_instance, "_threaded_flight_do_get", side_effect=mock_threaded_do_get):
            result = flight_instance.query("SELECT 1")

        assert result == mock_reader
        # authenticate_basic_token called twice: once in init, once for re-auth
        assert mock_client.authenticate_basic_token.call_count == 2

    @patch("spicepy._client.flight")
    def test_spice_flight_authenticate_without_api_key(
        self,
        mock_flight: MagicMock,
    ) -> None:
        """Test _SpiceFlight authentication without API key."""
        from spicepy._client import _SpiceFlight

        mock_client = MagicMock()
        mock_flight.connect.return_value = mock_client

        flight_instance = _SpiceFlight(
            grpc="grpc://localhost:50051",
            api_key=None,
            tls_root_certs=b"cert",
        )

        # authenticate_basic_token should not be called when api_key is None
        mock_client.authenticate_basic_token.assert_not_called()
        # Headers should only contain user-agent
        assert len(flight_instance.headers) == 1
        assert flight_instance.headers[0][0] == b"user-agent"


class TestArrowFlightCallThread:
    """Test _ArrowFlightCallThread class."""

    def test_thread_run_success(self) -> None:
        """Test _ArrowFlightCallThread.run with successful do_get."""
        from spicepy._client import _ArrowFlightCallThread

        mock_flight_client = MagicMock()
        mock_ticket = MagicMock()
        mock_options = MagicMock()
        mock_reader = MagicMock()
        mock_flight_client.do_get.return_value = mock_reader

        thread = _ArrowFlightCallThread(
            flight_client=mock_flight_client,
            ticket=mock_ticket,
            flight_options=mock_options,
        )

        thread.run()

        assert thread.reader == mock_reader
        mock_flight_client.do_get.assert_called_once_with(mock_ticket, mock_options)

    def test_thread_run_exception(self) -> None:
        """Test _ArrowFlightCallThread.run captures exception."""
        from spicepy._client import _ArrowFlightCallThread

        mock_flight_client = MagicMock()
        mock_ticket = MagicMock()
        mock_options = MagicMock()
        mock_flight_client.do_get.side_effect = RuntimeError("Connection failed")

        thread = _ArrowFlightCallThread(
            flight_client=mock_flight_client,
            ticket=mock_ticket,
            flight_options=mock_options,
        )

        thread.run()

        assert thread._exc is not None
        assert isinstance(thread._exc, RuntimeError)

    def test_thread_join_raises_exception(self) -> None:
        """Test _ArrowFlightCallThread.join raises captured exception."""
        from spicepy._client import _ArrowFlightCallThread

        mock_flight_client = MagicMock()
        mock_ticket = MagicMock()
        mock_options = MagicMock()
        mock_flight_client.do_get.side_effect = RuntimeError("Connection failed")

        thread = _ArrowFlightCallThread(
            flight_client=mock_flight_client,
            ticket=mock_ticket,
            flight_options=mock_options,
        )

        # Run the thread method to capture the exception
        thread.run()

        # Mock super().join to prevent "thread not started" error
        with patch.object(threading.Thread, "join"):
            with pytest.raises(RuntimeError, match="Connection failed"):
                thread.join()


class TestIsMacosArm64:
    """Test is_macos_arm64 function."""

    @patch("spicepy._client.platform")
    def test_is_macos_arm64_true(self, mock_platform: MagicMock) -> None:
        """Test is_macos_arm64 returns True on Apple Silicon."""
        from spicepy._client import is_macos_arm64

        mock_platform.platform.return_value = "macOS-14.0-arm64-arm-64bit"
        mock_platform.machine.return_value = "arm64"

        assert is_macos_arm64() is True

    @patch("spicepy._client.platform")
    def test_is_macos_arm64_false_linux(self, mock_platform: MagicMock) -> None:
        """Test is_macos_arm64 returns False on Linux."""
        from spicepy._client import is_macos_arm64

        mock_platform.platform.return_value = "Linux-5.10.0-aarch64"
        mock_platform.machine.return_value = "aarch64"

        assert is_macos_arm64() is False

    @patch("spicepy._client.platform")
    def test_is_macos_arm64_false_intel_mac(self, mock_platform: MagicMock) -> None:
        """Test is_macos_arm64 returns False on Intel Mac."""
        from spicepy._client import is_macos_arm64

        mock_platform.platform.return_value = "macOS-14.0-x86_64"
        mock_platform.machine.return_value = "x86_64"

        assert is_macos_arm64() is False
