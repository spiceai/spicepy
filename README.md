# spicepy

[![Build](https://github.com/spiceai/spicepy/actions/workflows/build.yml/badge.svg)](https://github.com/spiceai/spicepy/actions/workflows/build.yml)
[![Lint](https://github.com/spiceai/spicepy/actions/workflows/lint.yml/badge.svg)](https://github.com/spiceai/spicepy/actions/workflows/lint.yml)
[![Test](https://github.com/spiceai/spicepy/actions/workflows/test.yml/badge.svg)](https://github.com/spiceai/spicepy/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/spiceai/spicepy/branch/trunk/graph/badge.svg)](https://codecov.io/gh/spiceai/spicepy)
[![PyPI version](https://badge.fury.io/py/spicepy.svg)](https://badge.fury.io/py/spicepy)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Spice.ai client library for Python.

## Installation

```bash
pip install git+https://github.com/spiceai/spicepy@v3.1.0
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

For precise control over Arrow types, use tuples of `(value, pyarrow.DataType)`:

```python
import pyarrow as pa
from spicepy import Client

client = Client()

reader = client.query_with_params(
    'SELECT * FROM table WHERE id = $1 AND amount = $2',
    [(123, pa.int32()), (99.99, pa.float64())]
)
```

**Common PyArrow types:**

- **Integers**: `pa.int8()`, `pa.int16()`, `pa.int32()`, `pa.int64()`, `pa.uint8()`, `pa.uint16()`, `pa.uint32()`, `pa.uint64()`
- **Floating point**: `pa.float16()`, `pa.float32()`, `pa.float64()`
- **Strings**: `pa.string()`, `pa.large_string()`
- **Binary**: `pa.binary()`, `pa.large_binary()`
- **Boolean**: `pa.bool_()`
- **Temporal**: `pa.date32()`, `pa.date64()`, `pa.time32()`, `pa.time64()`, `pa.timestamp()`, `pa.duration()`
- **Decimals**: `pa.decimal128()`, `pa.decimal256()`
- **Null**: `pa.null()`

See the [PyArrow documentation](https://arrow.apache.org/docs/python/api/datatypes.html) for the full list of available types.

Querying data is done through a `Client` object that initialize the connection with Spice endpoint. `Client` has the following arguments:

- **api_key** (string, required): API key to authenticate with the endpoint.
- **url** (string, optional): URL of the endpoint to use (default: grpc+tls://flight.spiceai.io; firecache: grpc+tls://firecache.spiceai.io)
- **tls_root_cert** (Path or string, optional): Path to the tls certificate to use for the secure connection (omit for automatic detection)
- **user_agent** (string, optional): A custom `User-Agent` string to pass when connecting to Spice. Use `spicepy.config.get_user_agent` to build the custom `User-Agent`

Once a `Client` is obtained queries can be made using the `query()` function. The `query()` function has the following arguments:

- **query** (string, required): The SQL query.
- **timeout** (int, optional): The timeout in seconds.

A custom timeout can be set by passing the `timeout` parameter in the `query` function call. If no timeout is specified, it will default to a 10 min timeout then cancel the query, and a TimeoutError exception will be raised.

### Search

Search datasets for documents similar to a piece of text. This requires datasets with an embedding column and a loaded embedding model — see [Search & Retrieval](https://docs.spice.ai/features/search-and-retrieval) for how to configure them.

```python
from spicepy import Client

client = Client()

result = client.search(
    'tokyo plane tickets',
    datasets=['app_messages'],
    limit=3,
    additional_columns=['timestamp'],
)

print(f'{len(result)} matches in {result.duration_ms}ms')
for match in result:
    print(match.score, match.dataset, match.matches, match.data)
```

`search()` takes the search text plus the following keyword arguments:

- **datasets** (list of string, optional): Datasets to search. Omit to search every searchable dataset.
- **limit** (int, optional): Maximum matches to return per dataset.
- **where** (string, optional): A SQL predicate filtering candidate rows, without the leading `WHERE` — for example `'user_id = 42'`.
- **additional_columns** (list of string, optional): Extra columns to return with each match. Primary key columns are returned under `primary_key`, the rest under `data`.
- **keywords** (list of string, optional): Keywords for the lexical pass of a hybrid search, which the runtime combines with the vector scores into a single ranking.

It returns a `SearchResult` holding `duration_ms` and a list of `SearchMatch`. Iterating the result yields the matches directly. Each `SearchMatch` has:

- **dataset** (string): The dataset the match was found in.
- **score** (float): The match's similarity to the query. Higher is more similar.
- **matches** (dict): The matched values, keyed by source column. Each value is a list, because one column may contribute several chunks to a single match.
- **primary_key** (dict): The primary key columns identifying the matched row. Empty when the dataset declares no primary key.
- **data** (dict): Any `additional_columns` that were requested.
- **metadata** (dict): Extra per-match metadata the runtime attached.

## Documentation

Check out our [Documentation](https://docs.spice.ai/sdks/python-sdk) to learn more about how to use the Python SDK.
