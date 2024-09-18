import os
import platform
from importlib.metadata import version

DEFAULT_FLIGHT_URL = os.environ.get("SPICE_FLIGHT_URL", "grpc+tls://flight.spiceai.io")
DEFAULT_FIRECACHE_URL = os.environ.get(
    "SPICE_FIRECACHE_URL", "grpc+tls://firecache.spiceai.io"
)
DEFAULT_HTTP_URL = os.environ.get("SPICE_HTTP_URL", "https://data.spiceai.io")

DEFAULT_LOCAL_FLIGHT_URL = os.environ.get(
    "SPICE_LOCAL_FLIGHT_URL", "grpc://localhost:50051"
)
DEFAULT_LOCAL_HTTP_URL = os.environ.get(
    "SPICE_LOCAL_HTTP_URL", "http://localhost:3000 "
)


def get_user_agent():
    package_version = version("spicepy")
    system = platform.system()
    release = platform.release()
    arch = platform.architecture()[0]
    if arch == "32bit":  # expect a shorthand x32 or x64
        arch = "x86"
    elif arch == "64bit":
        arch = "x86_64"

    system_info = f"{system}/{release} {arch}"
    return f"spicepy {package_version} {system_info}"


SPICE_USER_AGENT = get_user_agent()
