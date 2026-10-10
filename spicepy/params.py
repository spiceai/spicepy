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
      nearest unit Arrow supports

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
    if isinstance(value, np.datetime64):
        if np.isnat(value):
            return None, pa.timestamp("ns")
        if np.datetime_data(value.dtype)[0] in ("Y", "M", "W", "D"):
            return value.astype("datetime64[D]").item(), pa.date32()
        value = pd.Timestamp(value)
    elif isinstance(value, np.timedelta64):
        if np.isnat(value):
            return None, pa.duration("ns")
        value = pd.Timedelta(value)
    elif isinstance(value, np.bool_ | np.integer | np.floating):
        return value, pa.from_numpy_dtype(value.dtype)

    if value is pd.NaT:
        return None, pa.timestamp("ns")
    if isinstance(value, pd.Timestamp):
        return value, pa.timestamp(value.unit)
    if isinstance(value, pd.Timedelta):
        return value, pa.duration(value.unit)
    return value, _infer_python_type(value)


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
