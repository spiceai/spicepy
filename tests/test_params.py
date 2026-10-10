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

    def test_unsupported_numpy_scalar_still_raises(self) -> None:
        """A numpy type with no SQL counterpart is still a clear TypeError."""
        with pytest.raises(TypeError, match="Unsupported parameter type: complex"):
            param_array(np.complex128(1 + 2j))
