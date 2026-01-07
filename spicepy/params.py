"""Parameter types for parameterized queries.

This module provides a Param class and helper functions for creating typed parameters
to use with parameterized queries. Parameters can be:
- Simple Python values (int, str, float, etc.) - type will be inferred
- Param instances with explicit Arrow type annotation

Example:
    # With automatic type inference
    reader = client.query(
        "SELECT * FROM table WHERE id = $1 AND name = $2",
        params=[123, "test"]
    )

    # With explicit types
    reader = client.query(
        "SELECT * FROM table WHERE id = $1 AND name = $2",
        params=[Param.int32(123), Param.string("test")]
    )
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Optional

import pyarrow as pa


@dataclass
class Param:
    """A query parameter with an optional explicit Arrow type.
    If type is None, the type will be inferred from the value.
    """

    value: Any
    arrow_type: Optional[pa.DataType] = None

    def has_explicit_type(self) -> bool:
        """Returns True if this parameter has an explicit type."""
        return self.arrow_type is not None

    # Integer types
    @classmethod
    def int8(cls, value: int) -> "Param":
        """Create an int8 parameter."""
        return cls(value, pa.int8())

    @classmethod
    def int16(cls, value: int) -> "Param":
        """Create an int16 parameter."""
        return cls(value, pa.int16())

    @classmethod
    def int32(cls, value: int) -> "Param":
        """Create an int32 parameter."""
        return cls(value, pa.int32())

    @classmethod
    def int64(cls, value: int) -> "Param":
        """Create an int64 parameter."""
        return cls(value, pa.int64())

    # Unsigned integer types
    @classmethod
    def uint8(cls, value: int) -> "Param":
        """Create a uint8 parameter."""
        return cls(value, pa.uint8())

    @classmethod
    def uint16(cls, value: int) -> "Param":
        """Create a uint16 parameter."""
        return cls(value, pa.uint16())

    @classmethod
    def uint32(cls, value: int) -> "Param":
        """Create a uint32 parameter."""
        return cls(value, pa.uint32())

    @classmethod
    def uint64(cls, value: int) -> "Param":
        """Create a uint64 parameter."""
        return cls(value, pa.uint64())

    # Floating point types
    @classmethod
    def float16(cls, value: float) -> "Param":
        """Create a float16 parameter."""
        return cls(value, pa.float16())

    @classmethod
    def float32(cls, value: float) -> "Param":
        """Create a float32 parameter."""
        return cls(value, pa.float32())

    @classmethod
    def float64(cls, value: float) -> "Param":
        """Create a float64 parameter."""
        return cls(value, pa.float64())

    # String and binary types
    @classmethod
    def string(cls, value: str) -> "Param":
        """Create a string (utf8) parameter."""
        return cls(value, pa.string())

    @classmethod
    def large_string(cls, value: str) -> "Param":
        """Create a large string parameter for strings > 2GB."""
        return cls(value, pa.large_string())

    @classmethod
    def binary(cls, value: bytes) -> "Param":
        """Create a binary parameter."""
        return cls(value, pa.binary())

    @classmethod
    def large_binary(cls, value: bytes) -> "Param":
        """Create a large binary parameter for data > 2GB."""
        return cls(value, pa.large_binary())

    @classmethod
    def fixed_size_binary(cls, value: bytes, size: int) -> "Param":
        """Create a fixed-size binary parameter."""
        return cls(value, pa.binary(size))

    # Boolean type
    @classmethod
    def bool_(cls, value: bool) -> "Param":
        """Create a boolean parameter."""
        return cls(value, pa.bool_())

    # Temporal types
    @classmethod
    def date32(cls, value: date) -> "Param":
        """Create a date32 parameter (days since epoch)."""
        return cls(value, pa.date32())

    @classmethod
    def date64(cls, value: date) -> "Param":
        """Create a date64 parameter (milliseconds since epoch)."""
        return cls(value, pa.date64())

    @classmethod
    def time32(cls, value: time, unit: str = "ms") -> "Param":
        """Create a time32 parameter.

        Args:
            value: Time value
            unit: Time unit - 's' (seconds) or 'ms' (milliseconds)
        """
        return cls(value, pa.time32(unit))

    @classmethod
    def time64(cls, value: time, unit: str = "us") -> "Param":
        """Create a time64 parameter.

        Args:
            value: Time value
            unit: Time unit - 'us' (microseconds) or 'ns' (nanoseconds)
        """
        return cls(value, pa.time64(unit))

    @classmethod
    def timestamp(cls, value: datetime, unit: str = "us", tz: Optional[str] = None) -> "Param":
        """Create a timestamp parameter.

        Args:
            value: Datetime value
            unit: Time unit - 's', 'ms', 'us', or 'ns'
            tz: Optional timezone string (e.g., 'UTC', 'America/New_York')
        """
        return cls(value, pa.timestamp(unit, tz=tz))

    @classmethod
    def duration(cls, value: timedelta, unit: str = "us") -> "Param":
        """Create a duration parameter.

        Args:
            value: Timedelta value
            unit: Time unit - 's', 'ms', 'us', or 'ns'
        """
        return cls(value, pa.duration(unit))

    # Decimal types
    @classmethod
    def decimal128(cls, value: Decimal, precision: int = 38, scale: int = 9) -> "Param":
        """Create a decimal128 parameter.

        Args:
            value: Decimal value
            precision: Total number of digits (default 38)
            scale: Number of digits after decimal point (default 9)
        """
        return cls(value, pa.decimal128(precision, scale))

    @classmethod
    def decimal256(cls, value: Decimal, precision: int = 76, scale: int = 38) -> "Param":
        """Create a decimal256 parameter.

        Args:
            value: Decimal value
            precision: Total number of digits (default 76)
            scale: Number of digits after decimal point (default 38)
        """
        return cls(value, pa.decimal256(precision, scale))

    # Null type
    @classmethod
    def null(cls) -> "Param":
        """Create a null parameter."""
        return cls(None, pa.null())

    # Generic factory methods
    @classmethod
    def of(cls, value: Any, arrow_type: Optional[pa.DataType] = None) -> "Param":
        """Create a parameter with optional explicit type.

        Args:
            value: The parameter value
            arrow_type: Optional explicit Arrow type (if None, type will be inferred)
        """
        return cls(value, arrow_type)


def infer_arrow_type(value: Any) -> pa.DataType:
    """Infer the Arrow data type from a Python value.

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
