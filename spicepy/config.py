import os
import platform
from importlib.metadata import version
from typing import Optional


DEFAULT_FLIGHT_URL = os.environ.get("SPICE_FLIGHT_URL", "grpc+tls://flight.spiceai.io")
DEFAULT_HTTP_URL = os.environ.get("SPICE_HTTP_URL", "https://data.spiceai.io")

DEFAULT_LOCAL_FLIGHT_URL = os.environ.get("SPICE_LOCAL_FLIGHT_URL", "grpc://localhost:50051")
DEFAULT_LOCAL_HTTP_URL = os.environ.get("SPICE_LOCAL_HTTP_URL", "http://localhost:8090")


###
# Get the default `User-Agent` string, or build a custom one
#
# client_name: Optional[str] = None : The name of the client. Default is `spicepy`.
# client_version: Optional[str] = None : The version of the client. Default is the version of the `spicepy` package.
# client_system: Optional[str] = None : The system information of the client.
#   Default is the system information of the current system, e.g. `Linux/5.4.0-1043-aws x86_64`.
###
def get_user_agent(
    client_name: Optional[str] = None, client_version: Optional[str] = None, client_system: Optional[str] = None
) -> str:
    package_version = version("spicepy") if client_version is None else client_version
    system = platform.system()
    release = platform.release()
    arch = platform.machine()
    if arch == "AMD64":
        arch = "x86_64"

    system_info = f"{system}/{release} {arch}" if client_system is None else client_system
    client = "spicepy" if client_name is None else client_name
    return f"{client}/{package_version} ({system_info})"


SPICE_USER_AGENT = get_user_agent()
