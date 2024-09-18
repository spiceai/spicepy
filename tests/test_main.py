import os
import time
import pytest
from spicepy import Client
from spicepy.config import SPICE_USER_AGENT


# Skip cloud tests if TEST_SPICE_CLOUD is not set to true
def skip_cloud():
    skip = os.environ.get("TEST_SPICE_CLOUD") != "true"
    return pytest.mark.skipif(skip, reason="Cloud tests disabled")


def get_cloud_client():
    api_key = os.environ["API_KEY"]
    return Client(api_key=api_key, flight_url="grpc+tls://flight.spiceai.io")


def get_local_client():
    return Client(flight_url="grpc://localhost:50051")


def test_user_agent_is_populated():
    expected_platforms = ["x86", "x86_64", "aarch64", "arm64", "AMD64"]

    assert SPICE_USER_AGENT.split(" ")[0] == "spicepy"
    assert SPICE_USER_AGENT.split(" ")[1] == "2.0.0"

    arch = SPICE_USER_AGENT.split(" ")[3].replace(")", "")
    assert arch in expected_platforms


@skip_cloud()
def test_flight_recent_blocks():
    client = get_cloud_client()
    data = client.query("SELECT * FROM eth.recent_blocks LIMIT 10")
    pandas_data = data.read_pandas()
    assert len(pandas_data) == 10


@skip_cloud()
def test_firecache_recent_blocks():
    client = get_cloud_client()
    data = client.fire_query("SELECT * FROM eth.recent_blocks LIMIT 10")
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


if __name__ == "__main__":
    test_flight_recent_blocks()
    test_firecache_recent_blocks()
    test_flight_streaming()
    test_flight_timeout()
    test_local_runtime()
