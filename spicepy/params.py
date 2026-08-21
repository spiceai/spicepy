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

    Args:
        value: The Python value to infer the type from

    Returns:
        The inferred Arrow data type

    Raises:
        TypeError: If the type cannot be inferred
    """
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
