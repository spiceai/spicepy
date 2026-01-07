import json
import os
import re
import time

import pyarrow as pa
import pytest

from spicepy import Client, Param, RefreshOpts
from spicepy.config import DEFAULT_LOCAL_FLIGHT_URL, DEFAULT_LOCAL_HTTP_URL, SPICE_USER_AGENT, get_user_agent
from spicepy.params import infer_arrow_type


# Skip cloud tests if TEST_SPICE_CLOUD is not set to true
def skip_cloud():
    skip = os.environ.get("TEST_SPICE_CLOUD") != "true"
    return pytest.mark.skipif(skip, reason="Cloud tests disabled (set TEST_SPICE_CLOUD=true)")


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
    assert num_batches > 1


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
    client = get_local_client()
    data = client.query("SELECT * FROM taxi_trips LIMIT 10")
    pandas_data = data.read_pandas()
    assert len(pandas_data) == 10


def test_local_runtime_refresh():
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
        "/v1/datasets/test/acceleration/refresh", headers={"User-Agent": SPICE_USER_AGENT}
    ).respond_with_data(json.dumps(reply), content_type="application/json")
    client = Client(flight_url=DEFAULT_LOCAL_FLIGHT_URL, http_url=httpserver.url_for("/"))
    response = client.refresh_dataset("test")
    httpserver.check_assertions()
    assert response == reply

    httpserver.expect_request(
        "/v1/datasets/test/acceleration/refresh", headers={"User-Agent": "custom-agent"}
    ).respond_with_data(json.dumps(reply), content_type="application/json")
    client = Client(flight_url=DEFAULT_LOCAL_FLIGHT_URL, http_url=httpserver.url_for("/"), user_agent="custom-agent")
    response = client.refresh_dataset("test")
    httpserver.check_assertions()
    assert response == reply

    custom_ua = get_user_agent("custom-client", "1.0.0", "custom-system")
    httpserver.expect_request(
        "/v1/datasets/test/acceleration/refresh", headers={"User-Agent": "custom-client/1.0.0 (custom-system)"}
    ).respond_with_data(json.dumps(reply), content_type="application/json")
    client = Client(flight_url=DEFAULT_LOCAL_FLIGHT_URL, http_url=httpserver.url_for("/"), user_agent=custom_ua)
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


def test_param_factory_methods():
    """Test Param class factory methods."""
    # Integer types
    p1 = Param.int8(1)
    assert p1.value == 1
    assert p1.arrow_type == pa.int8()
    assert p1.has_explicit_type()

    p2 = Param.int16(100)
    assert p2.value == 100
    assert p2.arrow_type == pa.int16()

    p3 = Param.int32(1000)
    assert p3.value == 1000
    assert p3.arrow_type == pa.int32()

    p4 = Param.int64(10000)
    assert p4.value == 10000
    assert p4.arrow_type == pa.int64()

    # Unsigned integer types
    p5 = Param.uint8(1)
    assert p5.value == 1
    assert p5.arrow_type == pa.uint8()

    p6 = Param.uint16(100)
    assert p6.arrow_type == pa.uint16()

    p7 = Param.uint32(1000)
    assert p7.arrow_type == pa.uint32()

    p8 = Param.uint64(10000)
    assert p8.arrow_type == pa.uint64()

    # Floating point types
    p9 = Param.float32(1.5)
    assert p9.value == 1.5
    assert p9.arrow_type == pa.float32()

    p10 = Param.float64(2.5)
    assert p10.value == 2.5
    assert p10.arrow_type == pa.float64()

    # String types
    p11 = Param.string("test")
    assert p11.value == "test"
    assert p11.arrow_type == pa.string()

    p12 = Param.large_string("large test")
    assert p12.value == "large test"
    assert p12.arrow_type == pa.large_string()

    # Boolean
    p13 = Param.bool_(True)
    assert p13.value is True
    assert p13.arrow_type == pa.bool_()

    # Binary
    p14 = Param.binary(b"\x01\x02\x03")
    assert p14.value == b"\x01\x02\x03"
    assert p14.arrow_type == pa.binary()

    # Null
    p15 = Param.null()
    assert p15.value is None
    assert p15.arrow_type == pa.null()

    # Generic factory method
    p16 = Param.of(42)
    assert p16.value == 42
    assert not p16.has_explicit_type()

    p17 = Param.of(42, pa.int32())
    assert p17.value == 42
    assert p17.arrow_type == pa.int32()
    assert p17.has_explicit_type()


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
    """Test parameterized query with explicit Param types."""
    client = get_local_client()

    reader = client.query_with_params(
        "SELECT trip_distance, fare_amount FROM taxi_trips WHERE trip_distance > $1 LIMIT 5", [Param.float64(10.0)]
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
        [5.0, Param.float64(20.0)],  # Mixed: inferred float and explicit float64
    )

    total_rows = 0
    for batch in reader:
        total_rows += batch.num_rows

    assert total_rows <= 5


@pytest.mark.skipif(skip_if_no_adbc(), reason="ADBC driver not installed")
def test_parameterized_query_no_params():
    """Test parameterized query method with no parameters (regular query)."""
    client = get_local_client()

    reader = client.query_with_params("SELECT trip_distance, fare_amount FROM taxi_trips LIMIT 5", [])

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
        "SELECT o_orderkey, o_totalprice, o_orderstatus FROM tpch.orders WHERE o_totalprice > $1 AND o_orderstatus = $2 LIMIT 10",
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
    """Test parameterized query with explicit Param types on Spice Cloud."""
    client = get_cloud_client()

    reader = client.query_with_params(
        "SELECT c_custkey, c_name, c_acctbal FROM tpch.customer WHERE c_acctbal > $1 LIMIT 10",
        [Param.float64(5000.0)],
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