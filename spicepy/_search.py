"""Types and request building for the runtime's ``/v1/search`` endpoint."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .error import SpiceAIError

SEARCH_PATH = "/v1/search"


def _malformed(detail: str) -> SpiceAIError:
    return SpiceAIError(f"{SEARCH_PATH} returned a malformed response: {detail}")


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

        ``dataset``, ``_score``, and ``matches`` are always sent, so a match
        without one raises :class:`~spicepy.SpiceAIError` rather than reading
        as an empty, zero-scored match. The runtime omits ``data``,
        ``primary_key``, and ``metadata`` when they are empty, so each is
        defaulted rather than required.
        """
        return _parse_match(obj, 0)


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
        """Build a result from the runtime's ``/v1/search`` response body.

        Raises :class:`~spicepy.SpiceAIError` when the body lacks a field the
        runtime always sends: defaulting it would report a malformed response
        as zero results in zero milliseconds, indistinguishable from a real
        empty search.
        """
        if not isinstance(obj, dict):
            raise _malformed("not a JSON object")
        results = obj.get("results")
        if results is None:
            raise _malformed("missing 'results'")
        if not isinstance(results, list):
            raise _malformed("'results' is not a list")
        if obj.get("duration_ms") is None:
            raise _malformed("missing 'duration_ms'")
        return cls(
            results=[_parse_match(m, i) for i, m in enumerate(results)],
            duration_ms=int(obj["duration_ms"]),
        )

    def __iter__(self):
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)


def _parse_match(obj: Any, index: int) -> SearchMatch:
    """Build the ``index``-th match, naming it in any error."""
    if not isinstance(obj, dict):
        raise _malformed(f"result {index} is not an object")
    dataset = obj.get("dataset")
    # Older runtimes serialized the score as "score".
    score = obj.get("_score", obj.get("score"))
    matches = obj.get("matches")
    if dataset is None:
        raise _malformed(f"result {index} is missing 'dataset'")
    if score is None:
        raise _malformed(f"result {index} is missing '_score'")
    if matches is None:
        raise _malformed(f"result {index} is missing 'matches'")
    return SearchMatch(
        dataset=dataset,
        score=float(score),
        matches=matches,
        primary_key=obj.get("primary_key") or {},
        data=obj.get("data") or {},
        metadata=obj.get("metadata") or {},
    )


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
