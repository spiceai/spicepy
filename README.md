# spicepy

Spice.xyz client library for Python.

## Installation

```bash
pip install git+https://github.com/spiceai/spicepy
```

## Usage

### Arrow Query
**SQL Query**
```python
from spicepy import Client

client = Client('API_KEY')
data = client.query('SELECT * FROM eth.recent_blocks LIMIT 10;', timeout=5*60)
pd = data.read_pandas()
```
**Firecache Query (Available if firecache is enabled)**
```python
from spicepy import Client

client = Client('API_KEY')
data = client.fire_query('SELECT * FROM eth.recent_blocks LIMIT 10;', timeout=5*60)
pd = data.read_pandas()
```

Querying data is done through a `Client` object that initialize the connection with Spice endpoint. `Client` has the following arguments:

- **api_key** (string, required): API key to authenticate with the endpoint.
- **url** (string, optional): URL of the endpoint to use (default: grpc+tls://flight.spiceai.io; firecache: grpc+tls://firecache.spiceai.io)
- **tls_root_cert** (Path or string, optional): Path to the tls certificate to use for the secure connection (omit for automatic detection)

Once a `Client` is obtained queries can be made using the `query()` function. The `query()` function has the following arguments:

- **query** (string, required): The SQL query.
- **timeout** (int, optional): The timeout in seconds.

A custom timeout can be set by passing the `timeout` parameter in the `query` function call. If no timeout is specified, it will default to a 10 min timeout then cancel the query, and a TimeoutError exception will be raised.

## Documentation

Check out our [Documentation](https://docs.spice.xyz/sdks/python-sdk) to learn more about how to use the Python SDK.
