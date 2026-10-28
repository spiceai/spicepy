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
