"""Tests for SpiceDataFrame SQL composition.

These tests use a mock Client; they verify that DataFrame operations
produce the expected SQL but don't actually run any query.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pyarrow as pa
import pytest

from spicepy import SpiceDataFrame, col, lit
from spicepy import functions as F
from spicepy._dataframe import values_dataframe


@pytest.fixture
def client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def df(client: MagicMock) -> SpiceDataFrame:
    return SpiceDataFrame(client, 'SELECT * FROM "trips"')


class TestProjection:
    def test_select(self, df: SpiceDataFrame) -> None:
        assert df.select(col("city")).to_sql() == (
            'SELECT "city" FROM (SELECT * FROM "trips")'
        )

    def test_select_by_string(self, df: SpiceDataFrame) -> None:
        assert df.select("city", "fare").to_sql() == (
            'SELECT "city", "fare" FROM (SELECT * FROM "trips")'
        )

    def test_select_requires_args(self, df: SpiceDataFrame) -> None:
        with pytest.raises(ValueError, match="at least one"):
            df.select()

    def test_with_column(self, df: SpiceDataFrame) -> None:
        assert df.with_column("y", col("x") * 2).to_sql() == (
            'SELECT *, ("x" * 2) AS "y" FROM (SELECT * FROM "trips")'
        )

    def test_with_columns(self, df: SpiceDataFrame) -> None:
        sql = df.with_columns(a=col("x") + 1, b=lit(5)).to_sql()
        assert 'AS "a"' in sql and 'AS "b"' in sql

    def test_with_columns_empty_noop(self, df: SpiceDataFrame) -> None:
        assert df.with_columns().to_sql() == df.to_sql()

    def test_drop(self, df: SpiceDataFrame) -> None:
        assert df.drop("a", "b").to_sql() == (
            'SELECT * EXCLUDE ("a", "b") FROM (SELECT * FROM "trips")'
        )

    def test_drop_empty_noop(self, df: SpiceDataFrame) -> None:
        assert df.drop().to_sql() == df.to_sql()

    def test_rename(self, df: SpiceDataFrame) -> None:
        assert df.rename({"old": "new"}).to_sql() == (
            'SELECT * REPLACE ("old" AS "new") FROM (SELECT * FROM "trips")'
        )

    def test_cast(self, df: SpiceDataFrame) -> None:
        sql = df.cast({"x": pa.int32()}).to_sql()
        assert 'CAST("x" AS INT) AS "x"' in sql


class TestFilter:
    def test_filter(self, df: SpiceDataFrame) -> None:
        assert df.filter(col("fare") > 10).to_sql() == (
            'SELECT * FROM (SELECT * FROM "trips") WHERE ("fare" > 10)'
        )

    def test_where_is_alias(self, df: SpiceDataFrame) -> None:
        assert (
            df.where(col("fare") > 10).to_sql() == df.filter(col("fare") > 10).to_sql()
        )


class TestSlice:
    def test_limit(self, df: SpiceDataFrame) -> None:
        assert df.limit(5).to_sql() == 'SELECT * FROM (SELECT * FROM "trips") LIMIT 5'

    def test_limit_with_offset(self, df: SpiceDataFrame) -> None:
        assert df.limit(5, offset=10).to_sql() == (
            'SELECT * FROM (SELECT * FROM "trips") LIMIT 5 OFFSET 10'
        )

    def test_limit_negative_raises(self, df: SpiceDataFrame) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            df.limit(-1)

    def test_limit_negative_offset_raises(self, df: SpiceDataFrame) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            df.limit(5, offset=-1)

    def test_head(self, df: SpiceDataFrame) -> None:
        assert df.head(3).to_sql() == df.limit(3).to_sql()

    def test_tail_raises(self, df: SpiceDataFrame) -> None:
        with pytest.raises(NotImplementedError):
            df.tail(3)


class TestSortDistinct:
    def test_sort(self, df: SpiceDataFrame) -> None:
        sql = df.sort(col("fare").desc(), "city").to_sql()
        assert 'ORDER BY "fare" DESC NULLS FIRST, "city"' in sql

    def test_sort_requires_args(self, df: SpiceDataFrame) -> None:
        with pytest.raises(ValueError, match="at least one"):
            df.sort()

    def test_order_by_alias(self, df: SpiceDataFrame) -> None:
        assert df.order_by("city").to_sql() == df.sort("city").to_sql()

    def test_distinct(self, df: SpiceDataFrame) -> None:
        assert df.distinct().to_sql() == (
            'SELECT DISTINCT * FROM (SELECT * FROM "trips")'
        )


class TestSetOps:
    def test_union(self, df: SpiceDataFrame, client: MagicMock) -> None:
        other = SpiceDataFrame(client, 'SELECT * FROM "t2"')
        assert df.union(other).to_sql() == (
            'SELECT * FROM "trips" UNION SELECT * FROM "t2"'
        )

    def test_union_all(self, df: SpiceDataFrame, client: MagicMock) -> None:
        other = SpiceDataFrame(client, 'SELECT * FROM "t2"')
        assert df.union(other, all=True).to_sql() == (
            'SELECT * FROM "trips" UNION ALL SELECT * FROM "t2"'
        )

    def test_intersect(self, df: SpiceDataFrame, client: MagicMock) -> None:
        other = SpiceDataFrame(client, 'SELECT * FROM "t2"')
        assert "INTERSECT" in df.intersect(other).to_sql()

    def test_except(self, df: SpiceDataFrame, client: MagicMock) -> None:
        other = SpiceDataFrame(client, 'SELECT * FROM "t2"')
        assert "EXCEPT" in df.except_(other).to_sql()


class TestJoin:
    def test_join_string_key(self, df: SpiceDataFrame, client: MagicMock) -> None:
        other = SpiceDataFrame(client, 'SELECT * FROM "drivers"')
        sql = df.join(other, on="driver_id", how="left").to_sql()
        assert "LEFT JOIN" in sql
        assert '"l"."driver_id" = "r"."driver_id"' in sql

    def test_join_multi_key(self, df: SpiceDataFrame, client: MagicMock) -> None:
        other = SpiceDataFrame(client, 'SELECT * FROM "t2"')
        sql = df.join(other, on=["a", "b"], how="inner").to_sql()
        assert '"l"."a" = "r"."a"' in sql and '"l"."b" = "r"."b"' in sql
        assert "AND" in sql

    def test_join_expr(self, df: SpiceDataFrame, client: MagicMock) -> None:
        other = SpiceDataFrame(client, 'SELECT * FROM "drivers"')
        sql = df.join(
            other,
            on=(col("id", "l") == col("driver_id", "r")),
            how="inner",
        ).to_sql()
        assert "INNER JOIN" in sql
        assert '("l"."id" = "r"."driver_id")' in sql

    def test_join_bad_kind(self, df: SpiceDataFrame, client: MagicMock) -> None:
        other = SpiceDataFrame(client, 'SELECT * FROM "t2"')
        with pytest.raises(ValueError, match="Unknown join kind"):
            df.join(other, on="x", how="bogus")

    def test_cross_join(self, df: SpiceDataFrame, client: MagicMock) -> None:
        other = SpiceDataFrame(client, 'SELECT * FROM "t2"')
        sql = df.cross_join(other).to_sql()
        assert "CROSS JOIN" in sql


class TestAggregate:
    def test_group_by_aggregate(self, df: SpiceDataFrame) -> None:
        sql = (
            df.group_by(col("city"))
            .aggregate(F.sum(col("fare")).alias("total"))
            .to_sql()
        )
        assert "GROUP BY" in sql
        assert 'SUM("fare") AS "total"' in sql

    def test_global_aggregate(self, df: SpiceDataFrame) -> None:
        sql = df.aggregate(F.count().alias("n")).to_sql()
        assert "COUNT(*)" in sql
        assert "GROUP BY" not in sql


class TestMaterialization:
    def test_collect_calls_query_arrow(
        self, df: SpiceDataFrame, client: MagicMock
    ) -> None:
        client.query_arrow.return_value = pa.table({"a": [1]})
        result = df.collect()
        client.query_arrow.assert_called_once_with(df.to_sql())
        assert isinstance(result, pa.Table)

    def test_to_pandas_delegates(self, df: SpiceDataFrame, client: MagicMock) -> None:
        df.to_pandas()
        client.query_pandas.assert_called_once_with(df.to_sql())

    def test_to_polars_delegates(self, df: SpiceDataFrame, client: MagicMock) -> None:
        df.to_polars()
        client.query_polars.assert_called_once_with(df.to_sql())

    def test_to_pylist_delegates(self, df: SpiceDataFrame, client: MagicMock) -> None:
        df.to_pylist()
        client.query_pylist.assert_called_once_with(df.to_sql())

    def test_to_pydict_delegates(self, df: SpiceDataFrame, client: MagicMock) -> None:
        df.to_pydict()
        client.query_pydict.assert_called_once_with(df.to_sql())

    def test_count(self, df: SpiceDataFrame, client: MagicMock) -> None:
        client.query_arrow.return_value = pa.table({"c": [42]})
        n = df.count()
        assert n == 42

    def test_schema(self, df: SpiceDataFrame, client: MagicMock) -> None:
        sample = pa.table({"a": [1]}, schema=pa.schema([("a", pa.int64())]))
        reader = MagicMock()
        reader.read_all.return_value = sample
        client.query.return_value = reader
        result = df.schema()
        assert result == sample.schema


class TestValuesDataFrame:
    def test_basic(self, client: MagicMock) -> None:
        df = values_dataframe(client, [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}])
        sql = df.to_sql()
        assert "VALUES" in sql
        assert "(1, 'x')" in sql and "(2, 'y')" in sql
        assert 't("a", "b")' in sql

    def test_empty_raises(self, client: MagicMock) -> None:
        with pytest.raises(ValueError, match="at least one row"):
            values_dataframe(client, [])

    def test_mismatched_columns_raises(self, client: MagicMock) -> None:
        with pytest.raises(ValueError, match="same columns"):
            values_dataframe(client, [{"a": 1}, {"b": 2}])


class TestRepr:
    def test_repr(self, df: SpiceDataFrame) -> None:
        assert "SELECT" in repr(df)
