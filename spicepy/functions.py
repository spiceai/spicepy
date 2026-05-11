"""Function builders for use with :class:`~spicepy.Expr` and :class:`~spicepy.SpiceDataFrame`.

Each function returns an :class:`~spicepy.Expr` representing a call to the
corresponding DataFusion built-in. Example::

    from spicepy import col
    from spicepy import functions as F

    df.group_by(col("city")).aggregate(
        F.sum(col("amount")).alias("total"),
        F.count_distinct(col("user_id")).alias("users"),
    )

Coverage is intentionally narrow: the most common scalar, aggregate, and
window functions. Anything not in this module is reachable by spelling the
call directly in SQL via :meth:`spicepy.Client.query` or via the ``_Raw``
escape hatch.
"""

from __future__ import annotations

from typing import Any

from ._expr import Expr, _Case, _coerce, _Func, _Raw
from ._expr import case as _case_builder


def _fn(name: str, *args: Any) -> Expr:
    return _Func(name, [_coerce(a) for a in args])


# --- aggregates ---


def sum(expr: Any) -> Expr:
    return _fn("SUM", expr)


def avg(expr: Any) -> Expr:
    return _fn("AVG", expr)


def mean(expr: Any) -> Expr:
    return avg(expr)


def min(expr: Any) -> Expr:
    return _fn("MIN", expr)


def max(expr: Any) -> Expr:
    return _fn("MAX", expr)


def count(expr: Any = None) -> Expr:
    if expr is None:
        return _Func("COUNT", [_Raw("*")])
    return _fn("COUNT", expr)


def count_distinct(expr: Any) -> Expr:
    return _Func("COUNT", [_coerce(expr)], distinct=True)


def stddev(expr: Any) -> Expr:
    return _fn("STDDEV", expr)


def variance(expr: Any) -> Expr:
    return _fn("VAR", expr)


def median(expr: Any) -> Expr:
    return _fn("MEDIAN", expr)


def approx_distinct(expr: Any) -> Expr:
    return _fn("APPROX_DISTINCT", expr)


def array_agg(expr: Any) -> Expr:
    return _fn("ARRAY_AGG", expr)


# --- math ---


def abs(expr: Any) -> Expr:
    return _fn("ABS", expr)


def round(expr: Any, ndigits: Any = 0) -> Expr:
    return _fn("ROUND", expr, ndigits)


def ceil(expr: Any) -> Expr:
    return _fn("CEIL", expr)


def floor(expr: Any) -> Expr:
    return _fn("FLOOR", expr)


def sqrt(expr: Any) -> Expr:
    return _fn("SQRT", expr)


def power(base: Any, exponent: Any) -> Expr:
    return _fn("POWER", base, exponent)


def ln(expr: Any) -> Expr:
    return _fn("LN", expr)


def log(expr: Any, base: Any = 10) -> Expr:
    return _fn("LOG", base, expr)


def exp(expr: Any) -> Expr:
    return _fn("EXP", expr)


# --- strings ---


def lower(expr: Any) -> Expr:
    return _fn("LOWER", expr)


def upper(expr: Any) -> Expr:
    return _fn("UPPER", expr)


def length(expr: Any) -> Expr:
    return _fn("CHAR_LENGTH", expr)


def trim(expr: Any) -> Expr:
    return _fn("TRIM", expr)


def concat(*exprs: Any) -> Expr:
    return _fn("CONCAT", *exprs)


def substr(expr: Any, start: Any, length: Any = None) -> Expr:
    if length is None:
        return _fn("SUBSTR", expr, start)
    return _fn("SUBSTR", expr, start, length)


def replace(expr: Any, search: Any, replacement: Any) -> Expr:
    return _fn("REPLACE", expr, search, replacement)


def regexp_match(expr: Any, pattern: Any) -> Expr:
    return _fn("REGEXP_MATCH", expr, pattern)


def starts_with(expr: Any, prefix: Any) -> Expr:
    return _fn("STARTS_WITH", expr, prefix)


def ends_with(expr: Any, suffix: Any) -> Expr:
    return _fn("ENDS_WITH", expr, suffix)


# --- date/time ---


def now() -> Expr:
    return _Func("NOW", [])


def current_date() -> Expr:
    return _Func("CURRENT_DATE", [])


def current_timestamp() -> Expr:
    return _Func("CURRENT_TIMESTAMP", [])


def date_trunc(part: Any, expr: Any) -> Expr:
    return _fn("DATE_TRUNC", part, expr)


def date_part(part: Any, expr: Any) -> Expr:
    return _fn("DATE_PART", part, expr)


def extract(part: Any, expr: Any) -> Expr:
    return date_part(part, expr)


# --- null / control flow ---


def coalesce(*exprs: Any) -> Expr:
    if not exprs:
        raise ValueError("coalesce requires at least one argument")
    return _fn("COALESCE", *exprs)


def nullif(a: Any, b: Any) -> Expr:
    return _fn("NULLIF", a, b)


def ifnull(expr: Any, default: Any) -> Expr:
    return coalesce(expr, default)


def case() -> _Case:
    """Start a CASE expression. See :func:`spicepy.case`."""
    return _case_builder()


# --- window-only functions ---


def row_number() -> _Func:
    return _Func("ROW_NUMBER", [])


def rank() -> _Func:
    return _Func("RANK", [])


def dense_rank() -> _Func:
    return _Func("DENSE_RANK", [])


def percent_rank() -> _Func:
    return _Func("PERCENT_RANK", [])


def cume_dist() -> _Func:
    return _Func("CUME_DIST", [])


def lag(expr: Any, offset: Any = 1, default: Any = None) -> _Func:
    args: list[Expr] = [_coerce(expr), _coerce(offset)]
    if default is not None:
        args.append(_coerce(default))
    return _Func("LAG", args)


def lead(expr: Any, offset: Any = 1, default: Any = None) -> _Func:
    args: list[Expr] = [_coerce(expr), _coerce(offset)]
    if default is not None:
        args.append(_coerce(default))
    return _Func("LEAD", args)


def first_value(expr: Any) -> _Func:
    return _Func("FIRST_VALUE", [_coerce(expr)])


def last_value(expr: Any) -> _Func:
    return _Func("LAST_VALUE", [_coerce(expr)])


def nth_value(expr: Any, n: Any) -> _Func:
    return _Func("NTH_VALUE", [_coerce(expr), _coerce(n)])
