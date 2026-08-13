"""Listing and cancelling running synchronous queries."""

from __future__ import annotations

from dataclasses import dataclass
import datetime
from typing import Any


@dataclass(frozen=True)
class ActiveQuery:
    """A synchronous query currently running on the runtime."""

    query_id: str
    """Server-assigned id, and what :meth:`Client.cancel_active_query` takes."""

    protocol: str
    """The protocol the query arrived on: ``http``, ``flight``, ``flightsql`` or
    ``internal``."""

    sql_preview: str
    """The query's SQL, truncated by the runtime for display."""

    started_at_ms: int
    """When the query started, in milliseconds since the Unix epoch."""

    @property
    def started_at(self) -> datetime.datetime:
        """When the query started, as a timezone-aware UTC datetime."""
        return datetime.datetime.fromtimestamp(
            self.started_at_ms / 1000, tz=datetime.UTC
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActiveQuery:
        """Build from a single ``GET /v1/sql/active`` response entry."""
        return cls(
            query_id=data.get("query_id", ""),
            protocol=data.get("protocol", ""),
            sql_preview=data.get("sql_preview", ""),
            started_at_ms=data.get("started_at_ms", 0),
        )
