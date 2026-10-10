"""Parameter utilities for parameterized queries.

This module provides helper functions for creating typed parameters
to use with parameterized queries. Parameters can be:
- Simple Python values (int, str, float, etc.) - type will be inferred automatically
- Tuples of (value, pyarrow.DataType) for explicit type control

Example:
    # With automatic type inference
    reader = client.sql_with_params(
        "SELECT * FROM table WHERE id = $1 AND name = $2",
        [123, "test"]
    )

    # With explicit PyArrow types
    import pyarrow as pa
    reader = client.sql_with_params(
        "SELECT * FROM table WHERE id = $1 AND amount = $2",
        [(123, pa.int32()), (99.99, pa.float64())]
    )
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa


def infer_arrow_type(value: Any) -> pa.DataType:
    """Infer the Arrow data type from a Python value.

    The following Python types are automatically mapped to Arrow types:
    - None → null
    - bool → bool_
    - int → int64
    - float → float64
    - str → string
    - bytes → binary
    - Decimal → decimal128(38, 9)
    - datetime → timestamp("us")
    - date → date32
    - time → time64("us")
    - timedelta → duration("us")
    - pandas.Timestamp → timestamp in its own unit, so nanoseconds survive
    - pandas.Timedelta → duration in its own unit
    - numpy scalars, as read out of a DataFrame or array: integers, floats and
      bool_ keep their numpy type (int32 → int32), datetime64[D] → date32,
      other datetime64 → timestamp and timedelta64 → duration, both in the
      nearest unit Arrow supports. A month or year timedelta64 has no fixed
      length and is rejected

    Args:
        value: The Python value to infer the type from

    Returns:
        The inferred Arrow data type

    Raises:
        TypeError: If the type cannot be inferred
    """
    return _normalize(value)[1]


def param_array(value: Any) -> pa.Array:
    """Build the one-element Arrow array that binds ``value`` as a parameter.

    The array's type is :func:`infer_arrow_type` of ``value``. A numpy
    ``datetime64`` or ``timedelta64`` is first converted to the pandas or
    Python value Arrow can build an array from, because Arrow rejects most of
    their units (``datetime64[D]``, ``timedelta64[m]``) directly.

    Raises:
        TypeError: If the type cannot be inferred
    """
    normalized, arrow_type = _normalize(value)
    return pa.array([normalized], type=arrow_type)


def _normalize(value: Any) -> tuple[Any, pa.DataType]:
    """Return ``value`` in a form ``pa.array`` accepts, with its Arrow type."""
    if isinstance(value, np.datetime64 | np.timedelta64):
        value = _without_unit_multiplier(value)
    if isinstance(value, np.datetime64):
        unit = np.datetime_data(value.dtype)[0]
        if unit in _DATE_UNITS:
            if np.isnat(value):
                return None, pa.date32()
            return value.astype("datetime64[D]").item(), pa.date32()
        if np.isnat(value):
            return None, pa.timestamp(_arrow_unit(unit))
        value = pd.Timestamp(value)
    elif isinstance(value, np.timedelta64):
        _reject_calendar_duration(value)
        if np.isnat(value):
            return None, pa.duration(_arrow_unit(np.datetime_data(value.dtype)[0]))
        value = _timedelta64_to_pandas(value)
    elif isinstance(value, np.bool_ | np.integer | np.floating):
        return value, pa.from_numpy_dtype(value.dtype)

    if value is pd.NaT:
        return None, pa.timestamp("ns")
    if isinstance(value, pd.Timestamp):
        return value, pa.timestamp(value.unit)
    if isinstance(value, pd.Timedelta):
        return value, pa.duration(value.unit)
    return value, _infer_python_type(value)


_DATE_UNITS = ("Y", "M", "W", "D")
_SUB_NANOSECOND_UNITS = {"ps": 10**3, "fs": 10**6, "as": 10**9}
_CALENDAR_UNITS = ("Y", "M")


def _reject_calendar_duration(value: np.timedelta64) -> None:
    """Refuse a month or year ``timedelta64``, which has no fixed length.

    Raises:
        TypeError: If ``value`` counts months or years
    """
    if np.datetime_data(value.dtype)[0] in _CALENDAR_UNITS:
        raise TypeError(
            f"Unsupported parameter value: {value!r} is a calendar duration "
            "with no fixed length; convert it to days or a finer unit first"
        )


def _timedelta64_to_pandas(value: np.timedelta64) -> pd.Timedelta:
    """Convert a non-NaT ``timedelta64`` to a ``pd.Timedelta``."""
    unit = np.datetime_data(value.dtype)[0]
    if unit in _SUB_NANOSECOND_UNITS:
        # Floor in Python integers: numpy's own conversion floors too, but
        # wraps around near the int64 minimum and flips the sign.
        ticks = int(value.astype(np.int64))
        value = np.timedelta64(ticks // _SUB_NANOSECOND_UNITS[unit], "ns")
    return pd.Timedelta(value)


def _without_unit_multiplier(value: Any) -> Any:
    """Return a ``datetime64``/``timedelta64`` in its dtype's base unit.

    A dtype like ``timedelta64[2s]`` counts in steps of two seconds, so its
    stored integer is half the number of seconds. Neither pandas nor Arrow
    reads the multiplier, so the value is rescaled to ``timedelta64[s]``
    first, keeping the instant or duration it stands for. A unit finer than a
    nanosecond is rescaled straight to nanoseconds, flooring, so a value whose
    tick count only overflows before that reduction still binds.

    Raises:
        TypeError: If the rescaled value does not fit in 64 bits
    """
    unit, count = np.datetime_data(value.dtype)
    if count == 1 or np.isnat(value):
        return value
    ticks = int(value.astype(np.int64)) * count
    if unit in _SUB_NANOSECOND_UNITS:
        ticks //= _SUB_NANOSECOND_UNITS[unit]
        unit = "ns"
    if not np.iinfo(np.int64).min < ticks <= np.iinfo(np.int64).max:
        kind = "datetime64" if isinstance(value, np.datetime64) else "timedelta64"
        raise TypeError(
            f"Unsupported parameter value: {value!r} does not fit in {kind}[{unit}]"
        )
    return type(value)(ticks, unit)


def _arrow_unit(numpy_unit: str) -> str:
    """Return the Arrow time unit nearest a numpy one, as pandas would pick it.

    Units coarser than a second become seconds and units finer than a
    nanosecond become nanoseconds, so a NaT binds with the same type a
    non-null value of its dtype does. A unitless NaT is nanoseconds, like
    ``pd.NaT``.
    """
    if numpy_unit in ("ms", "us", "ns"):
        return numpy_unit
    if numpy_unit in ("W", "D", "h", "m", "s"):
        return "s"
    return "ns"


def _infer_python_type(value: Any) -> pa.DataType:
    if value is None:
        return pa.null()
    if isinstance(value, bool):
        return pa.bool_()
    if isinstance(value, int):
        return pa.int64()
    if isinstance(value, float):
        return pa.float64()
    if isinstance(value, str):
        return pa.string()
    if isinstance(value, bytes):
        return pa.binary()
    if isinstance(value, Decimal):
        return pa.decimal128(38, 9)
    if isinstance(value, datetime):
        return pa.timestamp("us", tz=None)
    if isinstance(value, date):
        return pa.date32()
    if isinstance(value, time):
        return pa.time64("us")
    if isinstance(value, timedelta):
        return pa.duration("us")

    raise TypeError(f"Unsupported parameter type: {type(value).__name__}")
