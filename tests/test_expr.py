"""Tests for the Expr DSL."""

from __future__ import annotations

import pyarrow as pa
import pytest

from spicepy import case, col, lit
from spicepy._expr import _Raw


class TestColAndLit:
    def test_col(self) -> None:
        assert col("city").to_sql() == '"city"'

    def test_col_qualified(self) -> None:
        assert col("city", "l").to_sql() == '"l"."city"'

    def test_lit_int(self) -> None:
        assert lit(5).to_sql() == "5"

    def test_lit_str(self) -> None:
        assert lit("a").to_sql() == "'a'"

    def test_lit_none(self) -> None:
        assert lit(None).to_sql() == "NULL"


class TestOperators:
    def test_add(self) -> None:
        assert (col("x") + 1).to_sql() == '("x" + 1)'

    def test_radd(self) -> None:
        assert (1 + col("x")).to_sql() == '(1 + "x")'

    def test_sub(self) -> None:
        assert (col("x") - 2).to_sql() == '("x" - 2)'

    def test_mul(self) -> None:
        assert (col("x") * 3).to_sql() == '("x" * 3)'

    def test_div(self) -> None:
        assert (col("x") / 2).to_sql() == '("x" / 2)'

    def test_mod(self) -> None:
        assert (col("x") % 3).to_sql() == '("x" % 3)'

    def test_neg(self) -> None:
        assert (-col("x")).to_sql() == '(- "x")'

    def test_eq(self) -> None:
        assert (col("x") == 1).to_sql() == '("x" = 1)'

    def test_ne(self) -> None:
        assert (col("x") != 1).to_sql() == '("x" <> 1)'

    def test_lt(self) -> None:
        assert (col("x") < 5).to_sql() == '("x" < 5)'

    def test_le(self) -> None:
        assert (col("x") <= 5).to_sql() == '("x" <= 5)'

    def test_gt(self) -> None:
        assert (col("x") > 5).to_sql() == '("x" > 5)'

    def test_ge(self) -> None:
        assert (col("x") >= 5).to_sql() == '("x" >= 5)'

    def test_and(self) -> None:
        assert (
            (col("x") > 0) & (col("y") < 10)
        ).to_sql() == '(("x" > 0) AND ("y" < 10))'

    def test_or(self) -> None:
        assert (
            (col("x") > 0) | (col("y") < 10)
        ).to_sql() == '(("x" > 0) OR ("y" < 10))'

    def test_invert(self) -> None:
        assert (~col("flag")).to_sql() == '(NOT "flag")'


class TestPredicates:
    def test_is_null(self) -> None:
        assert col("x").is_null().to_sql() == '("x" IS NULL)'

    def test_is_not_null(self) -> None:
        assert col("x").is_not_null().to_sql() == '("x" IS NOT NULL)'

    def test_in(self) -> None:
        assert col("x").in_([1, 2, 3]).to_sql() == '("x" IN (1, 2, 3))'

    def test_in_strings(self) -> None:
        assert col("c").in_(["a", "b"]).to_sql() == """("c" IN ('a', 'b'))"""

    def test_in_empty(self) -> None:
        assert col("x").in_([]).to_sql() == "FALSE"

    def test_between(self) -> None:
        assert col("x").between(1, 10).to_sql() == '("x" BETWEEN 1 AND 10)'


class TestAliasAndCast:
    def test_alias(self) -> None:
        assert col("x").alias("y").to_sql() == '"x" AS "y"'

    def test_cast_string(self) -> None:
        assert col("x").cast("BIGINT").to_sql() == 'CAST("x" AS BIGINT)'

    def test_cast_arrow_type(self) -> None:
        assert col("x").cast(pa.int32()).to_sql() == 'CAST("x" AS INT)'

    def test_cast_arrow_string(self) -> None:
        assert col("x").cast(pa.string()).to_sql() == 'CAST("x" AS VARCHAR)'

    def test_cast_arrow_float(self) -> None:
        assert col("x").cast(pa.float64()).to_sql() == 'CAST("x" AS DOUBLE)'

    def test_cast_bad_type(self) -> None:
        with pytest.raises(TypeError):
            col("x").cast(object())


class TestSortQualifier:
    def test_asc(self) -> None:
        assert col("x").asc().to_sql() == '"x" ASC NULLS LAST'

    def test_desc(self) -> None:
        assert col("x").desc().to_sql() == '"x" DESC NULLS FIRST'

    def test_asc_nulls_first(self) -> None:
        assert col("x").asc(nulls_first=True).to_sql() == '"x" ASC NULLS FIRST'


class TestCase:
    def test_basic(self) -> None:
        e = case().when(col("x") > 0, "pos").otherwise("neg")
        assert e.to_sql() == """(CASE WHEN ("x" > 0) THEN 'pos' ELSE 'neg' END)"""

    def test_multiple_branches(self) -> None:
        e = case().when(col("x") > 0, "pos").when(col("x") < 0, "neg").otherwise("zero")
        assert "WHEN" in e.to_sql() and e.to_sql().count("WHEN") == 2

    def test_no_branches_raises(self) -> None:
        with pytest.raises(ValueError, match="no WHEN"):
            case().to_sql()


class TestRaw:
    def test_raw_passthrough(self) -> None:
        assert _Raw("FOO()").to_sql() == "FOO()"
