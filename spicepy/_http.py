from collections.abc import Callable
from dataclasses import dataclass
import datetime
import json
from pathlib import Path
from typing import Any, Literal

from requests import Response, Session
from requests.adapters import HTTPAdapter, Retry

from .config import SPICE_USER_AGENT
from .error import SpiceAIError


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


HttpMethod = Literal["POST", "GET", "PUT", "HEAD", "POST"]


class HttpRequests:
    def __init__(
        self,
        base_url: str,
        headers: dict[str, str],
        tls_client_certificate: str | Path | None = None,
        tls_client_key: str | Path | None = None,
    ) -> None:
        self.session = self._create_session(headers)

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

        response: Response = self._operation(method)(  # type: ignore[call-arg]
            url=f"{self.base_url}{path}",
            data=body,
            params=self.prepare_param(param.copy()) if param is not None else None,
            verify=True,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

    def post_json(self, path: str, payload: dict[str, Any]) -> Any:
        """POST a JSON payload and decode the JSON response.

        Unlike `send_request`, a failed request raises `SpiceAIError` carrying
        the runtime's own explanation. The runtime reports errors on these
        endpoints as a plain-text body, which `raise_for_status` discards.
        """
        headers = dict(self.session.headers)
        headers["Content-Type"] = "application/json"

        response: Response = self.session.post(
            url=f"{self.base_url}{path}",
            data=json.dumps(payload),
            verify=True,
            headers=headers,
        )

        if not response.ok:
            detail = (response.text or "").strip()
            raise SpiceAIError(
                f"{path} failed with status {response.status_code}"
                + (f": {detail}" if detail else "")
            )

        try:
            return response.json()
        except ValueError as exc:
            raise SpiceAIError(
                f"{path} returned a response that was not valid JSON"
            ) from exc

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

        return self._operation(method)(  # type: ignore[call-arg]
            url=f"{self.base_url}{path}",
            data=body,
            params=self.prepare_param(param.copy()) if param is not None else None,
            verify=True,
            headers=merged_headers,
        )

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
                max_retries=Retry(
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
