"""Expression DSL that compiles to SQL fragments.

The DataFrame layer (``spicepy._dataframe``) and the public ``spicepy.functions``
module both build trees of :class:`Expr` nodes. Calling :meth:`Expr.to_sql`
produces a SQL fragment safe to embed in a SELECT.
"""

from __future__ import annotations

from typing import Any

from ._sql import quote_ident, quote_literal


class Expr:
    """Base class for column expressions.

    All operator overloads (``+ - * / % == != < <= > >= & | ~``) return a new
    :class:`Expr`, which means expressions compose without evaluating until the
    enclosing DataFrame is materialized.

    Note: ``__eq__`` and the other comparison operators are intentionally
    overridden to build SQL expression trees rather than to return ``bool``.
    This is the standard DataFrame DSL pattern (SQLAlchemy, pandas, polars,
    Ibis, datafusion-python all do the same). ``col("x") == 5`` returns an
    :class:`Expr` that compiles to ``"x" = 5``, not the Python ``bool`` ``False``.
    Subclasses therefore *must not* override ``__eq__`` to compare attributes —
    doing so would silently break filtering and joins. Static analyzers that
    flag subclasses for "missing ``__eq__``" are misapplying a rule that
    assumes value-semantics ``__eq__``; here ``__eq__`` is the DSL builder.
    """

    def to_sql(self) -> str:
        raise NotImplementedError

    # --- naming ---

    def alias(self, name: str) -> Expr:
        return _Alias(self, name)

    # --- type coercion ---

    def cast(self, arrow_type: Any) -> Expr:
        return _Cast(self, _arrow_type_to_sql(arrow_type))

    def try_cast(self, arrow_type: Any) -> Expr:
        """Like :meth:`cast` but yields NULL instead of erroring on failure."""
        return _Cast(self, _arrow_type_to_sql(arrow_type), is_try=True)

    # --- comparison (DSL: returns Expr, not bool — see class docstring) ---

    def __eq__(self, other: object) -> Expr:  # type: ignore[override]
        return _BinOp(self, "=", _coerce(other))

    def __ne__(self, other: object) -> Expr:  # type: ignore[override]
        return _BinOp(self, "<>", _coerce(other))

    def __lt__(self, other: object) -> Expr:
        return _BinOp(self, "<", _coerce(other))

    def __le__(self, other: object) -> Expr:
        return _BinOp(self, "<=", _coerce(other))

    def __gt__(self, other: object) -> Expr:
        return _BinOp(self, ">", _coerce(other))

    def __ge__(self, other: object) -> Expr:
        return _BinOp(self, ">=", _coerce(other))

    # --- arithmetic ---

    def __add__(self, other: object) -> Expr:
        return _BinOp(self, "+", _coerce(other))

    def __radd__(self, other: object) -> Expr:
        return _BinOp(_coerce(other), "+", self)

    def __sub__(self, other: object) -> Expr:
        return _BinOp(self, "-", _coerce(other))

    def __rsub__(self, other: object) -> Expr:
        return _BinOp(_coerce(other), "-", self)

    def __mul__(self, other: object) -> Expr:
        return _BinOp(self, "*", _coerce(other))

    def __rmul__(self, other: object) -> Expr:
        return _BinOp(_coerce(other), "*", self)

    def __truediv__(self, other: object) -> Expr:
        return _BinOp(self, "/", _coerce(other))

    def __rtruediv__(self, other: object) -> Expr:
        return _BinOp(_coerce(other), "/", self)

    def __mod__(self, other: object) -> Expr:
        return _BinOp(self, "%", _coerce(other))

    def __neg__(self) -> Expr:
        return _UnaryOp("-", self)

    # --- logical ---

    def __and__(self, other: object) -> Expr:
        return _BinOp(self, "AND", _coerce(other))

    def __or__(self, other: object) -> Expr:
        return _BinOp(self, "OR", _coerce(other))

    def __invert__(self) -> Expr:
        return _UnaryOp("NOT", self)

    # --- null checks ---

    def is_null(self) -> Expr:
        return _Postfix(self, "IS NULL")

    def is_not_null(self) -> Expr:
        return _Postfix(self, "IS NOT NULL")

    # --- set membership ---

    def in_(self, values: list[Any]) -> Expr:
        if not values:
            return _Raw("FALSE")
        rendered = ", ".join(quote_literal(v) for v in values)
        return _Postfix(self, f"IN ({rendered})")

    def between(self, lo: Any, hi: Any) -> Expr:
        return _Between(self, _coerce(lo), _coerce(hi))

    # --- pattern matching ---

    def like(self, pattern: Any) -> Expr:
        return _BinOp(self, "LIKE", _coerce(pattern))

    def ilike(self, pattern: Any) -> Expr:
        return _BinOp(self, "ILIKE", _coerce(pattern))

    def not_like(self, pattern: Any) -> Expr:
        return _BinOp(self, "NOT LIKE", _coerce(pattern))

    def not_ilike(self, pattern: Any) -> Expr:
        return _BinOp(self, "NOT ILIKE", _coerce(pattern))

    # --- sort qualifier (used inside sort()/order_by) ---

    def asc(self, nulls_first: bool = False) -> _SortExpr:
        return _SortExpr(self, ascending=True, nulls_first=nulls_first)

    def desc(self, nulls_first: bool = True) -> _SortExpr:
        return _SortExpr(self, ascending=False, nulls_first=nulls_first)

    def __repr__(self) -> str:
        return f"Expr<{self.to_sql()}>"

    def __hash__(self) -> int:
        return id(self)


def _coerce(value: object) -> Expr:
    if isinstance(value, Expr):
        return value
    return _Literal(value)


def _arrow_type_to_sql(arrow_type: Any) -> str:
    import pyarrow as pa  # local import to keep base module light

    if isinstance(arrow_type, str):
        return arrow_type
    if isinstance(arrow_type, pa.DataType):
        # Map a few common types to their SQL names; fall back to str() for the rest.
        if pa.types.is_int8(arrow_type):
            return "TINYINT"
        if pa.types.is_int16(arrow_type):
            return "SMALLINT"
        if pa.types.is_int32(arrow_type):
            return "INT"
        if pa.types.is_int64(arrow_type):
            return "BIGINT"
        if pa.types.is_float32(arrow_type):
            return "FLOAT"
        if pa.types.is_float64(arrow_type):
            return "DOUBLE"
        if pa.types.is_boolean(arrow_type):
            return "BOOLEAN"
        if pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type):
            return "VARCHAR"
        if pa.types.is_date32(arrow_type) or pa.types.is_date64(arrow_type):
            return "DATE"
        if pa.types.is_timestamp(arrow_type):
            return "TIMESTAMP"
        return str(arrow_type).upper()
    raise TypeError(f"Unsupported cast target: {arrow_type!r}")


class _Col(Expr):
    __slots__ = ("name", "qualifier")

    def __init__(self, name: str, qualifier: str | None = None) -> None:
        self.name = name
        self.qualifier = qualifier

    def to_sql(self) -> str:
        if self.qualifier is None:
            return quote_ident(self.name)
        return f"{quote_ident(self.qualifier)}.{quote_ident(self.name)}"


class _Literal(Expr):
    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value

    def to_sql(self) -> str:
        return quote_literal(self.value)


class _Raw(Expr):
    """Escape hatch: a SQL fragment the user has vouched for."""

    __slots__ = ("sql",)

    def __init__(self, sql: str) -> None:
        self.sql = sql

    def to_sql(self) -> str:
        return self.sql


class _BinOp(Expr):
    __slots__ = ("left", "op", "right")

    def __init__(self, left: Expr, op: str, right: Expr) -> None:
        self.left = left
        self.op = op
        self.right = right

    def to_sql(self) -> str:
        return f"({self.left.to_sql()} {self.op} {self.right.to_sql()})"


class _UnaryOp(Expr):
    __slots__ = ("inner", "op")

    def __init__(self, op: str, inner: Expr) -> None:
        self.op = op
        self.inner = inner

    def to_sql(self) -> str:
        return f"({self.op} {self.inner.to_sql()})"


class _Postfix(Expr):
    __slots__ = ("inner", "suffix")

    def __init__(self, inner: Expr, suffix: str) -> None:
        self.inner = inner
        self.suffix = suffix

    def to_sql(self) -> str:
        return f"({self.inner.to_sql()} {self.suffix})"


class _Between(Expr):
    __slots__ = ("hi", "inner", "lo")

    def __init__(self, inner: Expr, lo: Expr, hi: Expr) -> None:
        self.inner = inner
        self.lo = lo
        self.hi = hi

    def to_sql(self) -> str:
        return (
            f"({self.inner.to_sql()} BETWEEN {self.lo.to_sql()} AND {self.hi.to_sql()})"
        )


class _Alias(Expr):
    __slots__ = ("inner", "name")

    def __init__(self, inner: Expr, name: str) -> None:
        self.inner = inner
        self.name = name

    def to_sql(self) -> str:
        return f"{self.inner.to_sql()} AS {quote_ident(self.name)}"


class _Cast(Expr):
    __slots__ = ("inner", "is_try", "type_sql")

    def __init__(self, inner: Expr, type_sql: str, is_try: bool = False) -> None:
        self.inner = inner
        self.type_sql = type_sql
        self.is_try = is_try

    def to_sql(self) -> str:
        func = "TRY_CAST" if self.is_try else "CAST"
        return f"{func}({self.inner.to_sql()} AS {self.type_sql})"


class _Func(Expr):
    """A scalar/aggregate function call: ``name(arg, arg, ...)``."""

    __slots__ = ("args", "distinct", "filter_pred", "name")

    def __init__(
        self,
        name: str,
        args: list[Expr],
        distinct: bool = False,
        filter_pred: Expr | None = None,
    ) -> None:
        self.name = name
        self.args = args
        self.distinct = distinct
        self.filter_pred = filter_pred

    def to_sql(self) -> str:
        prefix = "DISTINCT " if self.distinct else ""
        if not self.args:
            call = f"{self.name}()"
        else:
            rendered = ", ".join(a.to_sql() for a in self.args)
            call = f"{self.name}({prefix}{rendered})"
        if self.filter_pred is not None:
            call = f"{call} FILTER (WHERE {self.filter_pred.to_sql()})"
        return call

    def filter(self, predicate: Expr) -> _Func:
        """Attach a ``FILTER (WHERE ...)`` clause to this aggregate call.

        Example: ``F.sum(col("amt")).filter(col("status") == "paid")``.
        """
        return _Func(self.name, self.args, self.distinct, filter_pred=predicate)

    def over(
        self,
        partition_by: list[Expr] | None = None,
        order_by: list[Expr | _SortExpr] | None = None,
        frame: WindowFrame | None = None,
    ) -> Expr:
        return _Window(self, partition_by or [], order_by or [], frame)


class _Case(Expr):
    """CASE WHEN ... THEN ... [WHEN ... THEN ...] [ELSE ...] END."""

    __slots__ = ("branches", "else_value")

    def __init__(self) -> None:
        self.branches: list[tuple[Expr, Expr]] = []
        self.else_value: Expr | None = None

    def when(self, predicate: Expr, value: Any) -> _Case:
        self.branches.append((predicate, _coerce(value)))
        return self

    def otherwise(self, value: Any) -> _Case:
        self.else_value = _coerce(value)
        return self

    def to_sql(self) -> str:
        if not self.branches:
            raise ValueError("CASE expression has no WHEN clauses")
        parts = ["CASE"]
        for pred, val in self.branches:
            parts.append(f"WHEN {pred.to_sql()} THEN {val.to_sql()}")
        if self.else_value is not None:
            parts.append(f"ELSE {self.else_value.to_sql()}")
        parts.append("END")
        return "(" + " ".join(parts) + ")"


class _Window(Expr):
    __slots__ = ("frame", "func", "order_by", "partition_by")

    def __init__(
        self,
        func: _Func,
        partition_by: list[Expr],
        order_by: list[Expr | _SortExpr],
        frame: WindowFrame | None = None,
    ) -> None:
        self.func = func
        self.partition_by = partition_by
        self.order_by = order_by
        self.frame = frame

    def to_sql(self) -> str:
        parts = []
        if self.partition_by:
            parts.append(
                "PARTITION BY " + ", ".join(e.to_sql() for e in self.partition_by)
            )
        if self.order_by:
            parts.append("ORDER BY " + ", ".join(_sort_sql(e) for e in self.order_by))
        if self.frame is not None:
            parts.append(self.frame.to_sql())
        return f"{self.func.to_sql()} OVER ({' '.join(parts)})"


class WindowFrame:
    """A window frame: ``ROWS|RANGE|GROUPS BETWEEN <start> AND <end>``.

    Passed to :meth:`Expr.over` to bound a window function (running totals,
    moving averages). Bounds follow the datafusion-python convention:

    * ``None`` — unbounded (``UNBOUNDED PRECEDING`` at the start,
      ``UNBOUNDED FOLLOWING`` at the end).
    * ``0`` — ``CURRENT ROW``.
    * ``n > 0`` — ``n PRECEDING`` at the start, ``n FOLLOWING`` at the end.

    Example — a trailing 7-row moving average::

        F.avg(col("v")).over(
            order_by=[col("ts")],
            frame=WindowFrame("rows", 6, 0),
        )
    """

    __slots__ = ("end_bound", "start_bound", "units")

    _UNITS = ("rows", "range", "groups")

    def __init__(
        self,
        units: str,
        start_bound: int | None = None,
        end_bound: int | None = None,
    ) -> None:
        normalized = units.lower()
        if normalized not in self._UNITS:
            raise ValueError(
                f"Unknown window frame units {units!r}; "
                f"expected one of {list(self._UNITS)}"
            )
        if start_bound is not None and start_bound < 0:
            raise ValueError("start_bound must be None or a non-negative integer")
        if end_bound is not None and end_bound < 0:
            raise ValueError("end_bound must be None or a non-negative integer")
        self.units = normalized
        self.start_bound = start_bound
        self.end_bound = end_bound

    def to_sql(self) -> str:
        return (
            f"{self.units.upper()} BETWEEN "
            f"{self._bound_sql(self.start_bound, 'PRECEDING')} AND "
            f"{self._bound_sql(self.end_bound, 'FOLLOWING')}"
        )

    @staticmethod
    def _bound_sql(bound: int | None, direction: str) -> str:
        if bound is None:
            return f"UNBOUNDED {direction}"
        if bound == 0:
            return "CURRENT ROW"
        return f"{bound} {direction}"

    def __repr__(self) -> str:
        return f"WindowFrame({self.to_sql()})"


class _SortExpr:
    """An Expr together with ASC/DESC and NULLS FIRST/LAST modifiers.

    Returned by ``Expr.asc()`` / ``Expr.desc()`` and accepted by
    ``SpiceDataFrame.sort`` / window ``order_by``.
    """

    __slots__ = ("ascending", "expr", "nulls_first")

    def __init__(self, expr: Expr, ascending: bool, nulls_first: bool) -> None:
        self.expr = expr
        self.ascending = ascending
        self.nulls_first = nulls_first

    def to_sql(self) -> str:
        direction = "ASC" if self.ascending else "DESC"
        nulls = "NULLS FIRST" if self.nulls_first else "NULLS LAST"
        return f"{self.expr.to_sql()} {direction} {nulls}"


def _sort_sql(item: Expr | _SortExpr) -> str:
    if isinstance(item, _SortExpr):
        return item.to_sql()
    return item.to_sql()


# --- public builders ---


def col(name: str, qualifier: str | None = None) -> Expr:
    """Reference a column by name. ``col("city")`` -> ``"city"``."""
    return _Col(name, qualifier)


def lit(value: Any) -> Expr:
    """Wrap a Python value as a SQL literal expression."""
    return _Literal(value)


def case() -> _Case:
    """Start a CASE expression: ``case().when(pred, v).when(pred, v).otherwise(v)``."""
    return _Case()
