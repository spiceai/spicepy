"""SQL escape helpers for safe identifier/literal emission."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any


def quote_ident(name: str) -> str:
    """Quote a SQL identifier (column, table, schema) using ANSI double quotes.

    Embedded double quotes are doubled per the SQL standard.
    """
    return '"' + name.replace('"', '""') + '"'


def quote_qualified(*parts: str) -> str:
    """Quote a multi-part identifier, e.g. ("schema", "table") -> '"schema"."table"'."""
    return ".".join(quote_ident(p) for p in parts if p)


def quote_literal(value: Any) -> str:
    """Render a Python value as a SQL literal.

    Supports None, bool, int, float, Decimal, str, bytes, date, datetime, time,
    list (rendered as ``MAKE_ARRAY(...)``), and dict (rendered as
    ``NAMED_STRUCT(...)``); lists and dicts render their items recursively.
    Raises TypeError for unsupported types — use parameterized queries instead.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return "'" + escaped + "'"
    if isinstance(value, bytes):
        return "X'" + value.hex() + "'"
    if isinstance(value, datetime):
        return "CAST('" + value.isoformat(sep=" ") + "' AS TIMESTAMP)"
    if isinstance(value, date):
        return "CAST('" + value.isoformat() + "' AS DATE)"
    if isinstance(value, time):
        return "CAST('" + value.isoformat() + "' AS TIME)"
    if isinstance(value, list):
        return "MAKE_ARRAY(" + ", ".join(quote_literal(v) for v in value) + ")"
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            parts.append(quote_literal(str(key)))
            parts.append(quote_literal(item))
        return "NAMED_STRUCT(" + ", ".join(parts) + ")"
    raise TypeError(
        f"Cannot render {type(value).__name__} as a SQL literal; "
        "use a parameterized query."
    )
