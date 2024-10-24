import os
import platform
from importlib.metadata import version

DEFAULT_FLIGHT_URL = os.environ.get("SPICE_FLIGHT_URL", "grpc+tls://flight.spiceai.io")
DEFAULT_HTTP_URL = os.environ.get("SPICE_HTTP_URL", "https://data.spiceai.io")

DEFAULT_LOCAL_FLIGHT_URL = os.environ.get(
    "SPICE_LOCAL_FLIGHT_URL", "grpc://localhost:50051"
)
DEFAULT_LOCAL_HTTP_URL = os.environ.get("SPICE_LOCAL_HTTP_URL", "http://localhost:8090")


def get_user_agent():
    package_version = version("spicepy")
    system = platform.system()
    release = platform.release()
    arch = platform.machine()
    if arch == "AMD64":
        arch = "x86_64"

    system_info = f"{system}/{release} {arch}"
    return f"spicepy {package_version} ({system_info})"


SPICE_USER_AGENT = get_user_agent()
