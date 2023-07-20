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


class Client:
    def __init__(
        self,
        api_key: str,
        flight_url: str = "grpc+tls://flight.spiceai.io",
        firecache_url: str = "grpc+tls://firecache.spiceai.io",
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
            certs = cert_file.read()
            self._flight_client = flight.connect(flight_url, tls_root_certs=certs)
            self._firecache_client = flight.connect(firecache_url, tls_root_certs=certs)
            self._api_key = api_key
            self._flight_options = flight.FlightCallOptions()
            self._firecache_options = flight.FlightCallOptions()
            self._authenticate()

    def _authenticate(self):
        self.flight_headers = [self._flight_client.authenticate_basic_token("", self._api_key)]
        self.firecache_headers = [self._firecache_client.authenticate_basic_token("", self._api_key)]
        self._flight_options = flight.FlightCallOptions(headers=self.flight_headers, timeout=DEFAULT_QUERY_TIMEOUT_SECS)
        self._firecache_options = flight.FlightCallOptions(headers=self.firecache_headers,
                                                           timeout=DEFAULT_QUERY_TIMEOUT_SECS)

    # Create a generic query method, opt can be "flight" or "firequery"
    def _option_query(self, opt: str, query: str, **kwargs) -> flight.FlightStreamReader:
        opt_options = '_' + opt + '_options'
        opt_headers = opt + '_headers'
        opt_client = '_' + opt + '_client'

        timeout = kwargs.get("timeout", None)

        if timeout is not None:
            if not isinstance(timeout, int) or timeout <= 0:
                raise ValueError("Timeout must be a positive integer")
            setattr(self, opt_options,
                    flight.FlightCallOptions(headers=getattr(self, opt_headers), timeout=timeout))

        flight_info = getattr(self, opt_client).get_flight_info(
            flight.FlightDescriptor.for_command(query),
            getattr(self, opt_options)
        )

        try:
            reader = self._threaded_flight_do_get(opt, ticket=flight_info.endpoints[0].ticket)
        except flight.FlightUnauthenticatedError:
            self._authenticate()
            reader = self._threaded_flight_do_get(opt, ticket=flight_info.endpoints[0].ticket)
        except flight.FlightTimedOutError as exc:
            raise TimeoutError(f"Query timed out and was canceled after {timeout} seconds.") from exc

        return reader

    def query(self, query: str, **kwargs) -> flight.FlightStreamReader:
        return self._option_query('flight', query, **kwargs)

    def fire_query(self, query: str, **kwargs) -> flight.FlightStreamReader:
        return self._option_query('firecache', query, **kwargs)

    def _threaded_flight_do_get(self, opt: str, ticket: Ticket):
        thread = _ArrowFlightCallThread(
            ticket=ticket,
            flight_options=getattr(self, '_' + opt + '_options'),
            flight_client=getattr(self, '_' + opt + '_client')
        )
        thread.start()
        while thread.is_alive():
            thread.join(1)

        return thread.reader

    def _threaded_firecache_do_get(self, ticket: Ticket):
        thread = _ArrowFlightCallThread(
            ticket=ticket,
            flight_options=self._firecache_options,
            flight_client=self._firecache_client
        )
        thread.start()
        while thread.is_alive():
            thread.join(1)

        return thread.reader


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
