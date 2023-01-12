import os
from pathlib import Path
import platform
import ssl
import tempfile
from typing import Union
from urllib.request import urlretrieve


def is_macos_arm64() -> bool:
    return platform.platform().lower().startswith("macos") and platform.machine() == "arm64"


try:
    from pyarrow import flight
except (ImportError, ModuleNotFoundError) as error:
    if is_macos_arm64():
        raise ImportError(
            "Failed to import pyarrow. Detected Apple M1 system."
            " Installation of pyarrow on Apple M1 systems requires additional steps."
            " See https://docs.spice.xyz/sdks/python-sdk#m1-macs.") from error
    raise error from error

DEFAULT_QUERY_TIMEOUT_SECS = 10*60


class Client:
    def __init__(
        self,
        api_key: str,
        url: str = "grpc+tls://flight.spiceai.io",
        tls_root_cert: Union[str, Path] = None,
    ):
        cert_path = (
            Path(Path.cwd().absolute().anchor) / "usr" / "share" / "grpc" / "roots.pem"
        )
        if tls_root_cert is not None:
            tls_root_cert = (
                tls_root_cert
                if isinstance(tls_root_cert, Path)
                else Path(tls_root_cert)
            )
        self.root_cert = None
        if not cert_path.exists():
            env_name = "GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"
            if env_name not in os.environ or not Path(os.environ[env_name]).exists():
                temp_cert_path = Path(tempfile.gettempdir()) / "isrgrootx1.pem"
                if not Path(temp_cert_path).exists():
                    ssl._create_default_https_context = ssl._create_unverified_context
                    urlretrieve("https://letsencrypt.org/certs/isrgrootx1.pem", str(temp_cert_path))
                with open(temp_cert_path, 'rb') as cert_file:
                    self.root_cert = cert_file.read()

        self._api_key = api_key
        self._flight_client = flight.connect(url, tls_root_certs=self.root_cert)
        self._flight_options = flight.FlightCallOptions()
        self._authenticate()

    def _authenticate(self):
        self.headers = [self._flight_client.authenticate_basic_token("", self._api_key)]
        self._flight_options = flight.FlightCallOptions(headers=self.headers, timeout=DEFAULT_QUERY_TIMEOUT_SECS)

    def query(self, query: str, **kwargs) -> flight.FlightStreamReader:
        timeout = kwargs.get("timeout", None)
        if timeout is not None:
            if not isinstance(timeout, int) or timeout <= 0:
                raise ValueError("Timeout must be a positive integer")
            self._flight_options = flight.FlightCallOptions(headers=self.headers, timeout=timeout)
        flight_info = self._flight_client.get_flight_info(
            flight.FlightDescriptor.for_command(query), self._flight_options
        )
        try:
            reader = self._flight_client.do_get(
                flight_info.endpoints[0].ticket, self._flight_options
            )
        except flight.FlightUnauthenticatedError:
            self._authenticate()
            reader = self._flight_client.do_get(
                flight_info.endpoints[0].ticket, self._flight_options
            )
        except flight.FlightTimedOutError as exc:
            self._flight_client.cancel(flight_info.endpoints[0].ticket, self._flight_options)
            raise TimeoutError(f"Flight request timed out: {timeout}") from exc

        return reader
