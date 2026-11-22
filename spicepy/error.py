import requests


class SpiceAIError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return f"Spice AI error: {self.message}"


class SpiceTLSError(SpiceAIError, requests.exceptions.SSLError):
    """The runtime's TLS certificate could not be verified.

    Raised instead of retrying: a certificate the client doesn't trust won't
    become trusted on a later attempt. Also a ``requests.exceptions.SSLError``,
    so code that already catches that keeps working.
    """


class SpiceConnectionError(SpiceAIError, requests.exceptions.ConnectionError):
    """The runtime's HTTP endpoint could not be reached.

    Raised when a connection is refused, the host cannot be resolved, or the
    connection attempt times out, after any configured retries. Also a
    ``requests.exceptions.ConnectionError``, so code that already catches that
    keeps working.
    """


class SpiceConnectTimeoutError(
    SpiceConnectionError, requests.exceptions.ConnectTimeout
):
    """The connection attempt to the runtime's HTTP endpoint timed out.

    A ``SpiceConnectionError`` that is also a ``requests.exceptions.ConnectTimeout``
    (and so a ``requests.exceptions.Timeout``), so code that already catches
    either keeps working.
    """
