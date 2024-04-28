# spicepy

Spice.ai client library for Python.

## Installation

```bash
pip install git+https://github.com/spiceai/spicepy@v1.0.1
```

## Usage

### Arrow Query with local spice runtime

Follow the [quickstart guide](https://github.com/spiceai/spiceai?tab=readme-ov-file#%EF%B8%8F-quickstart-local-machine) to install and run spice locally

```python
from spicepy import Client

client = Client()
data = client.query('SELECT trip_distance, total_amount FROM taxi_trips ORDER BY trip_distance DESC LIMIT 10;', timeout=5*60)
pd = data.read_pandas()
```

### Arrow Query with spice.ai cloud

**SQL Query**

```python
from spicepy import Client

client = Client(
      api_key='API_KEY',
      flight_url="grpc+tls://flight.spiceai.io"
)
data = client.query('SELECT * FROM eth.recent_blocks LIMIT 10;', timeout=5*60)
pd = data.read_pandas()
```

**Firecache Query (Available if firecache is enabled)**

```python
from spicepy import Client

client = Client(
      api_key='API_KEY',
      flight_url="grpc+tls://flight.spiceai.io"
)
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

### AI Models
Spicepy supports running prediction against your own trained models.
```python
>>> client.models.predict(cid=my_cid, return_lookback_data=False)
Prediction(now=19122471,
           lookback=None,
           forecast=[
            Point(timestamp=19122471,
                  value=10.867426872253418,
                  covariate=None)
            ]
)
```

And out of the box support for `pandas`.
```python
>>> df = client.models.predict(cid=my_cid, to_dataframe=True)
>>> print(df.head(n=3))
    timestamp      value  covariate
0    19122420  22.230395      119.0
1    19122421  21.227253      201.0
2    19122422  21.579048      112.0
```

## Documentation

Check out our [Documentation](https://docs.spice.ai/sdks/python-sdk) to learn more about how to use the Python SDK.
