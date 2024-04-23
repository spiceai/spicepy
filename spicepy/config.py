import os

DEFAULT_FLIGHT_URL = os.environ.get("SPICE_FLIGHT_URL", "grpc+tls://flight.spiceai.io")
DEFAULT_FIRECACHE_URL = os.environ.get(
    "SPICE_FIRECACHE_URL", "grpc+tls://firecache.spiceai.io"
)
DEFAULT_HTTP_URL = os.environ.get("SPICE_HTTP_URL", "https://data.spiceai.io")
