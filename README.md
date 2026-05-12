# spicepy

[![Build](https://github.com/spiceai/spicepy/actions/workflows/build.yml/badge.svg)](https://github.com/spiceai/spicepy/actions/workflows/build.yml)
[![Lint](https://github.com/spiceai/spicepy/actions/workflows/lint.yml/badge.svg)](https://github.com/spiceai/spicepy/actions/workflows/lint.yml)
[![Test](https://github.com/spiceai/spicepy/actions/workflows/test.yml/badge.svg)](https://github.com/spiceai/spicepy/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/spiceai/spicepy/branch/trunk/graph/badge.svg)](https://codecov.io/gh/spiceai/spicepy)
[![PyPI version](https://badge.fury.io/py/spicepy.svg)](https://badge.fury.io/py/spicepy)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Spice.ai client library for Python.

## Requirements

- Python 3.11+

## Installation

`spicepy` is not published on PyPI under that name; install directly from GitHub:

```bash
pip install git+https://github.com/spiceai/spicepy@v4.0.0
```

Optional extras:

```bash
# Parameterized queries (ADBC FlightSQL driver)
pip install "spicepy[params] @ git+https://github.com/spiceai/spicepy@v4.0.0"

# Polars output support
pip install "spicepy[polars] @ git+https://github.com/spiceai/spicepy@v4.0.0"
```

## Connecting

Querying data goes through a `Client`, which connects to a Spice endpoint over Arrow Flight (gRPC) and the HTTP control plane.

```python
from spicepy import Client

# Local spice runtime (defaults: grpc://localhost:50051, http://localhost:8090).
# Follow the quickstart guide: https://github.com/spiceai/spiceai
client = Client()

# Spice.ai Cloud — endpoints are region-specific. Substitute your app's region
# (e.g. us-east-1, us-west-2, eu-west-1).
client = Client(
    api_key="API_KEY",
    flight_url="grpc+tls://us-east-1-prod-aws-flight.spiceai.io",
    http_url="https://us-east-1-prod-aws-data.spiceai.io",
)
```

`Client` accepts:

- **api_key** (str, optional): API key for authenticated endpoints. Falls back to the `SPICE_API_KEY` environment variable.
- **flight_url** (str, optional): Arrow Flight endpoint. Defaults to `grpc://localhost:50051`. For Spice.ai Cloud, use the region-specific hostname `grpc+tls://<region>-prod-aws-flight.spiceai.io`.
- **http_url** (str, optional): HTTP endpoint for control-plane operations (e.g. `refresh_dataset`). Defaults to `http://localhost:8090`. For Spice.ai Cloud, use `https://<region>-prod-aws-data.spiceai.io`.
- **tls_root_cert** (Path or str, optional): Path to a TLS root certificate. Omit for automatic detection via `certifi`.
- **user_agent** (str, optional): Custom `User-Agent` prefix. Build a default with `spicepy.config.get_user_agent()`.

## Usage

### Run a SQL query

The low-level `query()` method returns a `pyarrow.flight.FlightStreamReader` you can stream or materialize.

```python
data = client.query(
    "SELECT trip_distance, total_amount FROM taxi_trips "
    "ORDER BY trip_distance DESC LIMIT 10",
    timeout=5 * 60,
)
df = data.read_pandas()
```

If no `timeout` is given, queries default to a 10-minute timeout before raising `TimeoutError`.

### One-shot output helpers

For common cases use the typed helpers, which materialize the result in your preferred shape:

```python
table   = client.query_arrow("SELECT * FROM taxi_trips LIMIT 1000")
pdf     = client.query_pandas("SELECT * FROM taxi_trips LIMIT 1000")
pldf    = client.query_polars("SELECT * FROM taxi_trips LIMIT 1000")   # needs spicepy[polars]
rows    = client.query_pylist("SELECT * FROM taxi_trips LIMIT 1000")
columns = client.query_pydict("SELECT * FROM taxi_trips LIMIT 1000")
```

Stream results as Arrow `RecordBatch`es without materializing the whole table:

```python
for batch in client.query_batches("SELECT * FROM huge_table"):
    process(batch)
```

All helpers (except `query_batches`) accept `timeout=` and `params=` — see below.

### Parameterized queries (recommended for user input)

Parameterized queries prevent SQL injection and let the engine reuse plans. Use positional placeholders (`$1`, `$2`, …) and pass values via `params=` or `query_with_params()`.

```python
# Inferred types via the typed helpers
table = client.query_arrow(
    "SELECT trip_distance, fare_amount FROM taxi_trips WHERE trip_distance > $1 LIMIT 10",
    params=[5.0],
)

# Multiple parameters, streaming reader
reader = client.query_with_params(
    "SELECT * FROM taxi_trips WHERE trip_distance > $1 AND fare_amount > $2 LIMIT 10",
    [5.0, 20.0],
)
for batch in reader:
    print(batch.to_pandas())

# Query without parameters (pass an empty list)
reader = client.query_with_params("SELECT * FROM taxi_trips LIMIT 10", [])
```

Requires the `params` extra (`pip install "spicepy[params] @ git+https://github.com/spiceai/spicepy@v4.0.0"`).

#### Explicit Arrow types

For precise control, pass `(value, pyarrow.DataType)` tuples instead of plain values:

```python
import pyarrow as pa

reader = client.query_with_params(
    "SELECT * FROM t WHERE id = $1 AND amount = $2",
    [(123, pa.int32()), (99.99, pa.float64())],
)
```

Common PyArrow types: `pa.int8/16/32/64()`, `pa.uint8/16/32/64()`, `pa.float16/32/64()`, `pa.string()`, `pa.large_string()`, `pa.binary()`, `pa.large_binary()`, `pa.bool_()`, `pa.date32()`, `pa.date64()`, `pa.time32()`, `pa.time64()`, `pa.timestamp()`, `pa.duration()`, `pa.decimal128()`, `pa.decimal256()`, `pa.null()`. See the [PyArrow type reference](https://arrow.apache.org/docs/python/api/datatypes.html).

### DataFrame API

`SpiceDataFrame` is a lazy SQL builder. Each operation returns a new DataFrame holding a SQL fragment; terminal operations (`collect`, `to_pandas`, `to_polars`, `to_arrow`, `count`, `show`) ship the compiled SQL to the runtime over the existing Flight transport. There is no client-side execution.

```python
from spicepy import Client, col
from spicepy import functions as F

client = Client()

trips = client.table("taxi_trips")

result = (
    trips
    .filter(col("trip_distance") > 1.0)
    .group_by(col("payment_type"))
    .aggregate(
        F.count().alias("n"),
        F.sum(col("total_amount")).alias("revenue"),
        F.avg(col("trip_distance")).alias("avg_distance"),
    )
    .sort(col("revenue").desc())
    .limit(10)
    .to_pandas()
)
```

Entry points on `Client`:

| Method                     | Description                                           |
| -------------------------- | ----------------------------------------------------- |
| `client.table(name)`       | DataFrame over an existing table                      |
| `client.sql(query)`        | DataFrame wrapping an arbitrary SQL query             |
| `client.from_arrow(table)` | DataFrame from a PyArrow `Table` (inline VALUES)      |
| `client.from_pandas(df)`   | DataFrame from a pandas DataFrame (inline VALUES)     |
| `client.from_pydict(data)` | DataFrame from a column-oriented dict (inline VALUES) |

DataFrame operations include `select`, `with_column(s)`, `drop`, `rename`, `cast`, `filter`/`where`, `limit`, `head`, `sort`/`order_by`, `distinct`, `union`, `intersect`, `except_`, `join`, `cross_join`, `group_by(...).aggregate(...)`, `schema`, `explain`, `to_sql`, and the materializers `collect`/`to_arrow`/`to_pandas`/`to_polars`/`to_pylist`/`to_pydict`/`count`/`show`.

#### Expressions

`Expr` is the expression type. Build one with `col(name)`, `lit(value)`, or any of the functions in `spicepy.functions`. Operators (`+ - * / % == != < <= > >= & | ~`) return new `Expr`s, so expressions compose without evaluating.

```python
from spicepy import col, lit, case
from spicepy import functions as F

predicate = (col("trip_distance") > 1.0) & col("fare_amount").is_not_null()

amount_bucket = (
    case()
    .when(col("total_amount") < 10, lit("small"))
    .when(col("total_amount") < 50, lit("medium"))
    .otherwise(lit("large"))
    .alias("bucket")
)
```

`spicepy.functions` exposes common DataFusion functions: aggregates (`sum`, `avg`, `count`, `count_distinct`, `min`, `max`, `stddev`, `variance`, `median`, `approx_distinct`, `array_agg`), math (`abs`, `round`, `ceil`, `floor`, `sqrt`, `power`, `ln`, `log`, `exp`), strings (`lower`, `upper`, `length`, `trim`, `concat`, `substr`, `replace`, `regexp_match`, `starts_with`, `ends_with`), date/time (`now`, `current_date`, `current_timestamp`, `date_trunc`, `date_part`, `extract`), null/control flow (`coalesce`, `nullif`, `ifnull`, `case`), and window functions (`row_number`, `rank`, `dense_rank`, `percent_rank`, `cume_dist`, `lag`, `lead`, `first_value`, `last_value`, `nth_value`).

Anything not covered by the DSL is reachable by writing SQL directly via `client.query(...)` or `client.sql(...)`.

### Catalog introspection

```python
client.catalogs()                # list[str]
client.schemas()                 # list[str]
client.schemas(catalog="spice")  # list[str]
client.tables()                  # list[str]
client.tables(schema="public")   # list[str]
client.describe("taxi_trips")    # pandas.DataFrame of column metadata
client.get_schema("SELECT * FROM taxi_trips")  # pyarrow.Schema, no rows fetched
client.explain("SELECT * FROM taxi_trips", analyze=False, verbose=False)  # str
client.show("SELECT * FROM taxi_trips", n=20)  # pretty-print to stdout
```

### Writers

Stream query results directly to a file:

```python
client.write_parquet("SELECT * FROM taxi_trips", "trips.parquet")
client.write_csv("SELECT * FROM taxi_trips", "trips.csv")
client.write_json("SELECT * FROM taxi_trips", "trips.ndjson")   # newline-delimited JSON
```

### Dataset refresh

Trigger a refresh of an accelerated dataset:

```python
from spicepy import RefreshOpts

client.refresh_dataset(
    "taxi_trips",
    RefreshOpts(refresh_sql="SELECT * FROM taxi_trips LIMIT 10"),
)
```

## Documentation

Check out our [Documentation](https://docs.spice.ai/sdks/python-sdk) to learn more about how to use the Python SDK.
