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
from ._sql import quote_literal


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


def stddev_pop(expr: Any) -> Expr:
    return _fn("STDDEV_POP", expr)


def stddev_samp(expr: Any) -> Expr:
    return _fn("STDDEV_SAMP", expr)


def var_pop(expr: Any) -> Expr:
    return _fn("VAR_POP", expr)


def var_samp(expr: Any) -> Expr:
    return _fn("VAR_SAMP", expr)


def approx_median(expr: Any) -> Expr:
    return _fn("APPROX_MEDIAN", expr)


def approx_percentile_cont(expr: Any, percentile: Any) -> Expr:
    """Approximate continuous percentile, e.g. ``approx_percentile_cont(col("x"), 0.95)``."""
    return _fn("APPROX_PERCENTILE_CONT", expr, percentile)


def corr(y: Any, x: Any) -> Expr:
    return _fn("CORR", y, x)


def covar_pop(y: Any, x: Any) -> Expr:
    return _fn("COVAR_POP", y, x)


def covar_samp(y: Any, x: Any) -> Expr:
    return _fn("COVAR_SAMP", y, x)


def string_agg(expr: Any, delimiter: Any) -> Expr:
    return _fn("STRING_AGG", expr, delimiter)


def bool_and(expr: Any) -> Expr:
    return _fn("BOOL_AND", expr)


def bool_or(expr: Any) -> Expr:
    return _fn("BOOL_OR", expr)


def bit_and(expr: Any) -> Expr:
    return _fn("BIT_AND", expr)


def bit_or(expr: Any) -> Expr:
    return _fn("BIT_OR", expr)


def bit_xor(expr: Any) -> Expr:
    return _fn("BIT_XOR", expr)


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


def log2(expr: Any) -> Expr:
    return _fn("LOG2", expr)


def log10(expr: Any) -> Expr:
    return _fn("LOG10", expr)


def cbrt(expr: Any) -> Expr:
    return _fn("CBRT", expr)


def trunc(expr: Any) -> Expr:
    return _fn("TRUNC", expr)


def signum(expr: Any) -> Expr:
    return _fn("SIGNUM", expr)


def pi() -> Expr:
    return _Func("PI", [])


def degrees(expr: Any) -> Expr:
    return _fn("DEGREES", expr)


def radians(expr: Any) -> Expr:
    return _fn("RADIANS", expr)


def gcd(a: Any, b: Any) -> Expr:
    return _fn("GCD", a, b)


def lcm(a: Any, b: Any) -> Expr:
    return _fn("LCM", a, b)


def factorial(expr: Any) -> Expr:
    return _fn("FACTORIAL", expr)


def nanvl(expr: Any, replacement: Any) -> Expr:
    return _fn("NANVL", expr, replacement)


def isnan(expr: Any) -> Expr:
    return _fn("ISNAN", expr)


def iszero(expr: Any) -> Expr:
    return _fn("ISZERO", expr)


def sin(expr: Any) -> Expr:
    return _fn("SIN", expr)


def cos(expr: Any) -> Expr:
    return _fn("COS", expr)


def tan(expr: Any) -> Expr:
    return _fn("TAN", expr)


def asin(expr: Any) -> Expr:
    return _fn("ASIN", expr)


def acos(expr: Any) -> Expr:
    return _fn("ACOS", expr)


def atan(expr: Any) -> Expr:
    return _fn("ATAN", expr)


def atan2(y: Any, x: Any) -> Expr:
    return _fn("ATAN2", y, x)


def sinh(expr: Any) -> Expr:
    return _fn("SINH", expr)


def cosh(expr: Any) -> Expr:
    return _fn("COSH", expr)


def tanh(expr: Any) -> Expr:
    return _fn("TANH", expr)


def cot(expr: Any) -> Expr:
    return _fn("COT", expr)


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


def ltrim(expr: Any) -> Expr:
    return _fn("LTRIM", expr)


def rtrim(expr: Any) -> Expr:
    return _fn("RTRIM", expr)


def btrim(expr: Any) -> Expr:
    return _fn("BTRIM", expr)


def lpad(expr: Any, length: Any, fill: Any = None) -> Expr:
    if fill is None:
        return _fn("LPAD", expr, length)
    return _fn("LPAD", expr, length, fill)


def rpad(expr: Any, length: Any, fill: Any = None) -> Expr:
    if fill is None:
        return _fn("RPAD", expr, length)
    return _fn("RPAD", expr, length, fill)


def initcap(expr: Any) -> Expr:
    return _fn("INITCAP", expr)


def left(expr: Any, n: Any) -> Expr:
    return _fn("LEFT", expr, n)


def right(expr: Any, n: Any) -> Expr:
    return _fn("RIGHT", expr, n)


def reverse(expr: Any) -> Expr:
    return _fn("REVERSE", expr)


def repeat(expr: Any, n: Any) -> Expr:
    return _fn("REPEAT", expr, n)


def translate(expr: Any, from_chars: Any, to_chars: Any) -> Expr:
    return _fn("TRANSLATE", expr, from_chars, to_chars)


def concat_ws(separator: Any, *exprs: Any) -> Expr:
    return _fn("CONCAT_WS", separator, *exprs)


def split_part(expr: Any, delimiter: Any, n: Any) -> Expr:
    return _fn("SPLIT_PART", expr, delimiter, n)


def strpos(expr: Any, substring: Any) -> Expr:
    return _fn("STRPOS", expr, substring)


def regexp_replace(
    expr: Any, pattern: Any, replacement: Any, flags: Any = None
) -> Expr:
    if flags is None:
        return _fn("REGEXP_REPLACE", expr, pattern, replacement)
    return _fn("REGEXP_REPLACE", expr, pattern, replacement, flags)


def ascii(expr: Any) -> Expr:
    return _fn("ASCII", expr)


def chr(code: Any) -> Expr:
    return _fn("CHR", code)


def to_hex(expr: Any) -> Expr:
    return _fn("TO_HEX", expr)


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


def interval(value: str) -> Expr:
    """An INTERVAL literal: ``interval("1 day")`` -> ``INTERVAL '1 day'``."""
    return _Raw("INTERVAL " + quote_literal(value))


def date_bin(stride: Any, source: Any, origin: Any = None) -> Expr:
    """Bin timestamps into fixed-width buckets (time-series downsampling).

    ``stride`` may be an interval string (``"15 minutes"``) or an Expr. Example::

        F.date_bin("1 hour", col("ts"))
    """
    stride_expr = interval(stride) if isinstance(stride, str) else _coerce(stride)
    args = [stride_expr, _coerce(source)]
    if origin is not None:
        args.append(_coerce(origin))
    return _Func("DATE_BIN", args)


def to_timestamp(expr: Any, *formats: Any) -> Expr:
    return _fn("TO_TIMESTAMP", expr, *formats)


def to_date(expr: Any, *formats: Any) -> Expr:
    return _fn("TO_DATE", expr, *formats)


def from_unixtime(expr: Any) -> Expr:
    return _fn("FROM_UNIXTIME", expr)


def to_unixtime(expr: Any) -> Expr:
    return _fn("TO_UNIXTIME", expr)


def make_date(year: Any, month: Any, day: Any) -> Expr:
    return _fn("MAKE_DATE", year, month, day)


def to_char(expr: Any, fmt: Any) -> Expr:
    return _fn("TO_CHAR", expr, fmt)


# --- null / control flow ---


def coalesce(*exprs: Any) -> Expr:
    if not exprs:
        raise ValueError("coalesce requires at least one argument")
    return _fn("COALESCE", *exprs)


def nullif(a: Any, b: Any) -> Expr:
    return _fn("NULLIF", a, b)


def ifnull(expr: Any, default: Any) -> Expr:
    return coalesce(expr, default)


def nvl(expr: Any, default: Any) -> Expr:
    """Return ``expr`` if not null, else ``default`` (like ``coalesce`` of two)."""
    return _fn("NVL", expr, default)


def greatest(*exprs: Any) -> Expr:
    if not exprs:
        raise ValueError("greatest requires at least one argument")
    return _fn("GREATEST", *exprs)


def least(*exprs: Any) -> Expr:
    if not exprs:
        raise ValueError("least requires at least one argument")
    return _fn("LEAST", *exprs)


def case() -> _Case:
    """Start a CASE expression. See :func:`spicepy.case`."""
    return _case_builder()


# --- arrays ---


def make_array(*exprs: Any) -> Expr:
    """Construct an array from the given elements: ``make_array(1, 2, 3)``."""
    return _fn("MAKE_ARRAY", *exprs)


def array(*exprs: Any) -> Expr:
    """Alias for :func:`make_array`."""
    return make_array(*exprs)


def array_element(array: Any, n: Any) -> Expr:
    """Element at 1-based index ``n`` (SQL convention). See also ``expr[i]``."""
    return _fn("ARRAY_ELEMENT", array, n)


def array_length(array: Any, dimension: Any = None) -> Expr:
    if dimension is None:
        return _fn("ARRAY_LENGTH", array)
    return _fn("ARRAY_LENGTH", array, dimension)


def array_append(array: Any, element: Any) -> Expr:
    return _fn("ARRAY_APPEND", array, element)


def array_prepend(element: Any, array: Any) -> Expr:
    return _fn("ARRAY_PREPEND", element, array)


def array_concat(*arrays: Any) -> Expr:
    return _fn("ARRAY_CONCAT", *arrays)


def array_has(array: Any, element: Any) -> Expr:
    """True if ``array`` contains ``element``."""
    return _fn("ARRAY_HAS", array, element)


def array_has_all(array: Any, sub_array: Any) -> Expr:
    return _fn("ARRAY_HAS_ALL", array, sub_array)


def array_has_any(array: Any, other: Any) -> Expr:
    return _fn("ARRAY_HAS_ANY", array, other)


def array_position(array: Any, element: Any) -> Expr:
    return _fn("ARRAY_POSITION", array, element)


def array_slice(array: Any, begin: Any, end: Any, stride: Any = None) -> Expr:
    """Slice with 1-based inclusive bounds (SQL convention)."""
    if stride is None:
        return _fn("ARRAY_SLICE", array, begin, end)
    return _fn("ARRAY_SLICE", array, begin, end, stride)


def array_distinct(array: Any) -> Expr:
    return _fn("ARRAY_DISTINCT", array)


def array_remove(array: Any, element: Any) -> Expr:
    return _fn("ARRAY_REMOVE", array, element)


def array_to_string(array: Any, delimiter: Any) -> Expr:
    return _fn("ARRAY_TO_STRING", array, delimiter)


def string_to_array(string: Any, delimiter: Any) -> Expr:
    return _fn("STRING_TO_ARRAY", string, delimiter)


def array_reverse(array: Any) -> Expr:
    return _fn("ARRAY_REVERSE", array)


def array_sort(array: Any) -> Expr:
    return _fn("ARRAY_SORT", array)


def array_dims(array: Any) -> Expr:
    return _fn("ARRAY_DIMS", array)


def array_union(a: Any, b: Any) -> Expr:
    return _fn("ARRAY_UNION", a, b)


def array_intersect(a: Any, b: Any) -> Expr:
    return _fn("ARRAY_INTERSECT", a, b)


def array_except(a: Any, b: Any) -> Expr:
    return _fn("ARRAY_EXCEPT", a, b)


def array_repeat(element: Any, count: Any) -> Expr:
    return _fn("ARRAY_REPEAT", element, count)


def array_distance(a: Any, b: Any) -> Expr:
    """Euclidean (L2) distance between two equal-length numeric arrays."""
    return _fn("ARRAY_DISTANCE", a, b)


def flatten(array: Any) -> Expr:
    return _fn("FLATTEN", array)


def cardinality(array: Any) -> Expr:
    return _fn("CARDINALITY", array)


# --- structs ---


def struct(*exprs: Any) -> Expr:
    """Construct an unnamed struct from the given values."""
    return _fn("STRUCT", *exprs)


def named_struct(**fields: Any) -> Expr:
    """Construct a struct with named fields: ``named_struct(x=1, y=2)``."""
    if not fields:
        raise ValueError("named_struct requires at least one field")
    args: list[Any] = []
    for name, value in fields.items():
        args.append(name)
        args.append(value)
    return _fn("NAMED_STRUCT", *args)


def get_field(expr: Any, name: Any) -> Expr:
    """Extract a struct/map field by name. ``col("s")["x"]`` is shorthand."""
    return _fn("GET_FIELD", expr, name)


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


def ntile(n: Any) -> _Func:
    return _Func("NTILE", [_coerce(n)])


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
