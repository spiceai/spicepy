import os
import time
import re
import pytest
from spicepy import Client, RefreshOpts
from spicepy.config import (
    SPICE_USER_AGENT,
    DEFAULT_LOCAL_FLIGHT_URL,
    DEFAULT_LOCAL_HTTP_URL,
)


# Skip cloud tests if TEST_SPICE_CLOUD is not set to true
def skip_cloud():
    skip = os.environ.get("TEST_SPICE_CLOUD") != "true"
    return pytest.mark.skipif(skip, reason="Cloud tests disabled")


def get_cloud_client():
    api_key = os.environ["API_KEY"]
    return Client(api_key=api_key, flight_url="grpc+tls://flight.spiceai.io")


def get_local_client():
    return Client(flight_url=DEFAULT_LOCAL_FLIGHT_URL, http_url=DEFAULT_LOCAL_HTTP_URL)


def test_user_agent_is_populated():
    # use a regex to match the expected user agent string
    matching_regex = r"spicepy \d+\.\d+\.\d+ \((Linux|Windows|Darwin)/[\d\w\.\-\_]+ (x86_64|aarch64|i386|arm64)\)"

    assert re.match(matching_regex, SPICE_USER_AGENT)


@skip_cloud()
def test_flight_recent_blocks():
    client = get_cloud_client()
    data = client.query("SELECT * FROM eth.recent_blocks LIMIT 10")
    pandas_data = data.read_pandas()
    assert len(pandas_data) == 10


@skip_cloud()
def test_flight_streaming():
    client = get_cloud_client()
    query = """
SELECT number,
       "timestamp",
       base_fee_per_gas,
       base_fee_per_gas / 1e9 AS base_fee_per_gas_gwei
FROM eth.blocks limit 2000
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


@skip_cloud()
def test_flight_timeout():
    client = get_cloud_client()
    query = """SELECT block_number,
       TO_TIMESTAMP(block_timestamp) as block_timestamp,
       avg(gas) as avg_gas_used,
       avg(max_priority_fee_per_gas) as avg_max_priority_fee_per_gas,
       avg(gas_price) as avg_gas_price,
       avg(gas_price / 1e9) AS avg_gas_price_in_gwei,
       avg(gas * (gas_price / 1e18)) AS avg_fee_in_eth
FROM eth.transactions
WHERE block_timestamp > UNIX_TIMESTAMP()-60*60*24*30 -- last 30 days
GROUP BY block_number, block_timestamp
ORDER BY block_number DESC"""
    try:
        prev_time = time.time()
        _ = client.query(query, timeout=1)
        post_time = time.time()
        # Add 0.1s buffer time to 1s timeout time
        if post_time - prev_time < 1.1:
            assert True
        else:
            assert False
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


if __name__ == "__main__":
    test_flight_recent_blocks()
    test_flight_streaming()
    test_flight_timeout()
    test_local_runtime()
    test_local_runtime_refresh()
