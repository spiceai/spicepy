"""Vector, keyword, and hybrid search against datasets with an embedding column."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from .error import SpiceAIError


@dataclass
class SearchMatch:
    """A single document matched by a search.

    The runtime omits ``primary_key``, ``data``, and ``metadata`` when they are
    empty; they default to ``{}`` here so they can be read without a guard.
    """

    dataset: str
    """The dataset the match was found in."""

    score: float
    """Similarity of the match to the query text. Higher is closer."""

    matches: dict[str, list[Any]] = field(default_factory=dict)
    """The matched values of each searched column."""

    primary_key: dict[str, Any] = field(default_factory=dict)
    """Primary key identifying the matched row, if the dataset declares one."""

    data: dict[str, Any] = field(default_factory=dict)
    """Columns requested via ``additional_columns``."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Any additional metadata the runtime attached to the match."""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SearchMatch:
        """Build a match from the runtime's wire format.

        The wire format names the similarity score ``_score``.
        """
        return cls(
            dataset=payload.get("dataset", ""),
            score=payload.get("_score", 0.0),
            matches=payload.get("matches") or {},
            primary_key=payload.get("primary_key") or {},
            data=payload.get("data") or {},
            metadata=payload.get("metadata") or {},
        )


@dataclass
class SearchResponse:
    """The result of a search."""

    results: list[SearchMatch] = field(default_factory=list)
    """Matches, ordered by descending score."""

    duration_ms: int = 0
    """How long the runtime took to run the search."""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SearchResponse:
        """Build a response from the runtime's wire format."""
        if not isinstance(payload, dict):
            raise SpiceAIError(
                f"unexpected search response from the runtime: {payload!r}"
            )

        return cls(
            results=[SearchMatch.from_dict(m) for m in payload.get("results") or []],
            duration_ms=payload.get("duration_ms", 0),
        )

    def __len__(self) -> int:
        return len(self.results)

    def __iter__(self) -> Any:
        return iter(self.results)


def search_error_message(status_code: int | None, body: str | None) -> str:
    """Build the message to raise for a failed search.

    The runtime answers some failures with a JSON ``{"error": ...}`` body and others
    — ``"Search cannot be run on X because it has no embeddings or full text search
    indexes"``, for instance — with plain text. Without unpacking both, the caller is
    left with a bare ``400 Client Error`` and no indication of what to fix.
    """
    detail = (body or "").strip()

    if detail:
        try:
            parsed = json.loads(detail)
        except ValueError:
            pass
        else:
            if isinstance(parsed, dict) and parsed.get("error"):
                detail = str(parsed["error"])

    if not detail:
        detail = "(no response body)"

    if status_code is None:
        return f"search failed: {detail}"
    return f"search failed with status {status_code}: {detail}"


# pylint: disable=R0913
def build_search_body(
    text: str,
    *,
    datasets: list[str] | None = None,
    limit: int | None = None,
    where: str | None = None,
    additional_columns: list[str] | None = None,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """Build the ``/v1/search`` request body, omitting unset options.

    Raises:
        SpiceAIError: if ``text`` is empty.
    """
    if not text:
        raise SpiceAIError("search text is required")

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
