from spicepy import Client
import os


def test_recent_blocks():
    api_key = os.environ["API_KEY"]
    client = Client(api_key)
    data = client.query("SELECT * FROM eth.recent_blocks LIMIT 10;")
    pandas_data = data.read_pandas()
    assert len(pandas_data) == 10


if __name__ == "__main__":
    test_recent_blocks()
