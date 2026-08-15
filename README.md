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

### Text-to-SQL (NSQL)

`nsql()` answers a question in natural language: the configured LLM generates SQL, the runtime runs it read-only, and both the rows and the generated query come back. It requires an LLM model in the Spicepod — see [Text to SQL](https://docs.spice.ai/features/text-to-sql) for how to configure one.

```python
from spicepy import Client

client = Client()

result = client.nsql('top 5 customers by revenue', datasets=['sales'])

print('generated SQL:', result.sql)
for row in result:
    print(row)
```

`nsql()` takes the question plus the following keyword arguments:

- **model** (string, optional): The LLM used to generate SQL. Omit when the Spicepod configures exactly one compatible model.
- **datasets** (list of string, optional): Datasets to sample when building the model's context. This is a sampling hint — it does not restrict which tables the generated query may reference.
- **sample_data_enabled** (bool, optional): Include sample rows in the model's context. Improves generation on ambiguous schemas, at the cost of sending data values to the model.
- **prompt_cache_key** (string, optional): A stable key forwarded to the model provider for prompt caching.

It returns an `NsqlResult` holding `sql`, `row_count`, `schema` (a list of `NsqlField`), and `data`. Iterating the result yields the rows directly.

Values in `data` are decoded from JSON, so they carry JSON's types rather than the Arrow types named in `schema`. When Arrow types matter, generate the query and run it yourself — which is also how to inspect or edit a generated query before it runs:

```python
sql = client.nsql_generate_sql('top 5 customers by revenue')
print(sql)

table = client.query(sql).read_all()
```

### Runtime Health and Status

`is_ready()` reports whether the runtime is ready to serve queries — useful for waiting
on a runtime to come up before querying it:

```python
from spicepy import Client

client = Client(http_url="http://127.0.0.1:8090")

if not client.is_ready():
    print("runtime is not ready yet")
```

When you need to know *which* component is not ready, `runtime_status()` reports each
runtime connection separately:

```python
for component in client.runtime_status():
    print(f"{component.name} ({component.endpoint}): {component.status}")

# http (127.0.0.1:8090): Ready
# flight (127.0.0.1:50051): Ready
# metrics (N/A): Disabled
# opentelemetry (127.0.0.1:50051): Ready
```

Each `ConnectionDetails` carries the component `name` (`http`, `flight`, `metrics` or
`opentelemetry`), its `endpoint`, and its `status` — a `ComponentStatus` of
`Initializing`, `Ready`, `Disabled`, `Error`, `Refreshing`, `ShuttingDown` or
`NotLoaded`. `component.is_ready` is shorthand for a `Ready` status. A status added by
a future runtime is preserved as a plain string rather than raising.

### Listing and Cancelling Running Queries

`list_active_queries()` reports the synchronous queries running in the caller's scope —
those started by `query()`, `query_with_params()`, FlightSQL, NSQL and search — and
`cancel_active_query()` stops one by id.

The runtime does not hand a query's id back to the client that submitted it, so the two
are used together: list to find the query, then cancel it.

Two boundaries apply, and a query is reachable only inside both.

**One runtime instance.** The runtime holds active synchronous queries in memory, per
process, and these endpoints report only what the instance answering them knows. Behind
a load balancer, `http_url` may resolve to an instance that never received the query —
it will not be listed, and its id reports as not found.

**One authenticated principal**, not a `Client` instance. The principal is whatever
credential the runtime authenticates — an API key or a client certificate — so every
client presenting the same credential lists and cancels the same queries. Only requests
for which the runtime establishes no principal at all share the `public` scope. A query
outside the caller's scope is reported as if it did not exist.

> **Runtime version.** Principal scoping on these two endpoints landed in
> [spiceai/spiceai#12841](https://github.com/spiceai/spiceai/pull/12841) and is in no
> runtime release up to and including `v2.1.5`. Against an earlier runtime both calls
> operate on every active query the instance holds, for any caller with write access.
> Check your runtime version before relying on the scope described above.

```python
from spicepy import Client

client = Client(http_url="http://127.0.0.1:8090")

for query in client.list_active_queries():
    print(f"{query.query_id} [{query.protocol}] {query.sql_preview}")
    print(f"  started at {query.started_at.isoformat()}")

# Cancel a long-running query by id.
queries = client.list_active_queries()
if queries:
    client.cancel_active_query(queries[0].query_id)
```

`cancel_active_query()` returns `None` on success and raises `SpiceAIError` otherwise —
including when the id falls outside the caller's scope, which the runtime reports as not
found rather than cancelling.

## Documentation

Check out our [Documentation](https://docs.spice.ai/sdks/python-sdk) to learn more about how to use the Python SDK.
