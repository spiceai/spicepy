from pathlib import Path
import platform
from typing import Union
import certifi

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
        tls_root_cert: Union[str, Path, None] = None,
    ):
        if tls_root_cert is not None:
            tls_root_cert = (
                tls_root_cert
                if isinstance(tls_root_cert, Path)
                else Path(tls_root_cert)
            )
        else:
            tls_root_cert = Path(certifi.where())

        with open(tls_root_cert, 'rb') as cert_file:
            self._flight_client = flight.connect(url, tls_root_certs=cert_file.read())
        self._api_key = api_key
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
            raise TimeoutError(f"Query timed out and was canceled after {timeout} seconds.") from exc

        return reader
