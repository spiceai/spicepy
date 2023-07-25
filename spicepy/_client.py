from pathlib import Path
import platform
import threading
from typing import Union

import certifi
from pyarrow._flight import FlightCallOptions, FlightClient, Ticket  # pylint: disable=E0611


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


class _Cert:
    def __init__(
        self,
        tls_root_cert,
    ):
        if tls_root_cert is not None:
            tls_root_cert = (
                tls_root_cert
                if isinstance(tls_root_cert, Path)
                else Path(tls_root_cert)
            )
        else:
            tls_root_cert = Path(certifi.where())

        self.tls_root_certs = self.read_cert(tls_root_cert)

    def read_cert(self, tls_root_cert):
        with open(tls_root_cert, 'rb') as cert_file:
            return cert_file.read()


class _SpiceFlight:
    def __init__(
        self,
        grpc: str,
        api_key: str,
        tls_root_certs
    ):
        self._flight_client = flight.connect(grpc, tls_root_certs=tls_root_certs)
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
            reader = self._threaded_flight_do_get(ticket=flight_info.endpoints[0].ticket)
        except flight.FlightUnauthenticatedError:
            self._authenticate()
            reader = self._threaded_flight_do_get(ticket=flight_info.endpoints[0].ticket)
        except flight.FlightTimedOutError as exc:
            raise TimeoutError(f"Query timed out and was canceled after {timeout} seconds.") from exc

        return reader

    def _threaded_flight_do_get(self, ticket: Ticket):
        thread = _ArrowFlightCallThread(
            ticket=ticket,
            flight_options=self._flight_options,
            flight_client=self._flight_client
        )
        thread.start()
        while thread.is_alive():
            thread.join(1)

        return thread.reader


class Client:
    def __init__(
        self,
        api_key: str,
        flight_url: str = "grpc+tls://flight.spiceai.io",
        firecache_url: str = "grpc+tls://firecache.spiceai.io",
        tls_root_cert: Union[str, Path, None] = None,
    ):
        tls_root_certs = _Cert(tls_root_cert).tls_root_certs
        self._flight = _SpiceFlight(flight_url, api_key, tls_root_certs)
        self._firecache = _SpiceFlight(firecache_url, api_key, tls_root_certs)

    def query(self, query: str, **kwargs) -> flight.FlightStreamReader:
        return self._flight.query(query, **kwargs)

    def fire_query(self, query: str, **kwargs) -> flight.FlightStreamReader:
        return self._firecache.query(query, **kwargs)


class _ArrowFlightCallThread(threading.Thread):
    def __init__(
            self,
            flight_client: FlightClient,
            ticket: Ticket,
            flight_options: FlightCallOptions
    ):
        super().__init__()
        self._exc = None
        self._flight_client = flight_client
        self._ticket = ticket
        self._flight_options = flight_options
        self.reader = None

    def run(self):
        try:
            self.reader = self._flight_client.do_get(self._ticket, self._flight_options)
        except BaseException as exc:  # pylint: disable=W0718
            self._exc = exc

    def join(self, timeout=None):
        super().join(timeout)
        if self._exc:
            raise self._exc
