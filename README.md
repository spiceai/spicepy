# spice-py

Spice.xyz client library.

## Installation

From `pip`:

```bash
pip install git+https://github.com/spicehq/spice-py
```

From code:

```bash
pip install -e .
```

## Usage

```python
from spicepy import Client

client = Client('API_KEY')
data = client.query('SELECT * FROM eth.recent_blocks LIMIT 10;')
pd = data.read_pandas()
```

Querying data is done through a `Client` object that initialize the connection with Spice endpoint. `Client` have the following arguments:

- **api_key** (string, required): API key to authenticate with the endpoint.
- **url** (string, optional): URL of the endpoint to use (default: grpc+tls://flight.spiceai.io)
- **tls_root_cert** (Path or string, optional): Path to the tls certificate to use for the secure connection (ommit for automatic detection)
