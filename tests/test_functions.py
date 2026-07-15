"""Tests for the spicepy.functions module."""

from __future__ import annotations

import pytest

from spicepy import WindowFrame, col
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


class TestAnalyticsAggregates:
    def test_stddev_pop(self) -> None:
        assert F.stddev_pop(col("x")).to_sql() == 'STDDEV_POP("x")'

    def test_var_samp(self) -> None:
        assert F.var_samp(col("x")).to_sql() == 'VAR_SAMP("x")'

    def test_approx_percentile_cont(self) -> None:
        assert (
            F.approx_percentile_cont(col("x"), 0.95).to_sql()
            == 'APPROX_PERCENTILE_CONT("x", 0.95)'
        )

    def test_corr(self) -> None:
        assert F.corr(col("y"), col("x")).to_sql() == 'CORR("y", "x")'

    def test_string_agg(self) -> None:
        assert F.string_agg(col("c"), ", ").to_sql() == """STRING_AGG("c", ', ')"""

    def test_bool_and(self) -> None:
        assert F.bool_and(col("f")).to_sql() == 'BOOL_AND("f")'

    def test_bit_or(self) -> None:
        assert F.bit_or(col("m")).to_sql() == 'BIT_OR("m")'


class TestAggregateFilter:
    def test_filter(self) -> None:
        expr = F.sum(col("amt")).filter(col("status") == "paid")
        assert expr.to_sql() == """SUM("amt") FILTER (WHERE ("status" = 'paid'))"""

    def test_filter_preserves_distinct(self) -> None:
        expr = F.count_distinct(col("u")).filter(col("active"))
        assert expr.to_sql() == 'COUNT(DISTINCT "u") FILTER (WHERE "active")'


class TestConditional:
    def test_greatest(self) -> None:
        assert F.greatest(col("a"), col("b")).to_sql() == 'GREATEST("a", "b")'

    def test_least(self) -> None:
        assert F.least(col("a"), col("b"), 0).to_sql() == 'LEAST("a", "b", 0)'

    def test_greatest_requires_arg(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            F.greatest()

    def test_least_requires_arg(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            F.least()


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

    def test_interval(self) -> None:
        assert F.interval("1 day").to_sql() == "INTERVAL '1 day'"

    def test_date_bin(self) -> None:
        assert F.date_bin("1 hour", col("ts")).to_sql() == (
            """DATE_BIN(INTERVAL '1 hour', "ts")"""
        )

    def test_date_bin_with_origin(self) -> None:
        assert F.date_bin("1 day", col("ts"), col("origin")).to_sql() == (
            """DATE_BIN(INTERVAL '1 day', "ts", "origin")"""
        )


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

    def test_ntile(self) -> None:
        assert (
            F.ntile(4).over(order_by=[col("x")]).to_sql()
            == 'NTILE(4) OVER (ORDER BY "x")'
        )

    def test_over_with_frame(self) -> None:
        sql = (
            F.sum(col("v"))
            .over(
                order_by=[col("ts")],
                frame=WindowFrame("rows", None, 0),
            )
            .to_sql()
        )
        assert sql == (
            'SUM("v") OVER (ORDER BY "ts" '
            "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)"
        )

    def test_partition_order_and_frame(self) -> None:
        sql = (
            F.avg(col("v"))
            .over(
                partition_by=[col("sensor")],
                order_by=[col("ts")],
                frame=WindowFrame("rows", 6, 0),
            )
            .to_sql()
        )
        assert sql == (
            'AVG("v") OVER (PARTITION BY "sensor" ORDER BY "ts" '
            "ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)"
        )
