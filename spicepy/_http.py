from collections.abc import Callable
from dataclasses import dataclass
import datetime
import json
from pathlib import Path
import ssl
from typing import Any, Literal

from requests import Response, Session
from requests.adapters import HTTPAdapter, Retry
import requests.exceptions
from urllib3.exceptions import MaxRetryError
from urllib3.exceptions import SSLError as Urllib3SSLError

from .config import SPICE_USER_AGENT
from .error import SpiceAIError, SpiceTLSError


@dataclass
class RefreshOpts:
    refresh_sql: str | None = None
    refresh_mode: str | None = None
    refresh_jitter_max: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "refresh_sql": self.refresh_sql,
            "refresh_mode": self.refresh_mode,
            "refresh_jitter_max": self.refresh_jitter_max,
        }


def _certificate_error(exc: BaseException) -> ssl.SSLCertVerificationError | None:
    """Find the certificate verification failure under the wrappers requests and
    urllib3 add, or None when the TLS error is something else (e.g. the peer
    closing the connection mid-handshake).
    """
    seen: set[int] = set()
    pending: list[BaseException] = [exc]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return current
        pending.extend(arg for arg in current.args if isinstance(arg, BaseException))
        reason = getattr(current, "reason", None)
        if isinstance(reason, BaseException):
            pending.append(reason)
        for linked in (current.__cause__, current.__context__):
            if linked is not None:
                pending.append(linked)
    return None


class _Retry(Retry):
    """Retry transient failures, but not a certificate verification failure.

    urllib3 counts an SSL error against ``total`` like any other error, so an
    untrusted certificate was retried with backoff for about a minute before
    the caller heard about it. Certificate verification is deterministic: the
    next attempt fails the same way. Other TLS errors, such as an abrupt close
    by a load balancer, can be transient and keep the normal retries.
    """

    def increment(  # type: ignore[override]  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        method=None,
        url=None,
        response=None,
        error=None,
        _pool=None,
        _stacktrace=None,
    ):
        if isinstance(error, Urllib3SSLError) and _certificate_error(error):
            raise MaxRetryError(_pool, url, error) from error
        return super().increment(method, url, response, error, _pool, _stacktrace)


HttpMethod = Literal["GET", "POST", "PUT", "HEAD", "DELETE"]


def runtime_error_detail(response: Response) -> str:
    """Return the runtime's own explanation for a failed response, if it gave one.

    The runtime answers most `/v1/*` errors with a JSON object carrying a
    ``message`` — ``{"message": "Dataset taxi_trips not found"}`` — and some with
    a bare text body. Both say what the caller got wrong, so both are worth
    keeping; ``requests.Response.raise_for_status`` keeps neither.
    """
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()

    return (response.text or "").strip()


def raise_for_runtime_error(response: Response, path: str) -> None:
    """Raise `SpiceAIError` for a non-2xx response, carrying what the runtime said.

    Raised in place of `requests.HTTPError` so callers catch one exception type
    from this package rather than one from its HTTP dependency.
    """
    if response.ok:
        return

    detail = runtime_error_detail(response)
    raise SpiceAIError(
        f"{path} failed with status {response.status_code}"
        + (f": {detail}" if detail else "")
    )


class HttpRequests:
    def __init__(
        self,
        base_url: str,
        headers: dict[str, str],
        tls_client_certificate: str | Path | None = None,
        tls_client_key: str | Path | None = None,
        tls_root_cert: str | Path | None = None,
    ) -> None:
        self.session = self._create_session(headers)

        # Verify the runtime against the caller's CA when one is given, else
        # against the default bundle (certifi, or REQUESTS_CA_BUNDLE). Passed on
        # each request rather than set as session.verify, which requests lets
        # REQUESTS_CA_BUNDLE override.
        self.verify: str | bool = (
            str(tls_root_cert) if tls_root_cert is not None else True
        )

        # set the user-agent header
        if "user-agent" not in self.session.headers:
            self.session.headers["user-agent"] = SPICE_USER_AGENT

        # Configure client certificate for mTLS on HTTP requests
        if tls_client_certificate is not None and tls_client_key is not None:
            self.session.cert = (str(tls_client_certificate), str(tls_client_key))

        self.base_url = base_url

    # pylint: disable=R0913
    # pylint: disable=R0917
    def send_request(
        self,
        method: HttpMethod,
        path: str,
        param: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        body: str | None = None,
    ) -> Any:
        if headers is None:
            headers = {}

        headers.update(self.session.headers)

        response: Response = self._call(
            self._operation(method),
            url=f"{self.base_url}{path}",
            data=body,
            params=self.prepare_param(param.copy()) if param is not None else None,
            headers=headers,
        )
        raise_for_runtime_error(response, path)

        try:
            return response.json()
        except ValueError as exc:
            raise SpiceAIError(
                f"{path} returned a response that was not valid JSON"
            ) from exc

    def post_json(
        self, path: str, payload: dict[str, Any], accept: str | None = None
    ) -> Any:
        """POST a JSON payload and decode the JSON response.

        A failed request raises `SpiceAIError` carrying the runtime's own
        explanation.

        `accept` selects a response representation where an endpoint offers
        more than one.
        """
        response = self.post_raw(path, payload, accept)

        try:
            return response.json()
        except ValueError as exc:
            raise SpiceAIError(
                f"{path} returned a response that was not valid JSON"
            ) from exc

    def post_text(
        self, path: str, payload: dict[str, Any], accept: str | None = None
    ) -> str:
        """POST a JSON payload and return the response body as text.

        For endpoints that answer some media types with something other than
        JSON — ``/v1/nsql`` returns bare SQL for ``application/sql``.
        """
        return self.post_raw(path, payload, accept).text.strip()

    def post_raw(
        self, path: str, payload: dict[str, Any], accept: str | None = None
    ) -> Response:
        """POST a JSON payload, raising `SpiceAIError` on a non-2xx status."""
        headers = dict(self.session.headers)
        headers["Content-Type"] = "application/json"
        if accept is not None:
            headers["Accept"] = accept

        response: Response = self._call(
            self.session.post,
            url=f"{self.base_url}{path}",
            data=json.dumps(payload),
            headers=headers,
        )

        raise_for_runtime_error(response, path)

        return response

    # pylint: disable=R0913
    # pylint: disable=R0917
    def send_request_raw(
        self,
        method: HttpMethod,
        path: str,
        param: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        body: str | None = None,
    ) -> Response:
        """Send a request and return the raw ``Response``.

        Unlike :meth:`send_request`, this neither raises on a non-2xx status nor
        decodes JSON. Needed for endpoints whose status code carries the meaning
        (``/v1/ready`` answers ``503`` for "not ready") or whose body is not JSON.
        """
        merged_headers = dict(headers) if headers is not None else {}
        merged_headers.update(self.session.headers)

        return self._call(
            self._operation(method),
            url=f"{self.base_url}{path}",
            data=body,
            params=self.prepare_param(param.copy()) if param is not None else None,
            headers=merged_headers,
        )

    def _call(self, operation: Callable[..., Response], url: str, **kwargs) -> Response:
        """Send one request, verifying TLS against the configured CA.

        A certificate verification failure raises `SpiceTLSError` naming the URL
        and the reason, rather than a raw ``requests`` exception. Other TLS
        errors are retried as before and re-raised unchanged.
        """
        try:
            return operation(url=url, verify=self.verify, **kwargs)
        except requests.exceptions.SSLError as exc:
            cert_error = _certificate_error(exc)
            if cert_error is None:
                raise
            hint = (
                f"check that tls_root_cert ({self.verify}) is the CA that signed "
                "the runtime's certificate"
                if isinstance(self.verify, str)
                else "pass tls_root_cert=<path to the CA that signed the "
                "runtime's certificate>"
            )
            raise SpiceTLSError(
                f"TLS certificate verification failed for {url}: "
                f"certificate verify failed: {cert_error.verify_message or cert_error}; "
                f"{hint}"
            ) from exc

    def prepare_param(self, params: dict[str, Any]) -> dict[str, Any]:
        for k, val in params.items():
            if isinstance(val, datetime.timedelta):
                params[k] = timedelta_to_duration_str(val)
            elif isinstance(val, datetime.datetime):
                params[k] = int(val.timestamp())
        return params

    def _operation(self, method: HttpMethod) -> Callable[..., Response]:
        if method == "GET":
            _call = self.session.get
        elif method == "POST":
            _call = self.session.post
        elif method == "PUT":
            _call = self.session.put
        elif method == "HEAD":
            _call = self.session.head
        elif method == "DELETE":
            _call = self.session.delete
        else:
            raise SpiceAIError(f"{method} is not a valid HTTP operation")
        return _call

    def _create_session(self, headers: dict[str, str]) -> Session:
        sess = Session()
        sess.headers = headers  # type: ignore[assignment]
        sess.mount(
            "https://",
            HTTPAdapter(
                max_retries=_Retry(
                    total=5,
                    backoff_factor=2,
                    # Only retry 500s on GET so we don't unintentionally mutate data
                    allowed_methods=["GET"],
                    # https://support.cloudflare.com/hc/en-us/articles/115003011431-Troubleshooting-Cloudflare-5XX-errors
                    status_forcelist=[
                        429,
                        500,
                        502,
                        503,
                        504,
                        520,
                        521,
                        522,
                        523,
                        524,
                        526,
                        527,
                    ],
                )
            ),
        )
        return sess


def timedelta_to_duration_str(delta: datetime.timedelta) -> str:
    total_seconds = delta.total_seconds()

    days = delta.days
    hours, remainder = divmod(total_seconds, 3600)
    hours %= 24
    minutes, seconds = divmod(remainder, 60)

    # Build the Go-like duration string
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{int(hours)}h")
    if minutes:
        parts.append(f"{int(minutes)}m")
    if seconds:
        parts.append(f"{int(seconds)}s")

    return "".join(parts) if parts else "0s"
