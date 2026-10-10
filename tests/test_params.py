"""Unit tests for spicepy.params module."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

from spicepy.params import infer_arrow_type, param_array


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


class TestNumpyAndPandasScalars:
    """Values read out of a DataFrame or numpy array bind like the Python ones."""

    def test_dataframe_cells_bind_as_parameters(self) -> None:
        """Every cell type pandas hands back from ``iloc`` builds a parameter."""
        frame = pd.DataFrame(
            {
                "id": [7],
                "small": np.array([3], dtype=np.int32),
                "flag": [True],
                "fare": [12.5],
                "name": ["x"],
                "picked_up": pd.to_datetime(["2024-01-31 05:00:00.000000001"]),
                "trip": pd.to_timedelta(["30min"]),
            }
        )
        row = frame.iloc[0]

        arrays = [param_array(row[column]) for column in frame.columns]

        assert [a.type for a in arrays] == [
            pa.int64(),
            pa.int32(),
            pa.bool_(),
            pa.float64(),
            pa.string(),
            pa.timestamp("ns"),
            pa.duration(row["trip"].unit),
        ]
        assert arrays[0].to_pylist() == [7]
        assert arrays[2].to_pylist() == [True]
        assert arrays[5].cast(pa.int64()).to_pylist() == [1_706_677_200_000_000_001]
        assert arrays[6].to_pylist() == [timedelta(minutes=30)]

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (np.int64(5), pa.int64()),
            (np.uint8(5), pa.uint8()),
            (np.float32(1.5), pa.float32()),
            (np.bool_(False), pa.bool_()),
        ],
    )
    def test_numpy_numbers_keep_their_width(
        self, value: Any, expected: pa.DataType
    ) -> None:
        """A numpy number binds as its own Arrow type, not a widened one."""
        assert infer_arrow_type(value) == expected
        assert param_array(value).to_pylist() == [value.item()]

    def test_datetime64_day_binds_as_a_date(self) -> None:
        """``datetime64[D]``, which Arrow cannot build from directly, is a date."""
        array = param_array(np.datetime64("2024-01-31"))
        assert array.type == pa.date32()
        assert array.to_pylist() == [date(2024, 1, 31)]

    def test_datetime64_minutes_bind_in_the_nearest_supported_unit(self) -> None:
        """Arrow has no minute unit; the instant survives as seconds."""
        array = param_array(np.datetime64("2024-01-31T05:00", "m"))
        assert array.type == pa.timestamp("s")
        assert array.to_pylist() == [datetime(2024, 1, 31, 5, 0)]

    def test_timedelta64_minutes_bind_as_a_duration(self) -> None:
        """``timedelta64[m]``, which Arrow rejects directly, is a duration."""
        array = param_array(np.timedelta64(30, "m"))
        assert array.type == pa.duration("s")
        assert array.to_pylist() == [timedelta(minutes=30)]

    def test_pandas_timestamp_keeps_nanoseconds_and_converts_to_utc(self) -> None:
        """A tz-aware ``pd.Timestamp`` binds as its UTC instant, to the nanosecond."""
        stamp = pd.Timestamp("2024-01-31 00:00:00.000000001", tz="America/New_York")
        array = param_array(stamp)
        assert array.type == pa.timestamp("ns")
        assert array.cast(pa.int64()).to_pylist() == [1_706_677_200_000_000_001]

    @pytest.mark.parametrize(
        "value", [pd.NaT, np.datetime64("NaT"), np.timedelta64("NaT")]
    )
    def test_not_a_time_binds_as_null(self, value: Any) -> None:
        """NaT is a missing value, so it binds as a typed null."""
        array = param_array(value)
        assert array.null_count == 1

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (np.datetime64("NaT", "D"), pa.date32()),
            (np.datetime64("NaT", "M"), pa.date32()),
            (np.datetime64("NaT", "m"), pa.timestamp("s")),
            (np.datetime64("NaT", "ms"), pa.timestamp("ms")),
            (np.datetime64("NaT", "ps"), pa.timestamp("ns")),
            (np.timedelta64("NaT", "W"), pa.duration("s")),
            (np.timedelta64("NaT", "D"), pa.duration("s")),
            (np.timedelta64("NaT", "h"), pa.duration("s")),
            (np.timedelta64("NaT", "m"), pa.duration("s")),
            (np.timedelta64("NaT", "s"), pa.duration("s")),
            (np.timedelta64("NaT", "ms"), pa.duration("ms")),
            (np.timedelta64("NaT", "ns"), pa.duration("ns")),
            (np.timedelta64("NaT", "us"), pa.duration("us")),
        ],
    )
    def test_not_a_time_binds_as_the_type_of_its_unit(
        self, value: Any, expected: pa.DataType
    ) -> None:
        """A NaT binds with the type a non-null value of its dtype would get."""
        unit, _ = np.datetime_data(value.dtype)
        assert infer_arrow_type(value) == expected
        assert infer_arrow_type(value.dtype.type(1, unit)) == expected
        array = param_array(value)
        assert array.type == expected
        assert array.null_count == 1

    def test_timedelta64_finer_than_nanoseconds_binds_as_nanoseconds(self) -> None:
        """Arrow's finest unit is nanoseconds; a picosecond duration truncates to it."""
        array = param_array(np.timedelta64(1500, "ps"))
        assert array.type == pa.duration("ns")
        assert array.cast(pa.int64()).to_pylist() == [1]

    @pytest.mark.parametrize(
        ("unit", "scale"), [("ps", 10**3), ("fs", 10**6), ("as", 10**9)]
    )
    def test_negative_sub_nanosecond_timedelta64_keeps_its_sign(
        self, unit: str, scale: int
    ) -> None:
        """Near the int64 minimum a sub-nanosecond duration floors, never wraps."""
        ticks = -(2**63) + 1
        array = param_array(np.timedelta64(ticks, unit))
        assert array.cast(pa.int64()).to_pylist() == [ticks // scale]
        assert param_array(np.timedelta64(-1500, "ps")).cast(
            pa.int64()
        ).to_pylist() == [-2]

    @pytest.mark.parametrize(
        ("dtype", "expected"),
        [
            ("timedelta64[2s]", timedelta(seconds=10)),
            ("timedelta64[3ms]", timedelta(milliseconds=15)),
            ("datetime64[10s]", datetime(1970, 1, 1, 0, 0, 50)),
            ("datetime64[2h]", datetime(1970, 1, 1, 10, 0)),
            ("datetime64[2D]", date(1970, 1, 11)),
        ],
    )
    def test_a_unit_multiplier_scales_the_bound_value(
        self, dtype: str, expected: Any
    ) -> None:
        """``timedelta64[2s]`` counts two-second steps; five of them bind as 10s."""
        value = np.array([5], dtype=dtype)[0]
        assert param_array(value).to_pylist() == [expected]

    def test_a_unit_multiplier_that_overflows_raises(self) -> None:
        """A value that cannot be rescaled to its base unit is refused, not wrapped."""
        value = np.array([2**62], dtype="timedelta64[4s]")[0]
        with pytest.raises(TypeError, match="does not fit in timedelta64"):
            param_array(value)

    @pytest.mark.parametrize(
        ("dtype", "ticks", "expected_ns"),
        [
            ("timedelta64[4ps]", 2**62, 2**64 // 1000),
            ("timedelta64[2fs]", 2**63 - 1, (2**64 - 2) // 10**6),
            ("timedelta64[3as]", -(2**63) + 1, (-(2**63) + 1) * 3 // 10**9),
        ],
    )
    def test_a_multiplied_sub_nanosecond_unit_reduces_before_the_overflow_check(
        self, dtype: str, ticks: int, expected_ns: int
    ) -> None:
        """Only the nanosecond result has to fit in 64 bits, not the tick product."""
        array = param_array(np.array([ticks], dtype=dtype)[0])
        assert array.type == pa.duration("ns")
        assert array.cast(pa.int64()).to_pylist() == [expected_ns]

    @pytest.mark.parametrize(
        "value",
        [
            np.timedelta64(1, "M"),
            np.timedelta64(1, "Y"),
            np.timedelta64("NaT", "M"),
            np.array([2], dtype="timedelta64[3M]")[0],
        ],
    )
    def test_a_calendar_timedelta64_is_refused(self, value: Any) -> None:
        """A month or year has no fixed length, so it has no duration to bind."""
        with pytest.raises(TypeError, match="calendar duration"):
            param_array(value)

    def test_unsupported_numpy_scalar_still_raises(self) -> None:
        """A numpy type with no SQL counterpart is still a clear TypeError."""
        with pytest.raises(TypeError, match="Unsupported parameter type: complex"):
            param_array(np.complex128(1 + 2j))
