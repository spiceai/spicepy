"""Comprehensive unit tests for spicepy._client module."""

from __future__ import annotations

from collections.abc import Iterator
import gc
import os
from pathlib import Path
import threading
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

        client = Client(
            flight_url="grpc+tls://custom.spiceai.io",
            http_url="https://custom-data.spiceai.io",
        )

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

        mock_adbc.query_with_params.assert_called_once_with(
            "SELECT * FROM t WHERE id = $1", [42]
        )
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


class TestADBCClientStreaming:
    """_ADBCClient.query_with_params must stream, not buffer the whole result."""

    SCHEMA = pa.schema([pa.field("a", pa.int64())])

    @staticmethod
    def _adbc_client(mock_manager: MagicMock, mock_flightsql: MagicMock) -> _ADBCClient:
        mock_flightsql.connect.return_value = MagicMock()
        mock_manager.AdbcConnection.return_value = MagicMock()
        return _ADBCClient("grpc://localhost:50051")

    @classmethod
    def _source(cls, pulled: list[int], count: int = 3) -> pa.RecordBatchReader:
        """A reader that records each batch as it is pulled off the wire."""

        def batches() -> Iterator[pa.RecordBatch]:
            for i in range(count):
                pulled.append(i)
                yield pa.record_batch(
                    [pa.array([i], type=pa.int64())], schema=cls.SCHEMA
                )

        return pa.RecordBatchReader.from_batches(cls.SCHEMA, batches())

    @pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC not installed")
    @patch("spicepy._client.adbc_driver_flightsql")
    @patch("spicepy._client.adbc_driver_manager")
    def test_query_with_params_does_not_buffer_result(
        self,
        mock_manager: MagicMock,
        mock_flightsql: MagicMock,
    ) -> None:
        """Returning the reader must not drain the result stream first."""
        client = self._adbc_client(mock_manager, mock_flightsql)
        pulled: list[int] = []
        stmt = MagicMock()
        # A real reader stands in for the ADBC result handle; from_stream()
        # consumes it lazily through the Arrow C stream interface.
        stmt.execute_query.return_value = (self._source(pulled), None)
        mock_manager.AdbcStatement.return_value = stmt

        reader = client.query_with_params("SELECT * FROM t WHERE a = $1", [])

        # The whole result must not have been read just to hand back a reader.
        assert pulled != [0, 1, 2], "result was buffered instead of streamed"
        # The statement owns the stream, so it stays open while the caller reads.
        stmt.close.assert_not_called()

        reader.read_next_batch()
        assert pulled == [0]
        stmt.close.assert_not_called()

    @pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC not installed")
    @patch("spicepy._client.adbc_driver_flightsql")
    @patch("spicepy._client.adbc_driver_manager")
    def test_query_with_params_yields_all_batches_and_closes_statement(
        self,
        mock_manager: MagicMock,
        mock_flightsql: MagicMock,
    ) -> None:
        """Draining the reader yields every batch, then releases the statement."""
        client = self._adbc_client(mock_manager, mock_flightsql)
        pulled: list[int] = []
        stmt = MagicMock()
        # A real reader stands in for the ADBC result handle; from_stream()
        # consumes it lazily through the Arrow C stream interface.
        stmt.execute_query.return_value = (self._source(pulled), None)
        mock_manager.AdbcStatement.return_value = stmt

        reader = client.query_with_params("SELECT * FROM t WHERE a = $1", [])

        table = reader.read_all()

        assert table.num_rows == 3
        assert table.column("a").to_pylist() == [0, 1, 2]
        assert pulled == [0, 1, 2]
        stmt.close.assert_called_once()

    @pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC not installed")
    @patch("spicepy._client.adbc_driver_flightsql")
    @patch("spicepy._client.adbc_driver_manager")
    def test_query_with_params_closes_statement_on_error(
        self,
        mock_manager: MagicMock,
        mock_flightsql: MagicMock,
    ) -> None:
        """A failure before the stream exists must still release the statement."""
        client = self._adbc_client(mock_manager, mock_flightsql)
        stmt = MagicMock()
        stmt.execute_query.side_effect = RuntimeError("boom")
        mock_manager.AdbcStatement.return_value = stmt

        with pytest.raises(RuntimeError, match="boom"):
            client.query_with_params("SELECT * FROM t WHERE a = $1", [])

        stmt.close.assert_called_once()

    @pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC not installed")
    @patch("spicepy._client.adbc_driver_flightsql")
    @patch("spicepy._client.adbc_driver_manager")
    def test_query_with_params_closes_statement_when_abandoned(
        self,
        mock_manager: MagicMock,
        mock_flightsql: MagicMock,
    ) -> None:
        """Closing the reader early must not leak the statement."""
        client = self._adbc_client(mock_manager, mock_flightsql)
        pulled: list[int] = []
        stmt = MagicMock()
        # A real reader stands in for the ADBC result handle; from_stream()
        # consumes it lazily through the Arrow C stream interface.
        stmt.execute_query.return_value = (self._source(pulled), None)
        mock_manager.AdbcStatement.return_value = stmt

        reader = client.query_with_params("SELECT * FROM t WHERE a = $1", [])

        reader.read_next_batch()
        reader.close()
        del reader
        gc.collect()

        stmt.close.assert_called_once()

    def test_statement_is_released_even_if_reader_close_raises(self) -> None:
        """A failing reader.close() must not leak the statement."""
        from spicepy._client import _stream_until_closed

        class FailingCloseReader:
            schema = TestADBCClientStreaming.SCHEMA

            def __iter__(self) -> Iterator[pa.RecordBatch]:
                return iter(())

            def close(self) -> None:
                raise OSError("close failed")

        stmt = MagicMock()

        with pytest.raises(OSError, match="close failed"):
            _stream_until_closed(FailingCloseReader(), stmt).read_all()

        stmt.close.assert_called_once()


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
        with patch.object(
            flight_instance, "_threaded_flight_do_get", return_value=mock_reader
        ):
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
        with patch.object(
            flight_instance, "_threaded_flight_do_get", return_value=mock_reader
        ):
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

        with patch.object(
            flight_instance, "_threaded_flight_do_get", side_effect=mock_threaded_do_get
        ):
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

    @patch("spicepy._client.flight")
    def test_spice_flight_authenticate_with_empty_string_api_key(
        self,
        mock_flight: MagicMock,
    ) -> None:
        """Test _SpiceFlight authentication with empty string API key.

        Empty string API key should be treated the same as None - no authentication
        should be attempted. This prevents gRPC errors like 'Metadata keys cannot
        be zero length' that occur when authenticate_basic_token is called with
        empty credentials.
        """
        from spicepy._client import _SpiceFlight

        mock_client = MagicMock()
        mock_flight.connect.return_value = mock_client

        flight_instance = _SpiceFlight(
            grpc="grpc://localhost:50051",
            api_key="",
            tls_root_certs=b"cert",
        )

        # authenticate_basic_token should not be called when api_key is empty string
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


class TestClientQueryHelpers:
    """Test Client query_arrow / query_pandas / query_polars / query_pylist."""

    @staticmethod
    def _sample_table() -> pa.Table:
        return pa.table({"id": [1, 2, 3], "name": ["a", "b", "c"]})

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_query_arrow_returns_table(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        table = self._sample_table()
        mock_reader = MagicMock()
        mock_reader.read_all.return_value = table
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        result = client.query_arrow("SELECT * FROM t")

        assert result is table
        mock_flight.query.assert_called_once_with("SELECT * FROM t")

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_query_arrow_passes_timeout(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_reader = MagicMock()
        mock_reader.read_all.return_value = self._sample_table()
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        client.query_arrow("SELECT 1", timeout=30)

        mock_flight.query.assert_called_once_with("SELECT 1", timeout=30)

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    @patch("spicepy._client._ADBCClient")
    def test_query_arrow_routes_params_to_adbc(
        self,
        mock_adbc_class: MagicMock,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        table = self._sample_table()
        adbc_reader = MagicMock()
        adbc_reader.read_all.return_value = table
        mock_adbc = MagicMock()
        mock_adbc.query_with_params.return_value = adbc_reader
        mock_adbc_class.return_value = mock_adbc

        flight_instance = MagicMock()
        mock_flight_class.return_value = flight_instance

        client = Client()
        result = client.query_arrow("SELECT * FROM t WHERE id = $1", params=[1])

        assert result is table
        mock_adbc.query_with_params.assert_called_once_with(
            "SELECT * FROM t WHERE id = $1", [1]
        )
        flight_instance.query.assert_not_called()

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_query_pandas_returns_dataframe(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        import pandas as pd

        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_reader = MagicMock()
        mock_reader.read_all.return_value = self._sample_table()
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        df = client.query_pandas("SELECT * FROM t")

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["id", "name"]
        assert len(df) == 3

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_query_pylist_returns_row_dicts(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_reader = MagicMock()
        mock_reader.read_all.return_value = self._sample_table()
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        rows = client.query_pylist("SELECT * FROM t")

        assert rows == [
            {"id": 1, "name": "a"},
            {"id": 2, "name": "b"},
            {"id": 3, "name": "c"},
        ]

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_query_polars_returns_dataframe(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        pl = pytest.importorskip("polars")

        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_reader = MagicMock()
        mock_reader.read_all.return_value = self._sample_table()
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        df = client.query_polars("SELECT * FROM t")

        assert isinstance(df, pl.DataFrame)
        assert df.columns == ["id", "name"]
        assert df.height == 3

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_query_polars_missing_raises_importerror(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_reader = MagicMock()
        mock_reader.read_all.return_value = self._sample_table()
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()

        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "polars":
                raise ImportError("No module named 'polars'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(ImportError, match="polars is not installed"):
                client.query_polars("SELECT 1")


class TestClientCatalog:
    """Test catalog introspection helpers (catalogs/schemas/tables/describe/get_schema)."""

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_catalogs(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_reader = MagicMock()
        mock_reader.read_all.return_value = pa.table(
            {"catalog_name": ["default", "other"]}
        )
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        result = client.catalogs()
        assert result == ["default", "other"]
        sql = mock_flight.query.call_args[0][0]
        assert "information_schema.schemata" in sql

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_schemas_no_filter(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_reader = MagicMock()
        mock_reader.read_all.return_value = pa.table(
            {"schema_name": ["public", "info"]}
        )
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        assert client.schemas() == ["public", "info"]

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_schemas_filtered(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_reader = MagicMock()
        mock_reader.read_all.return_value = pa.table({"schema_name": ["public"]})
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        client.schemas(catalog="default")
        sql = mock_flight.query.call_args[0][0]
        assert "WHERE catalog_name = 'default'" in sql

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_tables_filtered(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_reader = MagicMock()
        mock_reader.read_all.return_value = pa.table({"table_name": ["trips"]})
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        client.tables(schema="public")
        sql = mock_flight.query.call_args[0][0]
        assert "table_schema = 'public'" in sql

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_describe(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_reader = MagicMock()
        mock_reader.read_all.return_value = pa.table(
            {"column_name": ["a"], "data_type": ["INT"]}
        )
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        client.describe("trips")
        sql = mock_flight.query.call_args[0][0]
        assert sql == 'DESCRIBE "trips"'

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_get_schema(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        sample = pa.table({"a": [1]}, schema=pa.schema([("a", pa.int64())]))
        mock_reader = MagicMock()
        mock_reader.read_all.return_value = sample
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        schema = client.get_schema("SELECT 1 AS a")
        assert schema == sample.schema
        sql = mock_flight.query.call_args[0][0]
        assert "LIMIT 0" in sql


class TestClientExplain:
    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_explain_basic(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_reader = MagicMock()
        mock_reader.read_all.return_value = pa.table(
            {"plan_type": ["logical_plan"], "plan": ["Projection: ..."]}
        )
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        text = client.explain("SELECT 1")
        assert "Projection" in text
        sql = mock_flight.query.call_args[0][0]
        assert sql.startswith("EXPLAIN ")

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_explain_analyze_verbose(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_reader = MagicMock()
        mock_reader.read_all.return_value = pa.table({"plan": ["..."]})
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        client.explain("SELECT 1", analyze=True, verbose=True)
        sql = mock_flight.query.call_args[0][0]
        assert "EXPLAIN ANALYZE VERBOSE" in sql


class TestClientBatchesAndPydict:
    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_query_pydict(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        mock_reader = MagicMock()
        mock_reader.read_all.return_value = pa.table({"a": [1, 2], "b": ["x", "y"]})
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        result = client.query_pydict("SELECT * FROM t")
        assert result == {"a": [1, 2], "b": ["x", "y"]}

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_query_batches_yields_batches(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        batch1 = pa.record_batch({"x": [1, 2]})
        batch2 = pa.record_batch({"x": [3, 4]})
        # FlightStreamChunk-like shape: object with `.data` attribute.
        chunk1 = MagicMock()
        chunk1.data = batch1
        chunk2 = MagicMock()
        chunk2.data = batch2
        mock_reader = MagicMock()
        mock_reader.__iter__.return_value = iter([chunk1, chunk2])
        mock_flight = MagicMock()
        mock_flight.query.return_value = mock_reader
        mock_flight_class.return_value = mock_flight

        client = Client()
        batches = list(client.query_batches("SELECT 1"))
        assert batches == [batch1, batch2]

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    @patch("spicepy._client._ADBCClient")
    def test_query_batches_with_params_streams(
        self,
        mock_adbc_class: MagicMock,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        """Parameterized batch streaming goes through the ADBC reader."""
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        batch1 = pa.record_batch({"x": [1, 2]})
        batch2 = pa.record_batch({"x": [3, 4]})
        mock_adbc = MagicMock()
        mock_adbc.query_with_params.return_value = iter([batch1, batch2])
        mock_adbc_class.return_value = mock_adbc

        client = Client()
        batches = list(client.query_batches("SELECT * FROM t WHERE x > $1", params=[0]))

        assert batches == [batch1, batch2]
        mock_adbc.query_with_params.assert_called_once_with(
            "SELECT * FROM t WHERE x > $1", [0]
        )


class TestClientDataFrameEntry:
    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_table_returns_dataframe(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        from spicepy import SpiceDataFrame

        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client()
        df = client.table("trips")
        assert isinstance(df, SpiceDataFrame)
        assert df.to_sql() == 'SELECT * FROM "trips"'

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_sql_returns_dataframe(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        from spicepy import SpiceDataFrame

        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client()
        df = client.sql("SELECT 1")
        assert isinstance(df, SpiceDataFrame)
        assert df.to_sql() == "SELECT 1"

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_from_arrow(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client()
        table = pa.table({"a": [1, 2], "b": ["x", "y"]})
        df = client.from_arrow(table)
        sql = df.to_sql()
        assert "VALUES" in sql and "(1, 'x')" in sql

    @patch("spicepy._client._SpiceFlight")
    @patch("spicepy._client._Cert")
    def test_from_pydict(
        self,
        mock_cert_class: MagicMock,
        mock_flight_class: MagicMock,
    ) -> None:
        mock_cert = MagicMock()
        mock_cert.tls_root_certs = b"cert"
        mock_cert_class.return_value = mock_cert

        client = Client()
        df = client.from_pydict({"a": [1], "b": [2]})
        assert "VALUES" in df.to_sql()


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
