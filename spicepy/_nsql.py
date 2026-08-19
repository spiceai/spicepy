"""Types and request building for the runtime's ``/v1/nsql`` endpoint."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NSQL_PATH = "/v1/nsql"

# Media type that makes the runtime return the generated SQL alongside the
# results. Without it ``/v1/nsql`` answers with a bare array of rows and the
# generated SQL is lost.
NSQL_JSON_MEDIA_TYPE = "application/vnd.spiceai.nsql.v1+json"

# Media type that makes the runtime generate SQL without executing it.
NSQL_SQL_MEDIA_TYPE = "application/sql"


@dataclass(frozen=True)
class NsqlField:
    """One column of an :class:`NsqlResult`.

    Attributes:
        name: The column name.
        data_type: The column's Arrow type in the JSON encoding the runtime
            emits. Simple types arrive as a string (``"Utf8"``), parameterized
            ones as a dict (``{"Timestamp": ["Nanosecond", None]}``).
        nullable: Whether the column admits nulls.
    """

    name: str
    data_type: Any = None
    nullable: bool = False

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> NsqlField:
        """Build a field from one element of the runtime's ``schema.fields``."""
        return cls(
            name=obj.get("name", ""),
            data_type=obj.get("data_type"),
            nullable=bool(obj.get("nullable", False)),
        )


@dataclass(frozen=True)
class NsqlResult:
    """The result of a single :meth:`spicepy.Client.nsql` call.

    Iterating an ``NsqlResult`` yields its rows, so the common case reads as
    ``for row in client.nsql(...)``.

    Attributes:
        sql: The query the model generated. Worth logging: a surprising result
            is usually a surprising query.
        row_count: The number of rows the runtime reported.
        schema: The columns in ``data``. Empty when the generated query
            returned no rows — the runtime omits the schema body in that case.
        data: The rows, each keyed by column name. Values are decoded from
            JSON, so they carry JSON's types rather than the Arrow types named
            in ``schema``. Use :meth:`spicepy.Client.nsql_generate_sql` with
            :meth:`spicepy.Client.query` when Arrow types matter.
    """

    sql: str = ""
    row_count: int = 0
    schema: list[NsqlField] = field(default_factory=list)
    data: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> NsqlResult:
        """Build a result from the runtime's ``/v1/nsql`` response body."""
        schema_obj = obj.get("schema") or {}
        fields = schema_obj.get("fields") or [] if isinstance(schema_obj, dict) else []
        data = obj.get("data") or []

        return cls(
            sql=obj.get("sql") or "",
            row_count=int(obj.get("row_count", len(data))),
            schema=[NsqlField.from_json(f) for f in fields],
            data=data,
        )

    def __iter__(self):
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)


def build_nsql_body(
    query: str,
    *,
    model: str | None = None,
    datasets: list[str] | None = None,
    sample_data_enabled: bool | None = None,
    prompt_cache_key: str | None = None,
) -> dict[str, Any]:
    """Build the ``/v1/nsql`` request body, validating what the runtime rejects.

    Optional fields are omitted rather than sent as null so the runtime applies
    its own defaults.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty natural language query")
    if datasets is not None and len(datasets) == 0:
        raise ValueError(
            "datasets must name at least one dataset. Omit it to let the runtime "
            "sample all of them."
        )

    body: dict[str, Any] = {"query": query}
    if model is not None:
        body["model"] = model
    if datasets is not None:
        body["datasets"] = datasets
    if sample_data_enabled is not None:
        body["sample_data_enabled"] = sample_data_enabled
    if prompt_cache_key is not None:
        body["prompt_cache_key"] = prompt_cache_key
    return body
