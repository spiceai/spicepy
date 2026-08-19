"""Tests for SpiceDataFrame SQL composition.

These tests use a mock Client; they verify that DataFrame operations
produce the expected SQL but don't actually run any query.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
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


def mock_schema(client: MagicMock, *names: str) -> None:
    """Serve *names as the schema of the mocked zero-row probe query."""
    client.query.return_value.read_all.return_value.schema = pa.schema(
        [pa.field(n, pa.int64()) for n in names]
    )


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

    def test_drop(self, df: SpiceDataFrame, client: MagicMock) -> None:
        mock_schema(client, "a", "b", "c")
        assert df.drop("a", "b").to_sql() == ('SELECT "c" FROM (SELECT * FROM "trips")')

    def test_drop_every_column_raises(
        self, df: SpiceDataFrame, client: MagicMock
    ) -> None:
        mock_schema(client, "a")
        with pytest.raises(ValueError, match="every column"):
            df.drop("a")

    def test_drop_empty_noop(self, df: SpiceDataFrame) -> None:
        assert df.drop().to_sql() == df.to_sql()

    def test_rename(self, df: SpiceDataFrame, client: MagicMock) -> None:
        mock_schema(client, "old", "other")
        assert df.rename({"old": "new"}).to_sql() == (
            'SELECT "old" AS "new", "other" FROM (SELECT * FROM "trips")'
        )

    def test_cast(self, df: SpiceDataFrame, client: MagicMock) -> None:
        mock_schema(client, "x", "y")
        assert df.cast({"x": pa.int32()}).to_sql() == (
            'SELECT CAST("x" AS INT) AS "x", "y" FROM (SELECT * FROM "trips")'
        )


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

    def test_limit_after_sort_shares_the_order_by_level(
        self, df: SpiceDataFrame
    ) -> None:
        """A wrapped subquery's ORDER BY is not guaranteed to survive planning."""
        assert df.sort(col("fare")).limit(5).to_sql() == (
            'SELECT * FROM (SELECT * FROM "trips") ORDER BY "fare" LIMIT 5'
        )

    def test_limit_after_limit_wraps(self, df: SpiceDataFrame) -> None:
        sql = df.sort(col("fare")).limit(5).limit(3).to_sql()
        assert sql.endswith('ORDER BY "fare" LIMIT 5) LIMIT 3')

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


class TestColumnSelection:
    def test_getitem_single(self, df: SpiceDataFrame) -> None:
        assert df["city"].to_sql() == 'SELECT "city" FROM (SELECT * FROM "trips")'

    def test_getitem_list(self, df: SpiceDataFrame) -> None:
        assert df[["city", "fare"]].to_sql() == (
            'SELECT "city", "fare" FROM (SELECT * FROM "trips")'
        )

    def test_getitem_empty_list_raises(self, df: SpiceDataFrame) -> None:
        with pytest.raises(KeyError, match="at least one column"):
            _ = df[[]]

    def test_getitem_bad_key_raises(self, df: SpiceDataFrame) -> None:
        with pytest.raises(TypeError, match="column name or list"):
            _ = df[5]

    def test_getitem_non_str_element_raises(self, df: SpiceDataFrame) -> None:
        with pytest.raises(TypeError, match="must be strings"):
            _ = df[["a", 1]]


class TestSetOpAll:
    def test_intersect_all(self, df: SpiceDataFrame, client: MagicMock) -> None:
        other = SpiceDataFrame(client, 'SELECT * FROM "t2"')
        assert "INTERSECT ALL" in df.intersect(other, all=True).to_sql()

    def test_except_all(self, df: SpiceDataFrame, client: MagicMock) -> None:
        other = SpiceDataFrame(client, 'SELECT * FROM "t2"')
        assert "EXCEPT ALL" in df.except_(other, all=True).to_sql()


class TestReprHtml:
    def test_repr_html(self, df: SpiceDataFrame, client: MagicMock) -> None:
        client.query_pandas.return_value = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        html = df._repr_html_()
        assert "<table" in html
        assert "SpiceDataFrame preview" in html
        # the preview came from a LIMIT query
        assert "LIMIT" in client.query_pandas.call_args[0][0]


class TestArrowCStream:
    def test_arrow_c_stream_roundtrips(
        self, df: SpiceDataFrame, client: MagicMock
    ) -> None:
        table = pa.table({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        client.query_arrow.return_value = table
        result = pa.RecordBatchReader.from_stream(df).read_all()
        assert result.equals(table)


class TestUnnest:
    def test_unnest_single(self, df: SpiceDataFrame, client: MagicMock) -> None:
        mock_schema(client, "tags", "city")
        assert df.unnest("tags").to_sql() == (
            'SELECT unnest("tags") AS "tags", "city" FROM (SELECT * FROM "trips")'
        )

    def test_unnest_multiple(self, df: SpiceDataFrame, client: MagicMock) -> None:
        mock_schema(client, "a", "b", "c")
        sql = df.unnest("a", "b").to_sql()
        assert 'unnest("a") AS "a", unnest("b") AS "b", "c"' in sql

    def test_unnest_empty_raises(self, df: SpiceDataFrame) -> None:
        with pytest.raises(ValueError, match="at least one column"):
            df.unnest()


class TestJoinAdvanced:
    @pytest.fixture
    def other(self, client: MagicMock) -> SpiceDataFrame:
        return SpiceDataFrame(client, 'SELECT * FROM "users"')

    def test_left_on_right_on(self, df: SpiceDataFrame, other: SpiceDataFrame) -> None:
        sql = df.join(other, left_on="user_id", right_on="id").to_sql()
        assert '"l"."user_id" = "r"."id"' in sql
        assert "INNER JOIN" in sql

    def test_left_on_right_on_multi(
        self, df: SpiceDataFrame, other: SpiceDataFrame
    ) -> None:
        sql = df.join(other, left_on=["a", "b"], right_on=["x", "y"]).to_sql()
        assert '"l"."a" = "r"."x" AND "l"."b" = "r"."y"' in sql

    def test_on_and_left_on_conflict(
        self, df: SpiceDataFrame, other: SpiceDataFrame
    ) -> None:
        with pytest.raises(ValueError, match="not both"):
            df.join(other, on="id", left_on="a", right_on="b")

    def test_left_on_without_right_on(
        self, df: SpiceDataFrame, other: SpiceDataFrame
    ) -> None:
        with pytest.raises(ValueError, match="provided together"):
            df.join(other, left_on="a")

    def test_join_missing_on_raises(
        self, df: SpiceDataFrame, other: SpiceDataFrame
    ) -> None:
        with pytest.raises(ValueError, match="join requires"):
            df.join(other)

    def test_join_on_predicate(self, df: SpiceDataFrame, other: SpiceDataFrame) -> None:
        sql = df.join_on(
            other, col("user_id", "l") == col("id", "r"), how="left"
        ).to_sql()
        assert 'ON ("l"."user_id" = "r"."id")' in sql
        assert "LEFT JOIN" in sql

    def test_join_on_multiple_predicates(
        self, df: SpiceDataFrame, other: SpiceDataFrame
    ) -> None:
        sql = df.join_on(
            other,
            col("a", "l") == col("a", "r"),
            col("b", "l") > col("b", "r"),
        ).to_sql()
        assert " AND " in sql

    def test_join_on_requires_predicate(
        self, df: SpiceDataFrame, other: SpiceDataFrame
    ) -> None:
        with pytest.raises(ValueError, match="at least one predicate"):
            df.join_on(other)

    def test_join_on_rejects_cross(
        self, df: SpiceDataFrame, other: SpiceDataFrame
    ) -> None:
        with pytest.raises(ValueError, match="does not support"):
            df.join_on(other, col("a", "l") == col("a", "r"), how="cross")


class TestDescribe:
    @staticmethod
    def _mock_schema(client: MagicMock, schema: pa.Schema) -> None:
        reader = MagicMock()
        reader.read_all.return_value.schema = schema
        client.query.return_value = reader

    def test_describe_numeric(self, df: SpiceDataFrame, client: MagicMock) -> None:
        self._mock_schema(
            client,
            pa.schema([("a", pa.int64()), ("b", pa.float64()), ("name", pa.string())]),
        )
        sql = df.describe().to_sql()
        assert "UNION ALL" in sql
        assert "'count'" in sql and "'mean'" in sql and "'stddev'" in sql
        assert 'AVG(CAST("a" AS DOUBLE))' in sql
        assert 'AS "statistic"' in sql
        # non-numeric column is excluded from the summary
        assert '"name"' not in sql

    def test_describe_no_numeric_raises(
        self, df: SpiceDataFrame, client: MagicMock
    ) -> None:
        self._mock_schema(client, pa.schema([("name", pa.string())]))
        with pytest.raises(ValueError, match="no numeric columns"):
            df.describe()


class TestWriters:
    def test_write_parquet_delegates(
        self, df: SpiceDataFrame, client: MagicMock
    ) -> None:
        df.write_parquet("out.parquet")
        client.write_parquet.assert_called_once_with(
            'SELECT * FROM "trips"', "out.parquet"
        )

    def test_write_parquet_passes_kwargs(
        self, df: SpiceDataFrame, client: MagicMock
    ) -> None:
        df.write_parquet("out.parquet", compression="snappy")
        client.write_parquet.assert_called_once_with(
            'SELECT * FROM "trips"', "out.parquet", compression="snappy"
        )

    def test_write_csv_delegates(self, df: SpiceDataFrame, client: MagicMock) -> None:
        df.write_csv("out.csv")
        client.write_csv.assert_called_once_with('SELECT * FROM "trips"', "out.csv")

    def test_write_json_delegates(self, df: SpiceDataFrame, client: MagicMock) -> None:
        df.write_json("out.json")
        client.write_json.assert_called_once_with('SELECT * FROM "trips"', "out.json")


class TestRepr:
    def test_repr(self, df: SpiceDataFrame) -> None:
        assert "SELECT" in repr(df)
