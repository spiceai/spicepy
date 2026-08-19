"""Live-runtime integration tests for the model-free client surface.

Everything in this module executes against a real local Spice runtime serving
the ``taxi_trips`` dataset — the same fixture ``test.yml`` boots for
``tests/test_main.py``. The unit suites assert the SQL these APIs *generate*;
this module asserts the runtime actually *accepts and executes* it.

Deliberately out of scope: ``search`` and ``nsql`` (both need a loaded
embedding/LLM model) and mTLS (needs an enterprise runtime with certificates).
"""

from __future__ import annotations

import json
import threading
import time

import pyarrow as pa
import pytest

from spicepy import Client, col, lit
from spicepy import functions as F
from spicepy.config import DEFAULT_LOCAL_FLIGHT_URL, DEFAULT_LOCAL_HTTP_URL

try:
    import polars as pl  # noqa: F401

    POLARS_AVAILABLE = True
except ImportError:
    POLARS_AVAILABLE = False

try:
    import adbc_driver_flightsql  # noqa: F401
    import adbc_driver_manager  # noqa: F401

    ADBC_AVAILABLE = True
except ImportError:
    ADBC_AVAILABLE = False

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", name="client")
def client_fixture() -> Client:
    """One shared client; fails the module fast when no runtime is up."""
    c = Client(flight_url=DEFAULT_LOCAL_FLIGHT_URL, http_url=DEFAULT_LOCAL_HTTP_URL)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if c.is_ready():
                return c
        except Exception:  # noqa: S110 - not up yet
            pass
        time.sleep(1)
    pytest.fail("Spice runtime did not become ready in time")


# ============== Runtime status ==============


def test_is_ready(client: Client) -> None:
    assert client.is_ready() is True


def test_runtime_status_reports_core_components(client: Client) -> None:
    components = {c.name: c for c in client.runtime_status()}
    assert components["http"].is_ready
    assert components["flight"].is_ready
    assert components["flight"].endpoint.endswith(":50051")


# ============== Typed query helpers ==============


def test_query_arrow(client: Client) -> None:
    table = client.query_arrow("SELECT trip_distance FROM taxi_trips LIMIT 10")
    assert isinstance(table, pa.Table)
    assert table.num_rows == 10
    assert table.column_names == ["trip_distance"]


def test_query_pandas(client: Client) -> None:
    df = client.query_pandas(
        "SELECT trip_distance, total_amount FROM taxi_trips LIMIT 5"
    )
    assert list(df.columns) == ["trip_distance", "total_amount"]
    assert len(df) == 5


@pytest.mark.skipif(not POLARS_AVAILABLE, reason="polars not installed")
def test_query_polars(client: Client) -> None:
    df = client.query_polars("SELECT payment_type FROM taxi_trips LIMIT 5")
    assert df.height == 5


def test_query_pylist_and_pydict(client: Client) -> None:
    rows = client.query_pylist("SELECT 1 AS a, 'x' AS b")
    assert rows == [{"a": 1, "b": "x"}]

    columns = client.query_pydict("SELECT 1 AS a UNION ALL SELECT 2 ORDER BY a")
    assert columns == {"a": [1, 2]}


def test_query_batches_streams_every_row(client: Client) -> None:
    expected = client.query_arrow("SELECT count(*) AS n FROM taxi_trips LIMIT 1")
    total = sum(
        batch.num_rows
        for batch in client.query_batches("SELECT trip_distance FROM taxi_trips")
    )
    assert total == expected.column("n")[0].as_py()


# ============== Parameterized queries through the typed helpers ==============


@pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC driver not installed")
def test_query_arrow_with_params(client: Client) -> None:
    table = client.query_arrow(
        "SELECT count(*) AS n FROM taxi_trips WHERE trip_distance > $1",
        params=[5.0],
    )
    baseline = client.query_arrow(
        "SELECT count(*) AS n FROM taxi_trips WHERE trip_distance > 5.0"
    )
    assert table.column("n")[0].as_py() == baseline.column("n")[0].as_py()


@pytest.mark.skipif(not ADBC_AVAILABLE, reason="ADBC driver not installed")
def test_query_batches_with_params_streams(client: Client) -> None:
    batches = list(
        client.query_batches(
            "SELECT trip_distance FROM taxi_trips WHERE trip_distance > $1 LIMIT 100",
            params=[1.0],
        )
    )
    assert sum(b.num_rows for b in batches) == 100
    assert all(isinstance(b, pa.RecordBatch) for b in batches)


# ============== Catalog introspection ==============


def test_catalogs(client: Client) -> None:
    assert "spice" in client.catalogs()


def test_schemas_and_tables(client: Client) -> None:
    assert "public" in client.schemas()
    assert "taxi_trips" in client.tables(schema="public")


def test_describe(client: Client) -> None:
    described = client.describe("taxi_trips")
    assert "trip_distance" in list(described["column_name"])


def test_get_schema(client: Client) -> None:
    schema = client.get_schema("SELECT trip_distance, payment_type FROM taxi_trips")
    assert schema.names == ["trip_distance", "payment_type"]


def test_explain(client: Client) -> None:
    plan = client.explain("SELECT count(*) FROM taxi_trips")
    assert plan  # a non-empty plan came back
    analyzed = client.explain("SELECT count(*) FROM taxi_trips", analyze=True)
    assert "elapsed" in analyzed.lower() or "metrics" in analyzed.lower()


def test_show_prints_rows(client: Client, capsys: pytest.CaptureFixture[str]) -> None:
    client.show("SELECT 42 AS answer", n=1)
    captured = capsys.readouterr().out
    assert "answer" in captured
    assert "42" in captured


# ============== DataFrame API end-to-end ==============


def test_dataframe_filter_sort_limit(client: Client) -> None:
    rows = (
        client.table("taxi_trips")
        .select(col("trip_distance"))
        .filter(col("trip_distance") > 2.0)
        .sort(col("trip_distance").desc())
        .limit(5)
        .to_pylist()
    )
    distances = [r["trip_distance"] for r in rows]
    assert len(distances) == 5
    assert distances == sorted(distances, reverse=True)
    assert all(d > 2.0 for d in distances)


def test_dataframe_group_by_aggregate_matches_raw_sql(client: Client) -> None:
    df = (
        client.table("taxi_trips")
        .group_by(col("payment_type"))
        .aggregate(
            F.count().alias("n"),
            F.sum(col("total_amount")).alias("revenue"),
        )
        .sort(col("payment_type"))
        .to_pandas()
    )
    raw = client.query_pandas(
        "SELECT payment_type, count(*) AS n, sum(total_amount) AS revenue "
        "FROM taxi_trips GROUP BY payment_type ORDER BY payment_type"
    )
    assert df["payment_type"].tolist() == raw["payment_type"].tolist()
    assert df["n"].tolist() == raw["n"].tolist()


def test_dataframe_with_column_cast_distinct_count(client: Client) -> None:
    frame = (
        client.from_pydict({"a": [1, 1, 2, 3, 3, 3]})
        .with_column("doubled", col("a") * lit(2))
        .cast({"doubled": "BIGINT"})
    )
    assert frame.count() == 6
    assert frame.select(col("a")).distinct().count() == 3


def test_dataframe_join(client: Client) -> None:
    left = client.from_pydict({"id": [1, 2, 3], "name": ["a", "b", "c"]})
    right = client.from_pydict({"id": [2, 3, 4], "score": [20, 30, 40]})
    joined = (
        left.join(right, on="id").select(col("name"), col("score")).sort(col("score"))
    )
    assert joined.to_pydict() == {"name": ["b", "c"], "score": [20, 30]}


def test_dataframe_set_operations(client: Client) -> None:
    first = client.from_pydict({"v": [1, 2, 3]})
    second = client.from_pydict({"v": [3, 4]})
    assert first.union(second).count() == 4  # UNION deduplicates
    assert first.union(second, all=True).count() == 5
    assert first.intersect(second).to_pydict() == {"v": [3]}
    assert sorted(first.except_(second).to_pydict()["v"]) == [1, 2]


def test_dataframe_unnest(client: Client) -> None:
    rows = client.sql("SELECT make_array(1, 2, 3) AS a").unnest("a").to_pylist()
    assert [r["a"] for r in rows] == [1, 2, 3]


def test_dataframe_describe(client: Client) -> None:
    stats = (
        client.table("taxi_trips").select(col("trip_distance")).describe().to_pandas()
    )
    assert len(stats) > 0


def test_dataframe_from_arrow_and_pandas_round_trip(client: Client) -> None:
    source = pa.table({"x": [10, 20, 30]})
    assert client.from_arrow(source).count() == 3

    pd = pytest.importorskip("pandas")
    assert client.from_pandas(pd.DataFrame({"x": [1, 2]})).count() == 2


def test_dataframe_to_sql_executes(client: Client) -> None:
    frame = client.table("taxi_trips").filter(col("trip_distance") > 10.0)
    via_sql = client.query_arrow(f"SELECT count(*) AS n FROM ({frame.to_sql()})")
    assert via_sql.column("n")[0].as_py() == frame.count()


def test_dataframe_arrow_c_stream_interop(client: Client) -> None:
    frame = client.from_pydict({"v": [1, 2, 3]})
    assert pa.table(frame) == frame.to_arrow()


# ============== Expression DSL and functions ==============


def test_functions_math(client: Client) -> None:
    row = (
        client.from_pydict({"x": [-2.5]})
        .select(
            F.abs(col("x")).alias("abs"),
            F.round(F.sqrt(lit(16.0))).alias("root"),
            F.ceil(col("x")).alias("ceil"),
            F.floor(col("x")).alias("floor"),
            F.power(lit(2), lit(10)).alias("pow"),
        )
        .to_pylist()[0]
    )
    assert row == {"abs": 2.5, "root": 4.0, "ceil": -2.0, "floor": -3.0, "pow": 1024.0}


def test_functions_strings(client: Client) -> None:
    row = (
        client.from_pydict({"s": ["  Spice AI  "]})
        .select(
            F.lower(F.trim(col("s"))).alias("lower"),
            F.length(F.trim(col("s"))).alias("len"),
            F.replace(F.trim(col("s")), lit("AI"), lit("SDK")).alias("replaced"),
            F.starts_with(F.trim(col("s")), lit("Spice")).alias("starts"),
            F.concat(lit("a"), lit("b")).alias("cat"),
            F.substr(lit("integration"), lit(1), lit(5)).alias("sub"),
        )
        .to_pylist()[0]
    )
    assert row == {
        "lower": "spice ai",
        "len": 8,
        "replaced": "Spice SDK",
        "starts": True,
        "cat": "ab",
        "sub": "integ",
    }


def test_functions_datetime(client: Client) -> None:
    rows = client.query_pylist(
        "SELECT date_part('year', to_timestamp('2026-08-19T00:00:00Z')) AS y"
    )
    assert rows[0]["y"] == 2026

    truncated = (
        client.from_pydict({"n": [1]})
        .select(F.date_part(lit("month"), F.to_timestamp(lit("2026-08-19"))).alias("m"))
        .to_pylist()[0]
    )
    assert truncated["m"] == 8


def test_functions_conditional(client: Client) -> None:
    from spicepy import case

    rows = (
        client.from_pydict({"amount": [5, 25, 75]})
        .select(
            col("amount"),
            case()
            .when(col("amount") < lit(10), lit("small"))
            .when(col("amount") < lit(50), lit("medium"))
            .otherwise(lit("large"))
            .alias("bucket"),
            F.coalesce(F.nullif(col("amount"), lit(5)), lit(-1)).alias("coalesced"),
        )
        .sort(col("amount"))
        .to_pylist()
    )
    assert [r["bucket"] for r in rows] == ["small", "medium", "large"]
    assert [r["coalesced"] for r in rows] == [-1, 25, 75]


def test_functions_aggregates(client: Client) -> None:
    row = (
        client.from_pydict({"v": [1, 2, 2, 3, 4]})
        .aggregate(
            F.count().alias("n"),
            F.count_distinct(col("v")).alias("distinct"),
            F.min(col("v")).alias("lo"),
            F.max(col("v")).alias("hi"),
            F.avg(col("v")).alias("mean"),
            F.median(col("v")).alias("median"),
        )
        .to_pylist()[0]
    )
    assert row == {"n": 5, "distinct": 4, "lo": 1, "hi": 4, "mean": 2.4, "median": 2}


def test_functions_window(client: Client) -> None:
    rows = (
        client.from_pydict({"v": [30, 10, 20]})
        .select(
            col("v"),
            F.row_number().over(order_by=col("v")).alias("rn"),
            F.lag(col("v")).over(order_by=col("v")).alias("prev"),
        )
        .sort(col("v"))
        .to_pylist()
    )
    assert [r["rn"] for r in rows] == [1, 2, 3]
    assert [r["prev"] for r in rows] == [None, 10, 20]


def test_functions_arrays_and_structs(client: Client) -> None:
    row = (
        client.sql("SELECT 1 AS n")
        .select(
            F.array_length(F.make_array(lit(1), lit(2), lit(3))).alias("len"),
            F.array_has(F.make_array(lit(1), lit(2)), lit(2)).alias("has"),
            F.get_field(F.named_struct(a=lit(7)), "a").alias("field"),
        )
        .to_pylist()[0]
    )
    assert row == {"len": 3, "has": True, "field": 7}


# ============== Writers ==============


def test_write_parquet_round_trip(client: Client, tmp_path) -> None:
    import pyarrow.parquet as pq

    target = tmp_path / "trips.parquet"
    client.write_parquet("SELECT trip_distance FROM taxi_trips LIMIT 25", str(target))
    assert pq.read_table(target).num_rows == 25


def test_write_csv_round_trip(client: Client, tmp_path) -> None:
    import pyarrow.csv as pa_csv

    target = tmp_path / "trips.csv"
    client.write_csv(
        "SELECT trip_distance, total_amount FROM taxi_trips LIMIT 25", str(target)
    )
    table = pa_csv.read_csv(target)
    assert table.num_rows == 25
    assert table.column_names == ["trip_distance", "total_amount"]


def test_write_json_round_trip(client: Client, tmp_path) -> None:
    target = tmp_path / "trips.ndjson"
    client.write_json("SELECT trip_distance FROM taxi_trips LIMIT 10", str(target))
    lines = target.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 10
    assert all("trip_distance" in json.loads(line) for line in lines)


# ============== Active query management ==============


def test_list_active_queries_returns_a_list(client: Client) -> None:
    queries = client.list_active_queries()
    assert isinstance(queries, list)
    for query in queries:
        assert query.query_id
        assert query.protocol


def test_cancel_active_query(client: Client) -> None:
    """Start a deliberately slow query on another thread, then cancel it."""
    started = threading.Event()

    def run_slow_query() -> None:
        started.set()
        try:
            # A blowup join the optimizer cannot shortcut (a bare count(*) over
            # a cross join can). Bounded inputs keep it finite: the runtime can
            # take minutes to actually stop a cancelled cross join, and an
            # unbounded one would keep burning CPU under the remaining tests.
            reader = client.query(
                "SELECT sum(a.total_amount * b.total_amount) "
                "FROM (SELECT * FROM taxi_trips LIMIT 500000) a "
                "CROSS JOIN (SELECT * FROM taxi_trips LIMIT 500000) b"
            )
            reader.read_all()
        except Exception:  # noqa: S110 - cancellation is the success path
            pass

    # Daemon: the abandoned Flight stream can take a while to observe the
    # cancellation, and the test does not need to wait for it.
    worker = threading.Thread(target=run_slow_query, daemon=True)
    worker.start()
    assert started.wait(timeout=10)

    # Wait for the runtime to report the query, then cancel it. Match on the
    # head of the SQL: the runtime truncates sql_preview.
    target_id = None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and target_id is None:
        for query in client.list_active_queries():
            if query.sql_preview.startswith("SELECT sum(a.total_amount"):
                target_id = query.query_id
                break
        time.sleep(0.5)
    assert target_id is not None, "slow query never appeared in list_active_queries"

    # The SDK contract: cancelling a listed query is acknowledged, cancelling
    # an unknown id raises. (How fast the runtime then unwinds the operators —
    # minutes, for a cross join — is runtime behavior, so it is not asserted.)
    client.cancel_active_query(target_id)

    from spicepy.error import SpiceAIError

    with pytest.raises(SpiceAIError):
        client.cancel_active_query("00000000-0000-0000-0000-000000000000")
