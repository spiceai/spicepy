import os
from pathlib import Path
import ssl
import tempfile
from typing import Union
from urllib.request import urlretrieve

import pandas as pd
from pyarrow import flight


class Client:
    def __init__(self, api_key: str, url: str = 'grpc+tls://flight.spiceai.io', tls_root_cert: Union[str, Path] = None):
        cert_path = Path(Path.cwd().absolute().anchor) / 'usr' / 'share' / 'grpc' / 'roots.pem'
        if tls_root_cert is not None:
            tls_root_cert = tls_root_cert if isinstance(tls_root_cert, Path) else Path(tls_root_cert)
        if not cert_path.exists():
            env_name = 'GRPC_DEFAULT_SSL_ROOTS_FILE_PATH'
            if env_name not in os.environ or not Path(os.environ[env_name]).exists():
                temp_cert_path = Path(tempfile.gettempdir()) / 'roots.pem'
                if not Path(temp_cert_path).exists():
                    ssl._create_default_https_context = ssl._create_unverified_context
                    urlretrieve('https://pki.google.com/roots.pem', str(temp_cert_path))
                os.environ[env_name] = str(temp_cert_path)

        self._flight_client = flight.connect(url)
        headers = [self._flight_client.authenticate_basic_token('', api_key)]
        self._flight_options = flight.FlightCallOptions(headers=headers)

    def query(self, query: str) -> pd.DataFrame:
        flight_info = self._flight_client.get_flight_info(
            flight.FlightDescriptor.for_command(query), self._flight_options)
        reader = self._flight_client.do_get(flight_info.endpoints[0].ticket, self._flight_options)
        return reader.read_pandas()
