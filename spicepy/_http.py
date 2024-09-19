import datetime
import json
from typing import Any, Callable, Dict, Literal, Optional, Union
from requests import Response, Session
from requests.adapters import HTTPAdapter, Retry

from .error import SpiceAIError
from .config import SPICE_USER_AGENT


HttpMethod = Literal["POST", "GET", "PUT", "HEAD", "POST"]


class HttpRequests:
    def __init__(self, base_url: str, headers: Dict[str, str]) -> None:
        self.session = self._create_session(headers)

        # set the x-spice-user-agent header
        self.session.headers["X-Spice-User-Agent"] = SPICE_USER_AGENT

        self.base_url = base_url

    def send_request(
        self,
        method: HttpMethod,
        path: str,
        param: Optional[Dict[str, Any]] = None,
        body: Optional[Union[Any, bytes, str]] = None,
    ) -> Any:
        if not isinstance(body, (bytes, str)) and body is not None:
            body = json.dumps(body)

        response: Response = self._operation(method)(
            url=f"{self.base_url}{path}",
            data=body,
            params=self.prepare_param(param.copy()) if param is not None else param,
            verify=True,
        )
        response.raise_for_status()
        return response.json()

    def prepare_param(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for k, val in params.items():
            if isinstance(val, datetime.timedelta):
                params[k] = timedelta_to_duration_str(val)
            elif isinstance(val, datetime.datetime):
                params[k] = int(val.timestamp())
        return params

    def _operation(self, method: HttpMethod) -> Callable[[], Response]:
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

    def _create_session(self, headers: Dict[str, str]) -> Session:
        sess = Session()
        sess.headers = headers
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
