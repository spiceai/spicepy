import os
import time
from spicepy import Client


def get_test_client():
    api_key = os.environ["API_KEY"]
    return Client(api_key)


def test_flight_recent_blocks():
    client = get_test_client()
    data = client.query("SELECT * FROM eth.recent_blocks LIMIT 10")
    pandas_data = data.read_pandas()
    assert len(pandas_data) == 10


def test_firecache_recent_blocks():
    client = get_test_client()
    data = client.fire_query("SELECT * FROM eth.recent_blocks LIMIT 10")
    pandas_data = data.read_pandas()
    assert len(pandas_data) == 10


def test_flight_streaming():
    client = get_test_client()
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


def test_flight_timeout():
    client = get_test_client()
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


if __name__ == "__main__":
    test_flight_recent_blocks()
    test_firecache_recent_blocks()
    test_flight_streaming()
    test_flight_timeout()
