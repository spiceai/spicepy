"""Comprehensive unit tests for spicepy.params module."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pyarrow as pa
import pytest

from spicepy import Param
from spicepy.params import infer_arrow_type


class TestParamDataclass:
    """Test Param dataclass basic functionality."""

    def test_param_creation_with_value_only(self) -> None:
        """Test creating a Param with just a value."""
        param = Param(value=42)
        assert param.value == 42
        assert param.arrow_type is None

    def test_param_creation_with_type(self) -> None:
        """Test creating a Param with value and type."""
        param = Param(value=42, arrow_type=pa.int32())
        assert param.value == 42
        assert param.arrow_type == pa.int32()

    def test_has_explicit_type_true(self) -> None:
        """Test has_explicit_type returns True when type is set."""
        param = Param(value=42, arrow_type=pa.int32())
        assert param.has_explicit_type() is True

    def test_has_explicit_type_false(self) -> None:
        """Test has_explicit_type returns False when type is None."""
        param = Param(value=42)
        assert param.has_explicit_type() is False

    def test_param_equality(self) -> None:
        """Test Param equality comparison."""
        param1 = Param(value=42, arrow_type=pa.int32())
        param2 = Param(value=42, arrow_type=pa.int32())
        assert param1 == param2

    def test_param_inequality_value(self) -> None:
        """Test Param inequality with different values."""
        param1 = Param(value=42, arrow_type=pa.int32())
        param2 = Param(value=43, arrow_type=pa.int32())
        assert param1 != param2

    def test_param_inequality_type(self) -> None:
        """Test Param inequality with different types."""
        param1 = Param(value=42, arrow_type=pa.int32())
        param2 = Param(value=42, arrow_type=pa.int64())
        assert param1 != param2


class TestIntegerFactoryMethods:
    """Test Param integer factory methods."""

    def test_int8(self) -> None:
        """Test int8 factory method."""
        param = Param.int8(127)
        assert param.value == 127
        assert param.arrow_type == pa.int8()
        assert param.has_explicit_type()

    def test_int8_min(self) -> None:
        """Test int8 with minimum value."""
        param = Param.int8(-128)
        assert param.value == -128
        assert param.arrow_type == pa.int8()

    def test_int16(self) -> None:
        """Test int16 factory method."""
        param = Param.int16(32767)
        assert param.value == 32767
        assert param.arrow_type == pa.int16()

    def test_int16_min(self) -> None:
        """Test int16 with minimum value."""
        param = Param.int16(-32768)
        assert param.value == -32768

    def test_int32(self) -> None:
        """Test int32 factory method."""
        param = Param.int32(2147483647)
        assert param.value == 2147483647
        assert param.arrow_type == pa.int32()

    def test_int32_zero(self) -> None:
        """Test int32 with zero."""
        param = Param.int32(0)
        assert param.value == 0

    def test_int64(self) -> None:
        """Test int64 factory method."""
        param = Param.int64(9223372036854775807)
        assert param.value == 9223372036854775807
        assert param.arrow_type == pa.int64()

    def test_int64_negative(self) -> None:
        """Test int64 with large negative value."""
        param = Param.int64(-9223372036854775808)
        assert param.value == -9223372036854775808


class TestUnsignedIntegerFactoryMethods:
    """Test Param unsigned integer factory methods."""

    def test_uint8(self) -> None:
        """Test uint8 factory method."""
        param = Param.uint8(255)
        assert param.value == 255
        assert param.arrow_type == pa.uint8()

    def test_uint8_zero(self) -> None:
        """Test uint8 with zero."""
        param = Param.uint8(0)
        assert param.value == 0

    def test_uint16(self) -> None:
        """Test uint16 factory method."""
        param = Param.uint16(65535)
        assert param.value == 65535
        assert param.arrow_type == pa.uint16()

    def test_uint32(self) -> None:
        """Test uint32 factory method."""
        param = Param.uint32(4294967295)
        assert param.value == 4294967295
        assert param.arrow_type == pa.uint32()

    def test_uint64(self) -> None:
        """Test uint64 factory method."""
        param = Param.uint64(18446744073709551615)
        assert param.value == 18446744073709551615
        assert param.arrow_type == pa.uint64()


class TestFloatFactoryMethods:
    """Test Param floating point factory methods."""

    def test_float16(self) -> None:
        """Test float16 factory method."""
        param = Param.float16(1.5)
        assert param.value == 1.5
        assert param.arrow_type == pa.float16()

    def test_float32(self) -> None:
        """Test float32 factory method."""
        param = Param.float32(3.14159)
        assert param.value == 3.14159
        assert param.arrow_type == pa.float32()

    def test_float32_zero(self) -> None:
        """Test float32 with zero."""
        param = Param.float32(0.0)
        assert param.value == 0.0

    def test_float32_negative(self) -> None:
        """Test float32 with negative value."""
        param = Param.float32(-273.15)
        assert param.value == -273.15

    def test_float64(self) -> None:
        """Test float64 factory method."""
        param = Param.float64(2.718281828459045)
        assert param.value == 2.718281828459045
        assert param.arrow_type == pa.float64()

    def test_float64_scientific_notation(self) -> None:
        """Test float64 with scientific notation."""
        param = Param.float64(1.23e-10)
        assert param.value == 1.23e-10

    def test_float64_infinity(self) -> None:
        """Test float64 with infinity."""
        param = Param.float64(float("inf"))
        assert param.value == float("inf")

    def test_float64_negative_infinity(self) -> None:
        """Test float64 with negative infinity."""
        param = Param.float64(float("-inf"))
        assert param.value == float("-inf")


class TestStringFactoryMethods:
    """Test Param string factory methods."""

    def test_string(self) -> None:
        """Test string factory method."""
        param = Param.string("hello world")
        assert param.value == "hello world"
        assert param.arrow_type == pa.string()

    def test_string_empty(self) -> None:
        """Test string with empty value."""
        param = Param.string("")
        assert param.value == ""
        assert param.arrow_type == pa.string()

    def test_string_unicode(self) -> None:
        """Test string with unicode characters."""
        param = Param.string("测试 🚀 тест émoji")
        assert param.value == "测试 🚀 тест émoji"

    def test_string_newlines(self) -> None:
        """Test string with newlines."""
        param = Param.string("line1\nline2\rline3\r\nline4")
        assert param.value == "line1\nline2\rline3\r\nline4"

    def test_string_special_chars(self) -> None:
        """Test string with special characters."""
        param = Param.string("tab\there, null\x00char, backslash\\")
        assert param.value == "tab\there, null\x00char, backslash\\"

    def test_large_string(self) -> None:
        """Test large_string factory method."""
        param = Param.large_string("large content")
        assert param.value == "large content"
        assert param.arrow_type == pa.large_string()


class TestBinaryFactoryMethods:
    """Test Param binary factory methods."""

    def test_binary(self) -> None:
        """Test binary factory method."""
        param = Param.binary(b"\x00\x01\x02\xff")
        assert param.value == b"\x00\x01\x02\xff"
        assert param.arrow_type == pa.binary()

    def test_binary_empty(self) -> None:
        """Test binary with empty value."""
        param = Param.binary(b"")
        assert param.value == b""

    def test_large_binary(self) -> None:
        """Test large_binary factory method."""
        param = Param.large_binary(b"\x00\x01\x02")
        assert param.value == b"\x00\x01\x02"
        assert param.arrow_type == pa.large_binary()

    def test_fixed_size_binary(self) -> None:
        """Test fixed_size_binary factory method."""
        param = Param.fixed_size_binary(b"\x00\x01\x02\x03", 4)
        assert param.value == b"\x00\x01\x02\x03"
        assert param.arrow_type == pa.binary(4)


class TestBooleanFactoryMethod:
    """Test Param boolean factory method."""

    def test_bool_true(self) -> None:
        """Test bool_ factory with True."""
        param = Param.bool_(True)
        assert param.value is True
        assert param.arrow_type == pa.bool_()

    def test_bool_false(self) -> None:
        """Test bool_ factory with False."""
        param = Param.bool_(False)
        assert param.value is False
        assert param.arrow_type == pa.bool_()


class TestTemporalFactoryMethods:
    """Test Param temporal factory methods."""

    def test_date32(self) -> None:
        """Test date32 factory method."""
        d = date(2024, 1, 15)
        param = Param.date32(d)
        assert param.value == d
        assert param.arrow_type == pa.date32()

    def test_date32_epoch(self) -> None:
        """Test date32 with epoch date."""
        d = date(1970, 1, 1)
        param = Param.date32(d)
        assert param.value == d

    def test_date64(self) -> None:
        """Test date64 factory method."""
        d = date(2024, 1, 15)
        param = Param.date64(d)
        assert param.value == d
        assert param.arrow_type == pa.date64()

    def test_time32_default(self) -> None:
        """Test time32 factory with default unit."""
        t = time(10, 30, 45)
        param = Param.time32(t)
        assert param.value == t
        assert param.arrow_type == pa.time32("ms")

    def test_time32_seconds(self) -> None:
        """Test time32 factory with seconds unit."""
        t = time(10, 30, 45)
        param = Param.time32(t, unit="s")
        assert param.arrow_type == pa.time32("s")

    def test_time64_default(self) -> None:
        """Test time64 factory with default unit."""
        t = time(10, 30, 45, 123456)
        param = Param.time64(t)
        assert param.value == t
        assert param.arrow_type == pa.time64("us")

    def test_time64_nanoseconds(self) -> None:
        """Test time64 factory with nanoseconds unit."""
        t = time(10, 30, 45)
        param = Param.time64(t, unit="ns")
        assert param.arrow_type == pa.time64("ns")

    def test_timestamp_default(self) -> None:
        """Test timestamp factory with default options."""
        dt = datetime(2024, 1, 15, 10, 30, 45)
        param = Param.timestamp(dt)
        assert param.value == dt
        assert param.arrow_type == pa.timestamp("us")

    def test_timestamp_with_timezone(self) -> None:
        """Test timestamp factory with timezone."""
        dt = datetime(2024, 1, 15, 10, 30, 45)
        param = Param.timestamp(dt, tz="UTC")
        assert param.arrow_type == pa.timestamp("us", tz="UTC")

    def test_timestamp_milliseconds(self) -> None:
        """Test timestamp factory with milliseconds."""
        dt = datetime(2024, 1, 15, 10, 30, 45)
        param = Param.timestamp(dt, unit="ms")
        assert param.arrow_type == pa.timestamp("ms")

    def test_duration_default(self) -> None:
        """Test duration factory with default unit."""
        td = timedelta(days=1, hours=2, minutes=30)
        param = Param.duration(td)
        assert param.value == td
        assert param.arrow_type == pa.duration("us")

    def test_duration_seconds(self) -> None:
        """Test duration factory with seconds unit."""
        td = timedelta(seconds=3600)
        param = Param.duration(td, unit="s")
        assert param.arrow_type == pa.duration("s")


class TestDecimalFactoryMethods:
    """Test Param decimal factory methods."""

    def test_decimal128_default(self) -> None:
        """Test decimal128 with default precision/scale."""
        d = Decimal("123.456789")
        param = Param.decimal128(d)
        assert param.value == d
        assert param.arrow_type == pa.decimal128(38, 9)

    def test_decimal128_custom(self) -> None:
        """Test decimal128 with custom precision/scale."""
        d = Decimal("123.45")
        param = Param.decimal128(d, precision=10, scale=2)
        assert param.arrow_type == pa.decimal128(10, 2)

    def test_decimal256_default(self) -> None:
        """Test decimal256 with default precision/scale."""
        d = Decimal("123456789012345678901234567890.12345678")
        param = Param.decimal256(d)
        assert param.value == d
        assert param.arrow_type == pa.decimal256(76, 38)

    def test_decimal256_custom(self) -> None:
        """Test decimal256 with custom precision/scale."""
        d = Decimal("123.456")
        param = Param.decimal256(d, precision=50, scale=20)
        assert param.arrow_type == pa.decimal256(50, 20)


class TestNullFactoryMethod:
    """Test Param null factory method."""

    def test_null(self) -> None:
        """Test null factory method."""
        param = Param.null()
        assert param.value is None
        assert param.arrow_type == pa.null()
        assert param.has_explicit_type()


class TestGenericFactoryMethod:
    """Test Param.of generic factory method."""

    def test_of_without_type(self) -> None:
        """Test of() without explicit type."""
        param = Param.of(42)
        assert param.value == 42
        assert param.arrow_type is None
        assert not param.has_explicit_type()

    def test_of_with_type(self) -> None:
        """Test of() with explicit type."""
        param = Param.of(42, pa.int32())
        assert param.value == 42
        assert param.arrow_type == pa.int32()
        assert param.has_explicit_type()

    def test_of_with_none_value(self) -> None:
        """Test of() with None value."""
        param = Param.of(None, pa.null())
        assert param.value is None
        assert param.arrow_type == pa.null()


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


class TestParamEdgeCases:
    """Test edge cases and special scenarios."""

    def test_param_with_nan(self) -> None:
        """Test Param with NaN value."""
        import math

        param = Param.float64(float("nan"))
        assert math.isnan(param.value)

    def test_param_repr(self) -> None:
        """Test Param string representation."""
        param = Param.int32(42)
        repr_str = repr(param)
        assert "42" in repr_str
        assert "int32" in repr_str

    def test_multiple_params_same_value(self) -> None:
        """Test creating multiple params with same value but different types."""
        p1 = Param.int32(100)
        p2 = Param.int64(100)
        p3 = Param.float64(100)

        assert p1.value == p2.value == p3.value
        assert p1.arrow_type != p2.arrow_type
        assert p2.arrow_type != p3.arrow_type
