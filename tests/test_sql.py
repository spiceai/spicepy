"""Tests for SQL identifier and literal escape helpers."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

import pytest

from spicepy._sql import quote_ident, quote_literal, quote_qualified


class TestQuoteIdent:
    def test_simple(self) -> None:
        assert quote_ident("col") == '"col"'

    def test_with_double_quote(self) -> None:
        assert quote_ident('co"l') == '"co""l"'

    def test_empty(self) -> None:
        assert quote_ident("") == '""'

    def test_unicode(self) -> None:
        assert quote_ident("纽约") == '"纽约"'


class TestQuoteQualified:
    def test_schema_table(self) -> None:
        assert quote_qualified("public", "trips") == '"public"."trips"'

    def test_drops_empty(self) -> None:
        assert quote_qualified("", "trips") == '"trips"'


class TestQuoteLiteral:
    def test_none(self) -> None:
        assert quote_literal(None) == "NULL"

    def test_bool(self) -> None:
        assert quote_literal(True) == "TRUE"
        assert quote_literal(False) == "FALSE"

    def test_int(self) -> None:
        assert quote_literal(42) == "42"
        assert quote_literal(-1) == "-1"

    def test_float(self) -> None:
        assert quote_literal(3.14) == "3.14"

    def test_decimal(self) -> None:
        assert quote_literal(Decimal("1.23")) == "1.23"

    def test_string(self) -> None:
        assert quote_literal("hello") == "'hello'"

    def test_string_with_single_quote(self) -> None:
        assert quote_literal("O'Hara") == "'O''Hara'"

    def test_bytes(self) -> None:
        assert quote_literal(b"\x00\xff") == "X'00ff'"

    def test_date(self) -> None:
        assert quote_literal(date(2024, 5, 1)) == "CAST('2024-05-01' AS DATE)"

    def test_datetime(self) -> None:
        result = quote_literal(datetime(2024, 5, 1, 12, 30, 0))
        assert result == "CAST('2024-05-01 12:30:00' AS TIMESTAMP)"

    def test_time(self) -> None:
        assert quote_literal(time(9, 15, 30)) == "CAST('09:15:30' AS TIME)"

    def test_unsupported_raises(self) -> None:
        with pytest.raises(TypeError, match="Cannot render"):
            quote_literal({"a": 1})
