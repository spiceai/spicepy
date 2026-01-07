# spicepy

Spice.ai client library for Python.

## Installation

```bash
pip install git+https://github.com/spiceai/spicepy@v2.0.0
```

For parameterized query support, install with the optional `params` extra:

```bash
pip install "spicepy[params]"
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
data = client.query('SELECT * FROM taxi_trips LIMIT 10;', timeout=5*60)
pd = data.read_pandas()
```

### Parameterized Queries (Recommended)

Use parameterized queries to prevent SQL injection and improve query performance. Parameters use positional placeholders (`$1`, `$2`, etc.):

```python
from spicepy import Client

client = Client()

# Query with automatic type inference
reader = client.query_with_params(
    'SELECT trip_distance, fare_amount FROM taxi_trips WHERE trip_distance > $1 LIMIT 10',
    [5.0]
)

for batch in reader:
    print(batch.to_pandas())

# Query without parameters (use empty list)
reader = client.query_with_params(
    'SELECT * FROM taxi_trips LIMIT 10',
    []
)
```

#### Multiple Parameters

```python
reader = client.query_with_params(
    'SELECT trip_distance, fare_amount FROM taxi_trips WHERE trip_distance > $1 AND fare_amount > $2 LIMIT 10',
    [5.0, 20.0]
)
```

#### Explicit Type Control

For precise control over Arrow types, use the `Param` class:

```python
from spicepy import Client, Param

client = Client()

reader = client.query_with_params(
    'SELECT * FROM table WHERE id = $1 AND amount = $2',
    [Param.int32(123), Param.float64(99.99)]
)
```

**Supported Param factory methods:**

- **Integers**: `Param.int8()`, `Param.int16()`, `Param.int32()`, `Param.int64()`, `Param.uint8()`, `Param.uint16()`, `Param.uint32()`, `Param.uint64()`
- **Floating point**: `Param.float16()`, `Param.float32()`, `Param.float64()`
- **Strings**: `Param.string()`, `Param.large_string()`
- **Binary**: `Param.binary()`, `Param.large_binary()`, `Param.fixed_size_binary()`
- **Boolean**: `Param.bool_()`
- **Temporal**: `Param.date32()`, `Param.date64()`, `Param.time32()`, `Param.time64()`, `Param.timestamp()`, `Param.duration()`
- **Decimals**: `Param.decimal128()`, `Param.decimal256()`
- **Null**: `Param.null()`
- **Generic**: `Param.of(value, arrow_type=None)`

Querying data is done through a `Client` object that initialize the connection with Spice endpoint. `Client` has the following arguments:

- **api_key** (string, required): API key to authenticate with the endpoint.
- **url** (string, optional): URL of the endpoint to use (default: grpc+tls://flight.spiceai.io; firecache: grpc+tls://firecache.spiceai.io)
- **tls_root_cert** (Path or string, optional): Path to the tls certificate to use for the secure connection (omit for automatic detection)
- **user_agent** (string, optional): A custom `User-Agent` string to pass when connecting to Spice. Use `spicepy.config.get_user_agent` to build the custom `User-Agent`

Once a `Client` is obtained queries can be made using the `query()` function. The `query()` function has the following arguments:

- **query** (string, required): The SQL query.
- **timeout** (int, optional): The timeout in seconds.

A custom timeout can be set by passing the `timeout` parameter in the `query` function call. If no timeout is specified, it will default to a 10 min timeout then cancel the query, and a TimeoutError exception will be raised.

## Documentation

Check out our [Documentation](https://docs.spice.ai/sdks/python-sdk) to learn more about how to use the Python SDK.
