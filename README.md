# spicepy

Spice.xyz client library for Python.

## Installation

```bash
pip install git+https://github.com/spiceai/spicepy
```

## Usage

### Arrow Query

```python
from spicepy import Client

client = Client('API_KEY')
data = client.query('SELECT * FROM eth.recent_blocks LIMIT 10;', timeout=10*60)
pd = data.read_pandas()
```

Querying data is done through a `Client` object that initialize the connection with Spice endpoint. `Client` have the following arguments:

- **api_key** (string, required): API key to authenticate with the endpoint.
- **url** (string, optional): URL of the endpoint to use (default: grpc+tls://flight.spiceai.io)
- **tls_root_cert** (Path or string, optional): Path to the tls certificate to use for the secure connection (ommit for automatic detection)

### Web3 interface

Once a client is created you can also use the [web3.py](https://web3py.readthedocs.io) interface under the `w3` attribute.

```python
from spicepy import Client

client = Client('API_KEY')
print(client.w3.eth.get_block_number())
```

User can manually set timeout in the function call. If no timeout is specified, the query will timeout after 15 mins by default and a TimeoutError exception will be raised.

`timeout` is `int` in seconds. 

## Documentation

Check out our [Documentation](https://docs.spice.xyz/sdks/python-sdk) to learn more about how to use the Python SDK.
