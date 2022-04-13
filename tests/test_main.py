from spicepy import Client


def test_recent_blocks():
    client = Client("3534|0a05e0808ff647ea98a656efab3f7e30")
    data = client.query("SELECT * FROM eth.recent_blocks LIMIT 10;")
    pandas_data = data.read_pandas()
    assert len(pandas_data) == 10


if __name__ == "__main__":
    test_recent_blocks()
