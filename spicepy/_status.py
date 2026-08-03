"""Runtime health and per-component status."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ComponentStatus(StrEnum):
    """The state of a single runtime component.

    Mirrors the runtime's ``ComponentStatus``. A value the runtime adds in future
    that this SDK does not know about is preserved as-is rather than raising, so
    :meth:`from_value` never fails on an unrecognized status.
    """

    INITIALIZING = "Initializing"
    READY = "Ready"
    DISABLED = "Disabled"
    ERROR = "Error"
    REFRESHING = "Refreshing"
    SHUTTING_DOWN = "ShuttingDown"
    NOT_LOADED = "NotLoaded"

    @classmethod
    def from_value(cls, value: str) -> ComponentStatus | str:
        """Return the matching member, or ``value`` unchanged if unrecognized."""
        try:
            return cls(value)
        except ValueError:
            return value

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ConnectionDetails:
    """The status of one runtime connection."""

    name: str
    """Name of the connection: ``http``, ``flight``, ``metrics`` or ``opentelemetry``."""

    endpoint: str
    """Endpoint the connection is served on, or ``N/A`` when the component is disabled."""

    status: ComponentStatus | str
    """Status of the component."""

    @property
    def is_ready(self) -> bool:
        """Whether this component is ready to accept connections."""
        return self.status == ComponentStatus.READY

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConnectionDetails:
        """Build from a single ``/v1/status`` response entry."""
        return cls(
            name=data.get("name", ""),
            endpoint=data.get("endpoint", ""),
            status=ComponentStatus.from_value(data.get("status", "")),
        )
