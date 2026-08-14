"""Types and request building for the runtime's ``/v1/search`` endpoint."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEARCH_PATH = "/v1/search"


@dataclass(frozen=True)
class SearchMatch:
    """A single document matched by :meth:`spicepy.Client.search`.

    Attributes:
        dataset: The dataset the match was found in.
        score: The match's similarity to the query. Higher is more similar.
        matches: The matched values, keyed by the column they came from. The
            runtime returns a list per column because a column may contribute
            more than one chunk to a single match.
        primary_key: The primary key columns identifying the matched row.
            Empty when the dataset declares no primary key.
        data: Any ``additional_columns`` requested, keyed by column name.
        metadata: Extra per-match metadata the runtime chose to attach.
    """

    dataset: str
    score: float
    matches: dict[str, list[Any]] = field(default_factory=dict)
    primary_key: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> SearchMatch:
        """Build a match from one element of the runtime's ``results`` array.

        The runtime omits ``data``, ``primary_key``, and ``metadata`` when they
        are empty, so each is defaulted rather than required.
        """
        return cls(
            dataset=obj.get("dataset", ""),
            score=float(obj.get("_score", 0.0)),
            matches=obj.get("matches") or {},
            primary_key=obj.get("primary_key") or {},
            data=obj.get("data") or {},
            metadata=obj.get("metadata") or {},
        )


@dataclass(frozen=True)
class SearchResult:
    """The matches returned by a single :meth:`spicepy.Client.search` call.

    Iterating a ``SearchResult`` yields its :class:`SearchMatch` items, so the
    common case reads as ``for match in client.search(...)``.
    """

    results: list[SearchMatch]
    duration_ms: int

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> SearchResult:
        """Build a result from the runtime's ``/v1/search`` response body."""
        return cls(
            results=[SearchMatch.from_json(m) for m in obj.get("results") or []],
            duration_ms=int(obj.get("duration_ms", 0)),
        )

    def __iter__(self):
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)


def build_search_body(
    text: str,
    *,
    datasets: list[str] | None = None,
    limit: int | None = None,
    where: str | None = None,
    additional_columns: list[str] | None = None,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """Build the ``/v1/search`` request body, validating what the runtime rejects.

    Optional fields are omitted rather than sent as null so the runtime applies
    its own defaults.
    """
    if not text or not text.strip():
        raise ValueError("text must be a non-empty search string")
    if datasets is not None and len(datasets) == 0:
        raise ValueError(
            "datasets must name at least one dataset. Omit it to search all "
            "searchable datasets."
        )
    if limit is not None and limit < 1:
        raise ValueError("limit must be greater than 0")

    body: dict[str, Any] = {"text": text}
    if datasets is not None:
        body["datasets"] = datasets
    if limit is not None:
        body["limit"] = limit
    if where is not None:
        body["where"] = where
    if additional_columns is not None:
        body["additional_columns"] = additional_columns
    if keywords is not None:
        body["keywords"] = keywords
    return body
