"""Unit tests for spicepy.params module."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pyarrow as pa
import pytest

from spicepy.params import infer_arrow_type


class TestInferArrowType:
    """Test infer_arrow_type function."""

    def test_infer_none(self) -> None:
        """Test inference of None."""
        assert infer_arrow_type(None) == pa.null()

    def test_infer_bool_true(self) -> None:
        """Test inference of True."""
        assert infer_arrow_type(True) == pa.bool_()

    def test_infer_bool_false(self) -> None:
        """Test inference of False."""
        assert infer_arrow_type(False) == pa.bool_()

    def test_infer_int(self) -> None:
        """Test inference of int."""
        assert infer_arrow_type(42) == pa.int64()

    def test_infer_int_zero(self) -> None:
        """Test inference of zero."""
        assert infer_arrow_type(0) == pa.int64()

    def test_infer_int_negative(self) -> None:
        """Test inference of negative int."""
        assert infer_arrow_type(-42) == pa.int64()

    def test_infer_int_large(self) -> None:
        """Test inference of large int."""
        assert infer_arrow_type(2**60) == pa.int64()

    def test_infer_float(self) -> None:
        """Test inference of float."""
        assert infer_arrow_type(3.14) == pa.float64()

    def test_infer_float_zero(self) -> None:
        """Test inference of float zero."""
        assert infer_arrow_type(0.0) == pa.float64()

    def test_infer_float_negative(self) -> None:
        """Test inference of negative float."""
        assert infer_arrow_type(-273.15) == pa.float64()

    def test_infer_string(self) -> None:
        """Test inference of string."""
        assert infer_arrow_type("hello") == pa.string()

    def test_infer_string_empty(self) -> None:
        """Test inference of empty string."""
        assert infer_arrow_type("") == pa.string()

    def test_infer_bytes(self) -> None:
        """Test inference of bytes."""
        assert infer_arrow_type(b"\x00\x01") == pa.binary()

    def test_infer_bytes_empty(self) -> None:
        """Test inference of empty bytes."""
        assert infer_arrow_type(b"") == pa.binary()

    def test_infer_decimal(self) -> None:
        """Test inference of Decimal."""
        assert infer_arrow_type(Decimal("123.45")) == pa.decimal128(38, 9)

    def test_infer_datetime(self) -> None:
        """Test inference of datetime."""
        dt = datetime(2024, 1, 15, 10, 30, 45)
        assert infer_arrow_type(dt) == pa.timestamp("us", tz=None)

    def test_infer_date(self) -> None:
        """Test inference of date."""
        d = date(2024, 1, 15)
        assert infer_arrow_type(d) == pa.date32()

    def test_infer_time(self) -> None:
        """Test inference of time."""
        t = time(10, 30, 45)
        assert infer_arrow_type(t) == pa.time64("us")

    def test_infer_timedelta(self) -> None:
        """Test inference of timedelta."""
        td = timedelta(days=1)
        assert infer_arrow_type(td) == pa.duration("us")

    def test_infer_list_raises(self) -> None:
        """Test that list raises TypeError."""
        with pytest.raises(TypeError, match="Unsupported parameter type: list"):
            infer_arrow_type([1, 2, 3])

    def test_infer_dict_raises(self) -> None:
        """Test that dict raises TypeError."""
        with pytest.raises(TypeError, match="Unsupported parameter type: dict"):
            infer_arrow_type({"key": "value"})

    def test_infer_tuple_raises(self) -> None:
        """Test that tuple raises TypeError."""
        with pytest.raises(TypeError, match="Unsupported parameter type: tuple"):
            infer_arrow_type((1, 2, 3))

    def test_infer_set_raises(self) -> None:
        """Test that set raises TypeError."""
        with pytest.raises(TypeError, match="Unsupported parameter type: set"):
            infer_arrow_type({1, 2, 3})

    def test_infer_custom_object_raises(self) -> None:
        """Test that custom object raises TypeError."""

        class CustomClass:
            pass

        with pytest.raises(TypeError, match="Unsupported parameter type: CustomClass"):
            infer_arrow_type(CustomClass())
