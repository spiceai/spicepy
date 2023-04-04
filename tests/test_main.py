
import os
from spicepy import Client


def get_test_client():
    api_key = os.environ["API_KEY"]
    return Client(api_key)


def test_recent_blocks():
    client = get_test_client()
    data = client.query("SELECT * FROM eth.recent_blocks LIMIT 10;")
    pandas_data = data.read_pandas()
    assert len(pandas_data) == 10


def test_streaming():
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


def test_timeout():
    client = get_test_client()
    query = """SELECT * FROM eth.logs ORDER BY block_number DESC"""
    try:
        _ = client.query(query, timeout=1)
        assert False
    except TimeoutError:
        assert True


if __name__ == "__main__":
    test_recent_blocks()
    test_streaming()
    test_timeout()
