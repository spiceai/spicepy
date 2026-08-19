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

# Rows fetched to render a notebook (_repr_html_) preview.
_HTML_PREVIEW_ROWS = 10


def _as_expr(value: Any) -> Expr:
    if isinstance(value, Expr):
        return value
    if isinstance(value, str):
        return _col_builder(value)
    raise TypeError(f"Expected Expr or column-name str, got {type(value).__name__}")


class SpiceDataFrame:
    """A lazy query plan that compiles to SQL on materialization."""

    def __init__(self, client: Client, sql: str, *, ordered: bool = False) -> None:
        self._client = client
        self._sql = sql
        self._ordered = ordered

    # ------------------------------------------------------------------
    # SQL lineage primitives
    # ------------------------------------------------------------------

    def _wrap(self, sql: str, *, ordered: bool = False) -> SpiceDataFrame:
        return SpiceDataFrame(self._client, sql, ordered=ordered)

    def _column_names(self) -> list[str]:
        """Column names of this frame, resolved with a zero-row query.

        Operations that rewrite the projection column-by-column (``drop``,
        ``rename``, ``cast``, ``unnest``) need the full column list: the
        runtime's SQL parser has no ``* EXCLUDE``/``* REPLACE`` star modifiers.
        """
        return list(self.schema().names)

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
        """Drop columns (resolves the frame's schema with a zero-row query)."""
        if not columns:
            return self
        dropped = set(columns)
        remaining = [c for c in self._column_names() if c not in dropped]
        if not remaining:
            raise ValueError("drop() would remove every column")
        rendered = ", ".join(quote_ident(c) for c in remaining)
        return self._wrap(f"SELECT {rendered} FROM {self._from()}")

    def rename(self, mapping: dict[str, str]) -> SpiceDataFrame:
        """Rename columns (resolves the frame's schema with a zero-row query)."""
        if not mapping:
            return self
        parts = [
            (
                f"{quote_ident(c)} AS {quote_ident(mapping[c])}"
                if c in mapping
                else quote_ident(c)
            )
            for c in self._column_names()
        ]
        return self._wrap(f"SELECT {', '.join(parts)} FROM {self._from()}")

    def cast(self, mapping: dict[str, Any]) -> SpiceDataFrame:
        """Cast columns in place (resolves the frame's schema with a zero-row query)."""
        if not mapping:
            return self
        # Reuse Expr.cast for type-name handling.
        parts = [
            (
                _col_builder(c).cast(mapping[c]).alias(c).to_sql()
                if c in mapping
                else quote_ident(c)
            )
            for c in self._column_names()
        ]
        return self._wrap(f"SELECT {', '.join(parts)} FROM {self._from()}")

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
        if self._ordered:
            # LIMIT must share the ORDER BY's query level: wrapping a sorted
            # frame in a subquery frees the planner to discard its ordering.
            return self._wrap(f"{self._sql} {clause}")
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
        return self._wrap(
            f"SELECT * FROM {self._from()} ORDER BY {', '.join(parts)}", ordered=True
        )

    order_by = sort

    def distinct(self) -> SpiceDataFrame:
        return self._wrap(f"SELECT DISTINCT * FROM {self._from()}")

    def unnest(self, *columns: str) -> SpiceDataFrame:
        """Explode array column(s) into one row per element.

        Non-unnested columns repeat for each element (DataFusion evaluates
        ``unnest`` in the projection). Resolves the frame's schema with a
        zero-row query.
        """
        if not columns:
            raise ValueError("unnest() requires at least one column")
        targets = set(columns)
        parts = [
            (
                f"unnest({quote_ident(c)}) AS {quote_ident(c)}"
                if c in targets
                else quote_ident(c)
            )
            for c in self._column_names()
        ]
        return self._wrap(f"SELECT {', '.join(parts)} FROM {self._from()}")

    # ------------------------------------------------------------------
    # Set operations
    # ------------------------------------------------------------------

    def union(self, other: SpiceDataFrame, all: bool = False) -> SpiceDataFrame:
        op = "UNION ALL" if all else "UNION"
        return self._wrap(f"{self._sql} {op} {other._sql}")

    def intersect(self, other: SpiceDataFrame, all: bool = False) -> SpiceDataFrame:
        op = "INTERSECT ALL" if all else "INTERSECT"
        return self._wrap(f"{self._sql} {op} {other._sql}")

    def except_(self, other: SpiceDataFrame, all: bool = False) -> SpiceDataFrame:
        op = "EXCEPT ALL" if all else "EXCEPT"
        return self._wrap(f"{self._sql} {op} {other._sql}")

    # ------------------------------------------------------------------
    # Joins
    # ------------------------------------------------------------------

    def join(
        self,
        other: SpiceDataFrame,
        on: str | list[str] | Expr | None = None,
        how: str = "inner",
        *,
        left_on: str | list[str] | None = None,
        right_on: str | list[str] | None = None,
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

        if left_on is not None or right_on is not None:
            if on is not None:
                raise ValueError("pass either `on` or `left_on`/`right_on`, not both")
            if left_on is None or right_on is None:
                raise ValueError("left_on and right_on must be provided together")
            left_keys = [left_on] if isinstance(left_on, str) else list(left_on)
            right_keys = [right_on] if isinstance(right_on, str) else list(right_on)
            if not left_keys or len(left_keys) != len(right_keys):
                raise ValueError(
                    "left_on and right_on must have the same non-zero length"
                )
            on_sql = "ON " + " AND ".join(
                f"{quote_ident(left_alias)}.{quote_ident(lk)} = "
                f"{quote_ident(right_alias)}.{quote_ident(rk)}"
                for lk, rk in zip(left_keys, right_keys, strict=True)
            )
        elif on is None:
            raise ValueError(
                "join requires `on`, or `left_on`/`right_on`, or how='cross'"
            )
        elif isinstance(on, Expr):
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

    def join_on(
        self,
        other: SpiceDataFrame,
        *predicates: Expr,
        how: str = "inner",
        left_alias: str = "l",
        right_alias: str = "r",
    ) -> SpiceDataFrame:
        """Join on arbitrary boolean predicates, ANDed together.

        Reference each side with a column qualifier, e.g.::

            df.join_on(other, col("user_id", "l") == col("id", "r"))
        """
        if not predicates:
            raise ValueError("join_on() requires at least one predicate")
        kind = how.lower()
        if kind not in _JOIN_KINDS or kind == "cross":
            valid = sorted(k for k in _JOIN_KINDS if k != "cross")
            raise ValueError(f"join_on does not support how={how!r}; expected {valid}")
        join_sql = _JOIN_KINDS[kind]
        left = f"{self._from()} {quote_ident(left_alias)}"
        right = f"{other._from()} {quote_ident(right_alias)}"
        on_sql = "ON " + " AND ".join(p.to_sql() for p in predicates)
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

    def describe(self) -> SpiceDataFrame:
        """Summary statistics (count, mean, stddev, min, max) per numeric column.

        Reads the schema (a ``LIMIT 0`` round-trip), then returns a lazy
        DataFrame whose rows are labelled by a ``statistic`` column. Only
        numeric columns are summarized, matching ``pandas.DataFrame.describe``.
        """
        import pyarrow as pa

        numeric = [
            field.name
            for field in self.schema()
            if pa.types.is_integer(field.type)
            or pa.types.is_floating(field.type)
            or pa.types.is_decimal(field.type)
        ]
        if not numeric:
            raise ValueError("describe() found no numeric columns to summarize")

        stats = [
            ("count", "CAST(COUNT({c}) AS DOUBLE)"),
            ("mean", "AVG(CAST({c} AS DOUBLE))"),
            ("stddev", "STDDEV(CAST({c} AS DOUBLE))"),
            ("min", "CAST(MIN({c}) AS DOUBLE)"),
            ("max", "CAST(MAX({c}) AS DOUBLE)"),
        ]
        selects = []
        for stat_name, template in stats:
            cols = ", ".join(
                f"{template.format(c=quote_ident(c))} AS {quote_ident(c)}"
                for c in numeric
            )
            selects.append(
                f"SELECT {quote_literal(stat_name)} AS {quote_ident('statistic')}, "
                f"{cols} FROM {self._from()}"
            )
        return self._wrap(" UNION ALL ".join(selects))

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

    # ------------------------------------------------------------------
    # Interop / display
    # ------------------------------------------------------------------

    def __getitem__(self, key: str | list[str]) -> SpiceDataFrame:
        """Select column(s): ``df["a"]`` or ``df[["a", "b"]]``."""
        if isinstance(key, str):
            return self.select(_col_builder(key))
        if isinstance(key, list):
            if not key:
                raise KeyError("column selection requires at least one column")
            if not all(isinstance(k, str) for k in key):
                raise TypeError("column names in a selection list must be strings")
            return self.select(*[_col_builder(k) for k in key])
        raise TypeError(
            f"index must be a column name or list of names, got {type(key).__name__}"
        )

    def __arrow_c_stream__(self, requested_schema: object = None) -> object:
        """Expose results via the Arrow C stream interface (PyCapsule protocol).

        Lets Arrow-native consumers ingest a SpiceDataFrame directly — e.g.
        ``pyarrow.table(df)``, ``polars.DataFrame(df)``, or DuckDB. The result
        is materialized, then its Arrow C stream is handed off.
        """
        return self.collect().__arrow_c_stream__(requested_schema)

    def _repr_html_(self) -> str:
        """Render a preview (first rows) as an HTML table for notebooks."""
        preview = self.limit(_HTML_PREVIEW_ROWS).to_pandas()
        caption = f"SpiceDataFrame preview (up to {_HTML_PREVIEW_ROWS} rows)"
        return f"{preview.to_html(index=False)}<em>{caption}</em>"

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
