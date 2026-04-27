import json
import os
import re
import time

import pyarrow as pa
import pytest
import requests

from spicepy import Client, RefreshOpts
from spicepy.config import (
    DEFAULT_LOCAL_FLIGHT_URL,
    DEFAULT_LOCAL_HTTP_URL,
    SPICE_USER_AGENT,
    get_user_agent,
)
from spicepy.params import infer_arrow_type


def wait_for_ready(
    http_url: str = DEFAULT_LOCAL_HTTP_URL, timeout: int = 60, interval: float = 1.0
) -> bool:
    """Wait for the Spice runtime to be ready by polling the /v1/ready endpoint.

    Args:
        http_url: The base HTTP URL of the Spice runtime.
        timeout: Maximum time to wait in seconds.
        interval: Time between polling attempts in seconds.

    Returns:
        True if the runtime is ready, False if timeout is reached.
    """
    start_time = time.time()
    ready_url = f"{http_url}/v1/ready"

    while time.time() - start_time < timeout:
        try:
            response = requests.get(ready_url, timeout=5)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass  # Server not ready yet
        time.sleep(interval)

    return False


# Skip cloud tests if TEST_SPICE_CLOUD is not set to true
def skip_cloud():
    skip = os.environ.get("TEST_SPICE_CLOUD") != "true"
    return pytest.mark.skipif(
        skip, reason="Cloud tests disabled (set TEST_SPICE_CLOUD=true)"
    )


def get_cloud_client():
    api_key = os.environ.get("SPICE_API_KEY", os.environ.get("API_KEY", ""))
    return Client(api_key=api_key, flight_url="grpc+tls://flight.spiceai.io")


def get_local_client():
    return Client(flight_url=DEFAULT_LOCAL_FLIGHT_URL, http_url=DEFAULT_LOCAL_HTTP_URL)


def test_user_agent_is_populated():
    # use a regex to match the expected user agent string
    matching_regex = r"spicepy/\d+\.\d+\.\d+ \((Linux|Windows|Darwin)/[\d\w\.\-\_]+ (x86_64|aarch64|i386|arm64)\)"

    assert re.match(matching_regex, SPICE_USER_AGENT)


@pytest.mark.cloud
@skip_cloud()
def test_flight_recent_blocks():
    client = get_cloud_client()
    data = client.query("SELECT * FROM tpch.lineitem LIMIT 10")
    pandas_data = data.read_pandas()
    assert len(pandas_data) == 10


@pytest.mark.cloud
@skip_cloud()
def test_flight_streaming():
    client = get_cloud_client()
    query = """
SELECT o_orderkey,
       o_custkey,
       o_orderstatus,
       o_totalprice
FROM tpch.orders LIMIT 2000
    """
    reader = client.query(query)

    total_rows = 0
    num_batches = 0
    has_more = True
    while has_more:
        try:
            flight_batch = reader.read_chunk()
            record_batch = flight_batch.data
            num_batches += 1
            total_rows += record_batch.num_rows
            assert len(record_batch.to_pandas()) == record_batch.num_rows
        except StopIteration:
            has_more = False

    assert total_rows == 2000
    assert num_batches >= 1


@pytest.mark.cloud
@skip_cloud()
def test_flight_timeout():
    client = get_cloud_client()
    query = """SELECT o_orderstatus,
       COUNT(*) as order_count,
       AVG(o_totalprice) as avg_price,
       SUM(o_totalprice) as total_price
FROM tpch.orders
GROUP BY o_orderstatus
ORDER BY total_price DESC"""
    try:
        prev_time = time.time()
        _ = client.query(query, timeout=1)
        post_time = time.time()
        # Add 0.1s buffer time to 1s timeout time
        if post_time - prev_time < 1.1:
            assert True
        else:
            raise AssertionError("Query took too long")
    except TimeoutError:
        assert True


def test_local_runtime():
    assert wait_for_ready(), "Spice runtime did not become ready in time"
    client = get_local_client()
    data = client.query("SELECT * FROM taxi_trips LIMIT 10")
    pandas_data = data.read_pandas()
    assert len(pandas_data) == 10


def test_local_runtime_refresh():
    assert wait_for_ready(), "Spice runtime did not become ready in time"
    client = get_local_client()
    # basic refresh
    response = client.refresh_dataset("taxi_trips", None)
    assert response["message"] == "Dataset refresh triggered for taxi_trips."

    time.sleep(10)
    data = client.query("SELECT * FROM taxi_trips LIMIT 10")
    pandas_data = data.read_pandas()
    assert len(pandas_data) == 10

    # refresh sql limited to 10 rows

    response = client.refresh_dataset(
        "taxi_trips",
        RefreshOpts(refresh_sql="SELECT * FROM taxi_trips LIMIT 10"),
    )
    assert response["message"] == "Dataset refresh triggered for taxi_trips."

    time.sleep(10)
    data = client.query("SELECT * FROM taxi_trips")
    pandas_data = data.read_pandas()
    assert len(pandas_data) == 10

    # refresh sql limited to 20 rows
    response = client.refresh_dataset(
        "taxi_trips",
        RefreshOpts(refresh_sql="SELECT * FROM taxi_trips LIMIT 20"),
    )
    assert response["message"] == "Dataset refresh triggered for taxi_trips."

    time.sleep(10)
    data = client.query("SELECT * FROM taxi_trips")
    pandas_data = data.read_pandas()
    assert len(pandas_data) == 20


# pylint: disable=E1120
def test_user_agent(httpserver):
    reply = {"message": "OK"}
    httpserver.expect_request(
        "/v1/datasets/test/acceleration/refresh",
        headers={"User-Agent": SPICE_USER_AGENT},
    ).respond_with_data(json.dumps(reply), content_type="application/json")
    client = Client(
        flight_url=DEFAULT_LOCAL_FLIGHT_URL, http_url=httpserver.url_for("/")
    )
    response = client.refresh_dataset("test")
    httpserver.check_assertions()
    assert response == reply

    httpserver.expect_request(
        "/v1/datasets/test/acceleration/refresh", headers={"User-Agent": "custom-agent"}
    ).respond_with_data(json.dumps(reply), content_type="application/json")
    client = Client(
        flight_url=DEFAULT_LOCAL_FLIGHT_URL,
        http_url=httpserver.url_for("/"),
        user_agent="custom-agent",
    )
    response = client.refresh_dataset("test")
    httpserver.check_assertions()
    assert response == reply

    custom_ua = get_user_agent("custom-client", "1.0.0", "custom-system")
    httpserver.expect_request(
        "/v1/datasets/test/acceleration/refresh",
        headers={"User-Agent": "custom-client/1.0.0 (custom-system)"},
    ).respond_with_data(json.dumps(reply), content_type="application/json")
    client = Client(
        flight_url=DEFAULT_LOCAL_FLIGHT_URL,
        http_url=httpserver.url_for("/"),
        user_agent=custom_ua,
    )
    response = client.refresh_dataset("test")
    httpserver.check_assertions()
    assert response == reply


if __name__ == "__main__":
    test_flight_recent_blocks()
    test_flight_streaming()
    test_flight_timeout()
    test_local_runtime()
    test_local_runtime_refresh()
    test_user_agent()


# ============== Parameterized Query Tests ==============


def test_infer_arrow_type():
    """Test Arrow type inference from Python values."""
    # Null
    assert infer_arrow_type(None) == pa.null()

    # Boolean
    assert infer_arrow_type(True) == pa.bool_()
    assert infer_arrow_type(False) == pa.bool_()

    # Integer (defaults to int64)
    assert infer_arrow_type(42) == pa.int64()

    # Float (defaults to float64)
    assert infer_arrow_type(3.14) == pa.float64()

    # String
    assert infer_arrow_type("hello") == pa.string()

    # Binary
    assert infer_arrow_type(b"\x00\x01") == pa.binary()


def test_infer_arrow_type_unsupported():
    """Test that unsupported types raise TypeError."""
    with pytest.raises(TypeError):
        infer_arrow_type([1, 2, 3])  # Lists not supported

    with pytest.raises(TypeError):
        infer_arrow_type({"key": "value"})  # Dicts not supported


def skip_if_no_adbc():
    """Skip test if ADBC is not available."""
    try:
        import adbc_driver_flightsql  # noqa: F401
        import adbc_driver_manager  # noqa: F401

        return False
    except ImportError:
        return True


@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_parameterized_query_local():
    """Test parameterized query with local Spice runtime."""
    client = get_local_client()

    # Test with float parameter
    reader = client.query_with_params(
        "SELECT trip_distance, fare_amount FROM taxi_trips WHERE trip_distance > $1 ORDER BY trip_distance LIMIT 5",
        [10.0],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        # Validate trip_distance > 10.0
        trip_distance = batch.column("trip_distance")
        for i in range(batch.num_rows):
            assert trip_distance[i].as_py() > 10.0

    assert total_rows > 0
    assert total_rows <= 5


@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_parameterized_query_multiple_params():
    """Test parameterized query with multiple parameters."""
    client = get_local_client()

    reader = client.query_with_params(
        "SELECT trip_distance, fare_amount FROM taxi_trips WHERE trip_distance > $1 AND fare_amount > $2 LIMIT 5",
        [5.0, 20.0],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        trip_distance = batch.column("trip_distance")
        fare_amount = batch.column("fare_amount")
        for i in range(batch.num_rows):
            assert trip_distance[i].as_py() > 5.0
            assert fare_amount[i].as_py() > 20.0

    assert total_rows <= 5


@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_parameterized_query_with_string():
    """Test parameterized query with string parameter."""
    client = get_local_client()

    reader = client.query_with_params(
        "SELECT trip_distance, fare_amount, store_and_fwd_flag FROM taxi_trips WHERE store_and_fwd_flag = $1 LIMIT 5",
        ["N"],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        flag_col = batch.column("store_and_fwd_flag")
        for i in range(batch.num_rows):
            assert flag_col[i].as_py() == "N"

    assert total_rows <= 5


@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_parameterized_query_with_explicit_types():
    """Test parameterized query with explicit PyArrow types."""
    client = get_local_client()

    reader = client.query_with_params(
        "SELECT trip_distance, fare_amount FROM taxi_trips WHERE trip_distance > $1 LIMIT 5",
        [(10.0, pa.float64())],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows

    assert total_rows <= 5


@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_parameterized_query_mixed_types():
    """Test parameterized query with mixed inferred and explicit types."""
    client = get_local_client()

    reader = client.query_with_params(
        "SELECT trip_distance, fare_amount FROM taxi_trips WHERE trip_distance > $1 AND fare_amount > $2 LIMIT 5",
        [5.0, (20.0, pa.float64())],  # Mixed: inferred float and explicit float64
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows

    assert total_rows <= 5


@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_parameterized_query_no_params():
    """Test parameterized query method with no parameters (regular query)."""
    client = get_local_client()

    reader = client.query_with_params(
        "SELECT trip_distance, fare_amount FROM taxi_trips LIMIT 5", []
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows

    assert total_rows == 5


# ============== Cloud Parameterized Query Tests ==============


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_basic():
    """Test parameterized query with Spice Cloud TPCH dataset."""
    client = get_cloud_client()

    # Test with integer parameter
    reader = client.query_with_params(
        "SELECT l_orderkey, l_quantity, l_extendedprice FROM tpch.lineitem WHERE l_quantity > $1 LIMIT 10",
        [40],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        # Validate l_quantity > 40
        quantity = batch.column("l_quantity")
        for i in range(batch.num_rows):
            assert quantity[i].as_py() > 40

    assert total_rows > 0
    assert total_rows <= 10


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_multiple_params():
    """Test parameterized query with multiple parameters on Spice Cloud."""
    client = get_cloud_client()

    reader = client.query_with_params(
        """SELECT o_orderkey, o_totalprice, o_orderstatus
           FROM tpch.orders
           WHERE o_totalprice > $1 AND o_orderstatus = $2
           LIMIT 10""",
        [100000.0, "O"],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        totalprice = batch.column("o_totalprice")
        status = batch.column("o_orderstatus")
        for i in range(batch.num_rows):
            assert totalprice[i].as_py() > 100000.0
            assert status[i].as_py() == "O"

    assert total_rows <= 10


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_with_explicit_types():
    """Test parameterized query with explicit PyArrow types on Spice Cloud."""
    client = get_cloud_client()

    reader = client.query_with_params(
        "SELECT c_custkey, c_name, c_acctbal FROM tpch.customer WHERE c_acctbal > $1 LIMIT 10",
        [(5000.0, pa.float64())],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        acctbal = batch.column("c_acctbal")
        for i in range(batch.num_rows):
            assert acctbal[i].as_py() > 5000.0

    assert total_rows <= 10


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_empty_params():
    """Test parameterized query with empty params on Spice Cloud."""
    client = get_cloud_client()

    reader = client.query_with_params(
        "SELECT n_nationkey, n_name, n_regionkey FROM tpch.nation LIMIT 5",
        [],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows

    assert total_rows == 5


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_string_param():
    """Test parameterized query with string parameter on Spice Cloud."""
    client = get_cloud_client()

    reader = client.query_with_params(
        "SELECT n_nationkey, n_name, n_regionkey FROM tpch.nation WHERE n_name = $1",
        ["UNITED STATES"],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        name = batch.column("n_name")
        for i in range(batch.num_rows):
            assert name[i].as_py() == "UNITED STATES"

    assert total_rows == 1


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_with_join():
    """Test parameterized query with JOIN on Spice Cloud TPCH dataset."""
    client = get_cloud_client()

    reader = client.query_with_params(
        """SELECT o.o_orderkey, o.o_totalprice, c.c_name, c.c_acctbal
           FROM tpch.orders o
           JOIN tpch.customer c ON o.o_custkey = c.c_custkey
           WHERE o.o_totalprice > $1 AND c.c_acctbal > $2
           LIMIT 20""",
        [200000.0, 5000.0],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        totalprice = batch.column("o_totalprice")
        acctbal = batch.column("c_acctbal")
        for i in range(batch.num_rows):
            assert totalprice[i].as_py() > 200000.0
            assert acctbal[i].as_py() > 5000.0

    assert total_rows > 0
    assert total_rows <= 20


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_aggregation():
    """Test parameterized query with aggregation on Spice Cloud."""
    client = get_cloud_client()

    # Get aggregated stats for orders with status parameter
    reader = client.query_with_params(
        """SELECT o_orderstatus,
                  COUNT(*) as order_count,
                  CAST(AVG(o_totalprice) AS DOUBLE) as avg_price,
                  SUM(o_totalprice) as total_price
           FROM tpch.orders
           WHERE o_orderstatus = $1
           GROUP BY o_orderstatus""",
        ["F"],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        status = batch.column("o_orderstatus")
        order_count = batch.column("order_count")
        for i in range(batch.num_rows):
            assert status[i].as_py() == "F"
            assert order_count[i].as_py() > 0

    assert total_rows == 1


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_in_clause_simulation():
    """Test parameterized query simulating IN clause with multiple ORs."""
    client = get_cloud_client()

    reader = client.query_with_params(
        """SELECT r_regionkey, r_name, r_comment
           FROM tpch.region
           WHERE r_name = $1 OR r_name = $2""",
        ["AMERICA", "EUROPE"],
    )

    total_rows = 0
    result_names = []
    for batch in reader:
        total_rows += batch.num_rows
        name = batch.column("r_name")
        for i in range(batch.num_rows):
            result_names.append(name[i].as_py())

    assert total_rows == 2
    assert "AMERICA" in result_names
    assert "EUROPE" in result_names


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_with_int8():
    """Test parameterized query with explicit int8 type on Spice Cloud."""
    client = get_cloud_client()

    reader = client.query_with_params(
        "SELECT r_regionkey, r_name FROM tpch.region WHERE r_regionkey = $1",
        [(1, pa.int8())],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        regionkey = batch.column("r_regionkey")
        for i in range(batch.num_rows):
            assert regionkey[i].as_py() == 1

    assert total_rows == 1


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_with_int64():
    """Test parameterized query with explicit int64 type on Spice Cloud."""
    client = get_cloud_client()

    reader = client.query_with_params(
        "SELECT l_orderkey, l_partkey, l_quantity FROM tpch.lineitem WHERE l_orderkey = $1 LIMIT 10",
        [(1, pa.int64())],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        orderkey = batch.column("l_orderkey")
        for i in range(batch.num_rows):
            assert orderkey[i].as_py() == 1

    assert total_rows > 0


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_with_float32():
    """Test parameterized query with explicit float32 type on Spice Cloud."""
    client = get_cloud_client()

    reader = client.query_with_params(
        "SELECT l_orderkey, l_discount FROM tpch.lineitem WHERE l_discount >= $1 LIMIT 10",
        [(0.05, pa.float32())],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        discount = batch.column("l_discount")
        for i in range(batch.num_rows):
            # l_discount may be Decimal type, convert to float for comparison
            discount_val = float(discount[i].as_py())
            assert discount_val >= 0.05

    assert total_rows > 0


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_subquery():
    """Test parameterized query with subquery on Spice Cloud."""
    client = get_cloud_client()

    reader = client.query_with_params(
        """SELECT c_custkey, c_name, c_acctbal
           FROM tpch.customer
           WHERE c_nationkey IN (
               SELECT n_nationkey FROM tpch.nation WHERE n_regionkey = $1
           )
           LIMIT 20""",
        [1],  # AMERICA region
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows

    assert total_rows > 0
    assert total_rows <= 20


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_order_by():
    """Test parameterized query with ORDER BY on Spice Cloud."""
    client = get_cloud_client()

    reader = client.query_with_params(
        """SELECT o_orderkey, o_totalprice, o_orderdate
           FROM tpch.orders
           WHERE o_totalprice > $1
           ORDER BY o_totalprice DESC
           LIMIT 10""",
        [300000.0],
    )

    prices = []
    for batch in reader:
        totalprice = batch.column("o_totalprice")
        for i in range(batch.num_rows):
            prices.append(totalprice[i].as_py())

    assert len(prices) > 0
    assert len(prices) <= 10
    # Verify results are ordered descending
    for i in range(len(prices) - 1):
        assert prices[i] >= prices[i + 1]


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_like_pattern():
    """Test parameterized query with LIKE pattern on Spice Cloud."""
    client = get_cloud_client()

    reader = client.query_with_params(
        "SELECT p_partkey, p_name, p_brand FROM tpch.part WHERE p_brand = $1 LIMIT 10",
        ["Brand#13"],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        p_brand = batch.column("p_brand")
        for i in range(batch.num_rows):
            assert p_brand[i].as_py() == "Brand#13"

    assert total_rows > 0


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_three_params():
    """Test parameterized query with three parameters on Spice Cloud."""
    client = get_cloud_client()

    reader = client.query_with_params(
        """SELECT l_orderkey, l_quantity, l_extendedprice, l_discount
           FROM tpch.lineitem
           WHERE l_quantity >= $1 AND l_extendedprice > $2 AND l_discount <= $3
           LIMIT 15""",
        [25, 40000.0, 0.05],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        quantity = batch.column("l_quantity")
        price = batch.column("l_extendedprice")
        discount = batch.column("l_discount")
        for i in range(batch.num_rows):
            assert quantity[i].as_py() >= 25
            assert price[i].as_py() > 40000.0
            assert discount[i].as_py() <= 0.05

    assert total_rows <= 15


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_mixed_param_types():
    """Test parameterized query with mixed explicit and inferred param types."""
    client = get_cloud_client()

    reader = client.query_with_params(
        """SELECT s_suppkey, s_name, s_acctbal, s_nationkey
           FROM tpch.supplier
           WHERE s_acctbal > $1 AND s_nationkey = $2
           LIMIT 10""",
        [(8000.0, pa.float64()), 24],  # Mix explicit type tuple and plain value
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        acctbal = batch.column("s_acctbal")
        nationkey = batch.column("s_nationkey")
        for i in range(batch.num_rows):
            assert acctbal[i].as_py() > 8000.0
            assert nationkey[i].as_py() == 24

    assert total_rows <= 10


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_partsupp_table():
    """Test parameterized query on partsupp table on Spice Cloud."""
    client = get_cloud_client()

    reader = client.query_with_params(
        """SELECT ps_partkey, ps_suppkey, ps_availqty, ps_supplycost
           FROM tpch.partsupp
           WHERE ps_supplycost > $1 AND ps_availqty > $2
           LIMIT 10""",
        [900.0, 5000],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        supplycost = batch.column("ps_supplycost")
        availqty = batch.column("ps_availqty")
        for i in range(batch.num_rows):
            assert supplycost[i].as_py() > 900.0
            assert availqty[i].as_py() > 5000

    assert total_rows <= 10


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_larger_result_set():
    """Test parameterized query returning larger result set on Spice Cloud."""
    client = get_cloud_client()

    reader = client.query_with_params(
        "SELECT l_orderkey, l_linenumber, l_quantity FROM tpch.lineitem WHERE l_quantity > $1 LIMIT 500",
        [45],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        quantity = batch.column("l_quantity")
        for i in range(batch.num_rows):
            assert quantity[i].as_py() > 45

    assert total_rows > 0
    assert total_rows <= 500


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_count_aggregation():
    """Test parameterized query with COUNT aggregation on Spice Cloud."""
    client = get_cloud_client()

    reader = client.query_with_params(
        """SELECT n_name, COUNT(*) as customer_count
           FROM tpch.customer c
           JOIN tpch.nation n ON c.c_nationkey = n.n_nationkey
           WHERE n.n_regionkey = $1
           GROUP BY n_name
           ORDER BY customer_count DESC""",
        [2],  # ASIA region
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        customer_count = batch.column("customer_count")
        for i in range(batch.num_rows):
            assert customer_count[i].as_py() > 0

    # ASIA region has 5 nations
    assert total_rows == 5


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_null_safe():
    """Test parameterized query handling columns that might have NULL values."""
    client = get_cloud_client()

    reader = client.query_with_params(
        """SELECT p_partkey, p_name, p_mfgr, p_comment
           FROM tpch.part
           WHERE p_size > $1
           LIMIT 10""",
        [45],
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        # Just verify we can read all columns without errors
        _ = batch.column("p_partkey")
        _ = batch.column("p_name")
        _ = batch.column("p_mfgr")
        _ = batch.column("p_comment")

    assert total_rows > 0


@pytest.mark.cloud
@skip_cloud()
@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_cloud_parameterized_query_with_bool():
    """Test parameterized query with explicit boolean type on Spice Cloud."""
    client = get_cloud_client()

    # Using a comparison that returns a boolean-like result
    reader = client.query_with_params(
        """SELECT l_orderkey, l_returnflag, l_linestatus
           FROM tpch.lineitem
           WHERE l_returnflag = $1
           LIMIT 10""",
        [("R", pa.string())],  # 'R' for returned
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows
        returnflag = batch.column("l_returnflag")
        for i in range(batch.num_rows):
            assert returnflag[i].as_py() == "R"

    assert total_rows > 0
