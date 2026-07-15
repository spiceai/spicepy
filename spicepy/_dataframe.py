"""Lazy DataFrame that compiles to SQL and executes against a :class:`Client`.

The :class:`SpiceDataFrame` is a thin client-side builder. Each operation
returns a new DataFrame holding a SQL fragment; terminal operations
(``collect``, ``to_pandas``, ``to_polars``, ``to_arrow``, ``count``, ``show``)
materialize the SQL by shipping it through the existing Flight transport on
:class:`spicepy.Client`. There is no client-side execution.

Lineage is built as nested subqueries with auto-generated table aliases.
DataFusion flattens these in the optimizer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._expr import Expr, _sort_sql, _SortExpr
from ._expr import col as _col_builder
from ._sql import quote_ident, quote_literal

if TYPE_CHECKING:
    import pandas as pd
    import polars as pl
    import pyarrow as pa

    from ._client import Client


_JOIN_KINDS = {
    "inner": "INNER JOIN",
    "left": "LEFT JOIN",
    "right": "RIGHT JOIN",
    "full": "FULL OUTER JOIN",
    "semi": "LEFT SEMI JOIN",
    "anti": "LEFT ANTI JOIN",
    "cross": "CROSS JOIN",
}


def _as_expr(value: Any) -> Expr:
    if isinstance(value, Expr):
        return value
    if isinstance(value, str):
        return _col_builder(value)
    raise TypeError(f"Expected Expr or column-name str, got {type(value).__name__}")


class SpiceDataFrame:
    """A lazy query plan that compiles to SQL on materialization."""

    def __init__(self, client: Client, sql: str) -> None:
        self._client = client
        self._sql = sql

    # ------------------------------------------------------------------
    # SQL lineage primitives
    # ------------------------------------------------------------------

    def _wrap(self, sql: str) -> SpiceDataFrame:
        return SpiceDataFrame(self._client, sql)

    def _from(self) -> str:
        """Return ``(<inner_sql>)`` for use as a FROM source."""
        return f"({self._sql})"

    def to_sql(self) -> str:
        """Return the compiled SQL for this DataFrame (no trailing semicolon)."""
        return self._sql

    # ------------------------------------------------------------------
    # Projection
    # ------------------------------------------------------------------

    def select(self, *exprs: Expr | str) -> SpiceDataFrame:
        if not exprs:
            raise ValueError("select() requires at least one expression")
        items = ", ".join(_as_expr(e).to_sql() for e in exprs)
        return self._wrap(f"SELECT {items} FROM {self._from()}")

    def with_column(self, name: str, expr: Expr | str) -> SpiceDataFrame:
        rendered = _as_expr(expr).to_sql()
        return self._wrap(
            f"SELECT *, {rendered} AS {quote_ident(name)} FROM {self._from()}"
        )

    def with_columns(self, **named: Expr | str) -> SpiceDataFrame:
        if not named:
            return self
        parts = [
            f"{_as_expr(e).to_sql()} AS {quote_ident(n)}" for n, e in named.items()
        ]
        return self._wrap(f"SELECT *, {', '.join(parts)} FROM {self._from()}")

    def drop(self, *columns: str) -> SpiceDataFrame:
        if not columns:
            return self
        rendered = ", ".join(quote_ident(c) for c in columns)
        return self._wrap(f"SELECT * EXCLUDE ({rendered}) FROM {self._from()}")

    def rename(self, mapping: dict[str, str]) -> SpiceDataFrame:
        if not mapping:
            return self
        renames = ", ".join(
            f"{quote_ident(old)} AS {quote_ident(new)}" for old, new in mapping.items()
        )
        return self._wrap(f"SELECT * REPLACE ({renames}) FROM {self._from()}")

    def cast(self, mapping: dict[str, Any]) -> SpiceDataFrame:
        if not mapping:
            return self
        # Reuse Expr.cast for type-name handling.
        renamed = {
            name: _col_builder(name).cast(target).alias(name)
            for name, target in mapping.items()
        }
        return self.with_columns(**renamed)

    # ------------------------------------------------------------------
    # Filter / slice
    # ------------------------------------------------------------------

    def filter(self, predicate: Expr) -> SpiceDataFrame:
        return self._wrap(f"SELECT * FROM {self._from()} WHERE {predicate.to_sql()}")

    where = filter

    def limit(self, n: int, offset: int | None = None) -> SpiceDataFrame:
        if n < 0:
            raise ValueError("limit must be non-negative")
        clause = f"LIMIT {n}"
        if offset is not None:
            if offset < 0:
                raise ValueError("offset must be non-negative")
            clause = f"{clause} OFFSET {offset}"
        return self._wrap(f"SELECT * FROM {self._from()} {clause}")

    def head(self, n: int = 5) -> SpiceDataFrame:
        return self.limit(n)

    def tail(self, n: int = 5) -> SpiceDataFrame:
        # No portable SQL tail; emulate by sorting on a row_number from the end.
        # Keep it explicit so users opt-in.
        raise NotImplementedError(
            "tail() is not supported; sort by your key descending and use head()."
        )

    # ------------------------------------------------------------------
    # Sort / distinct
    # ------------------------------------------------------------------

    def sort(self, *exprs: Expr | _SortExpr | str) -> SpiceDataFrame:
        if not exprs:
            raise ValueError("sort() requires at least one key")
        parts = []
        for e in exprs:
            if isinstance(e, _SortExpr):
                parts.append(e.to_sql())
            else:
                parts.append(_sort_sql(_as_expr(e)))
        return self._wrap(f"SELECT * FROM {self._from()} ORDER BY {', '.join(parts)}")

    order_by = sort

    def distinct(self) -> SpiceDataFrame:
        return self._wrap(f"SELECT DISTINCT * FROM {self._from()}")

    # ------------------------------------------------------------------
    # Set operations
    # ------------------------------------------------------------------

    def union(self, other: SpiceDataFrame, all: bool = False) -> SpiceDataFrame:
        op = "UNION ALL" if all else "UNION"
        return self._wrap(f"{self._sql} {op} {other._sql}")

    def intersect(self, other: SpiceDataFrame) -> SpiceDataFrame:
        return self._wrap(f"{self._sql} INTERSECT {other._sql}")

    def except_(self, other: SpiceDataFrame) -> SpiceDataFrame:
        return self._wrap(f"{self._sql} EXCEPT {other._sql}")

    # ------------------------------------------------------------------
    # Joins
    # ------------------------------------------------------------------

    def join(
        self,
        other: SpiceDataFrame,
        on: str | list[str] | Expr,
        how: str = "inner",
        left_alias: str = "l",
        right_alias: str = "r",
    ) -> SpiceDataFrame:
        kind = how.lower()
        if kind not in _JOIN_KINDS:
            raise ValueError(
                f"Unknown join kind {how!r}; expected one of {sorted(_JOIN_KINDS)}"
            )
        join_sql = _JOIN_KINDS[kind]

        left = f"{self._from()} {quote_ident(left_alias)}"
        right = f"{other._from()} {quote_ident(right_alias)}"

        if kind == "cross":
            return self._wrap(f"SELECT * FROM {left} {join_sql} {right}")

        if isinstance(on, Expr):
            on_sql = f"ON {on.to_sql()}"
        else:
            keys = [on] if isinstance(on, str) else list(on)
            if not keys:
                raise ValueError("join `on` requires at least one key")
            on_sql = "ON " + " AND ".join(
                f"{quote_ident(left_alias)}.{quote_ident(k)} = "
                f"{quote_ident(right_alias)}.{quote_ident(k)}"
                for k in keys
            )
        return self._wrap(f"SELECT * FROM {left} {join_sql} {right} {on_sql}")

    def cross_join(self, other: SpiceDataFrame) -> SpiceDataFrame:
        return self.join(other, on="", how="cross")

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def group_by(self, *exprs: Expr | str) -> _GroupedDataFrame:
        keys = [_as_expr(e) for e in exprs]
        return _GroupedDataFrame(self, keys)

    def aggregate(self, *aggs: Expr) -> SpiceDataFrame:
        """Aggregate without grouping (single-row result)."""
        return self.group_by().aggregate(*aggs)

    # ------------------------------------------------------------------
    # Schema / introspection
    # ------------------------------------------------------------------

    def schema(self) -> pa.Schema:
        """Return the Arrow schema of this DataFrame (executes ``LIMIT 0``)."""
        reader = self._client.query(f"SELECT * FROM {self._from()} LIMIT 0")
        return reader.read_all().schema

    def explain(self, analyze: bool = False, verbose: bool = False) -> str:
        prefix = "EXPLAIN"
        if analyze:
            prefix += " ANALYZE"
        if verbose:
            prefix += " VERBOSE"
        table = self._client.query(f"{prefix} {self._sql}").read_all()
        rows = table.to_pylist()
        return "\n".join(
            (row.get("plan") or row.get("plan_type") or str(row)) for row in rows
        )

    # ------------------------------------------------------------------
    # Materialization
    # ------------------------------------------------------------------

    def collect(self) -> pa.Table:
        return self._client.query_arrow(self._sql)

    def to_arrow(self) -> pa.Table:
        return self.collect()

    def to_pandas(self) -> pd.DataFrame:
        return self._client.query_pandas(self._sql)

    def to_polars(self) -> pl.DataFrame:
        return self._client.query_polars(self._sql)

    def to_pylist(self) -> list[dict[str, Any]]:
        return self._client.query_pylist(self._sql)

    def to_pydict(self) -> dict[str, list[Any]]:
        return self._client.query_pydict(self._sql)

    def count(self) -> int:
        table = self._client.query_arrow(f"SELECT COUNT(*) AS c FROM {self._from()}")
        return int(table.column("c")[0].as_py())

    def show(self, n: int = 20) -> None:
        self.limit(n).to_pandas_print()  # pragma: no cover  - alias

    def to_pandas_print(self) -> None:
        df = self.to_pandas()
        print(df.to_string(index=False))  # noqa: T201

    # ------------------------------------------------------------------
    # Writers
    # ------------------------------------------------------------------

    def write_parquet(self, path: str, **kwargs: Any) -> None:
        """Stream this DataFrame's result to a Parquet file at ``path``."""
        self._client.write_parquet(self._sql, path, **kwargs)

    def write_csv(self, path: str, **kwargs: Any) -> None:
        """Stream this DataFrame's result to a CSV file at ``path``."""
        self._client.write_csv(self._sql, path, **kwargs)

    def write_json(self, path: str) -> None:
        """Write this DataFrame's result to ``path`` as newline-delimited JSON."""
        self._client.write_json(self._sql, path)

    def __repr__(self) -> str:
        return f"SpiceDataFrame({self._sql})"


class _GroupedDataFrame:
    """Intermediate object returned by :meth:`SpiceDataFrame.group_by`."""

    def __init__(self, source: SpiceDataFrame, keys: list[Expr]) -> None:
        self._source = source
        self._keys = keys

    def aggregate(self, *aggs: Expr) -> SpiceDataFrame:
        if not aggs and not self._keys:
            raise ValueError("aggregate() requires at least one aggregate expression")
        key_sql = [k.to_sql() for k in self._keys]
        agg_sql = [a.to_sql() for a in aggs]
        projection = ", ".join(key_sql + agg_sql) if (key_sql or agg_sql) else "*"
        clause = f"SELECT {projection} FROM {self._source._from()}" + (
            f" GROUP BY {', '.join(key_sql)}" if key_sql else ""
        )
        return SpiceDataFrame(self._source._client, clause)

    agg = aggregate

    def __repr__(self) -> str:
        keys = ", ".join(k.to_sql() for k in self._keys)
        return f"_GroupedDataFrame(keys=[{keys}])"


def values_dataframe(client: Client, rows: list[dict[str, Any]]) -> SpiceDataFrame:
    """Build a SpiceDataFrame from a list of row dicts via inline VALUES.

    Intended for small literal tables only — no upload path. Column order is
    taken from the first row and must match across rows.
    """
    if not rows:
        raise ValueError("values_dataframe requires at least one row")
    columns = list(rows[0].keys())
    rendered_rows = []
    for r in rows:
        if list(r.keys()) != columns:
            raise ValueError("All rows must have the same columns in the same order")
        rendered_rows.append(
            "(" + ", ".join(quote_literal(r[c]) for c in columns) + ")"
        )
    column_list = ", ".join(quote_ident(c) for c in columns)
    values_sql = ", ".join(rendered_rows)
    sql = f"SELECT * FROM (VALUES {values_sql}) AS t({column_list})"
    return SpiceDataFrame(client, sql)
