from spicepy import Client


def test_recent_blocks():
    client = Client("3534|0a05e0808ff647ea98a656efab3f7e30")
    data = client.query("SELECT * FROM eth.recent_blocks LIMIT 10;")
    pd = data.read_pandas()
    assert len(pd) == 10
