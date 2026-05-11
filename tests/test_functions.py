"""Tests for the spicepy.functions module."""

from __future__ import annotations

from spicepy import col
from spicepy import functions as F


class TestAggregates:
    def test_sum(self) -> None:
        assert F.sum(col("x")).to_sql() == 'SUM("x")'

    def test_avg(self) -> None:
        assert F.avg(col("x")).to_sql() == 'AVG("x")'

    def test_min_max(self) -> None:
        assert F.min(col("x")).to_sql() == 'MIN("x")'
        assert F.max(col("x")).to_sql() == 'MAX("x")'

    def test_count_no_arg(self) -> None:
        assert F.count().to_sql() == "COUNT(*)"

    def test_count_col(self) -> None:
        assert F.count(col("x")).to_sql() == 'COUNT("x")'

    def test_count_distinct(self) -> None:
        assert F.count_distinct(col("x")).to_sql() == 'COUNT(DISTINCT "x")'


class TestMath:
    def test_abs(self) -> None:
        assert F.abs(col("x")).to_sql() == 'ABS("x")'

    def test_round(self) -> None:
        assert F.round(col("x"), 2).to_sql() == 'ROUND("x", 2)'

    def test_power(self) -> None:
        assert F.power(col("x"), 3).to_sql() == 'POWER("x", 3)'


class TestStrings:
    def test_lower(self) -> None:
        assert F.lower(col("c")).to_sql() == 'LOWER("c")'

    def test_concat(self) -> None:
        assert F.concat(col("a"), col("b")).to_sql() == 'CONCAT("a", "b")'

    def test_substr_two_args(self) -> None:
        assert F.substr(col("c"), 1).to_sql() == 'SUBSTR("c", 1)'

    def test_substr_three_args(self) -> None:
        assert F.substr(col("c"), 1, 3).to_sql() == 'SUBSTR("c", 1, 3)'

    def test_length(self) -> None:
        assert F.length(col("c")).to_sql() == 'CHAR_LENGTH("c")'


class TestDateTime:
    def test_date_trunc(self) -> None:
        assert F.date_trunc("day", col("ts")).to_sql() == """DATE_TRUNC('day', "ts")"""

    def test_now(self) -> None:
        assert F.now().to_sql() == "NOW()"

    def test_current_date(self) -> None:
        assert F.current_date().to_sql() == "CURRENT_DATE()"


class TestNullHandling:
    def test_coalesce(self) -> None:
        assert F.coalesce(col("a"), col("b"), 0).to_sql() == 'COALESCE("a", "b", 0)'

    def test_nullif(self) -> None:
        assert F.nullif(col("a"), 0).to_sql() == 'NULLIF("a", 0)'


class TestWindowFunctions:
    def test_row_number(self) -> None:
        sql = F.row_number().over(partition_by=[col("city")]).to_sql()
        assert sql == 'ROW_NUMBER() OVER (PARTITION BY "city")'

    def test_rank_ordered(self) -> None:
        sql = F.rank().over(order_by=[col("ts").desc()]).to_sql()
        assert sql == 'RANK() OVER (ORDER BY "ts" DESC NULLS FIRST)'

    def test_lag(self) -> None:
        assert F.lag(col("x")).over().to_sql() == 'LAG("x", 1) OVER ()'

    def test_lag_with_default(self) -> None:
        assert F.lag(col("x"), 2, 0).over().to_sql() == 'LAG("x", 2, 0) OVER ()'
