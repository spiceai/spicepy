# spicepy

Spice.ai client library for Python.

## Installation

```bash
pip install git+https://github.com/spiceai/spicepy@v1.0.1
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

### HTTP API
#### Prices
Get the latest price for a token pair.
```python
>>> client.prices.get_latest("BTC-USDC")
{'BTC-USDC': Quote(pair=None,
                   prices={'binance': 26639.37},
                   min_price=26639.37,
                   max_price=26639.37,
                   mean_price=26639.37)}
```

Get historical data 
```python
>>> client.prices.get("BTC-USDC")
{'BTC-USDC': [Price(timestamp=datetime.datetime(2023, 9, 22, 4, 20, tzinfo=datetime.timezone.utc),
                    price=26642.77,
                    high=26642.77,
                    low=26633.98,
                    open=26633.98,
                    close=26642.77),
              Price(timestamp=datetime.datetime(2023, 9, 22, 4, 25, tzinfo=datetime.timezone.utc),
                    price=26631.46,
                    high=26638.77,
                    low=26631.46,
                    open=26638.77,
                    close=26631.46),
              Price(timestamp=datetime.datetime(2023, 9, 22, 4, 30, tzinfo=datetime.timezone.utc),
                    price=26639.61,
                    high=26644.16,
                    low=26634.41,
                    open=26634.41,
                    close=26627.63)]}
```

Support for multiple pairs and configurable time periods
```python
>>> client.prices.get(["BTC-USDC", "ETH-BTC"],
    start=datetime.now() - timedelta(days=7),
    end=datetime.now() - timedelta(days=6),
    granularity=timedelta(hours=12)
)
{'BTC-USDC': [Price(timestamp=datetime.datetime(2023, 9, 15, 12, 0, tzinfo=datetime.timezone.utc),
                    price=26426.23,
                    high=26686.76,
                    low=26372.71,
                    open=26526.38,
                    close=26426.23),
              Price(timestamp=datetime.datetime(2023, 9, 16, 0, 0, tzinfo=datetime.timezone.utc),
                    price=26601.63,
                    high=26886.13,
                    low=26224.17,
                    open=26407.31,
                    close=26601.63)],
 'ETH-BTC': [Price(timestamp=datetime.datetime(2023, 9, 15, 12, 0, tzinfo=datetime.timezone.utc),
                   price=0.06127,
                   high=0.06152,
                   low=0.06116,
                   open=0.06132,
                   close=0.06127),
             Price(timestamp=datetime.datetime(2023, 9, 16, 0, 0, tzinfo=datetime.timezone.utc),
                   price=0.06166,
                   high=0.06181,
                   low=0.0613,
                   open=0.06134,
                   close=0.06166)]}

```

#### AI Models
Spicepy supports running prediction against your own trained models.
```python
>>> client.models.predict(cid=my_cid)
Prediction(now=19122451,
      lookback=[
            Point(timestamp=19122442,
                  value=20.689821537,
                  covariate=55),
            Point(timestamp=19122443,
                  value=18.707675599,
                  covariate=149),
            Point(timestamp=19122444,
                  value=17.992664808,
                  covariate=264),
            Point(timestamp=19122445,
                  value=19.648576381,
                  covariate=11),
            Point(timestamp=19122446,
                  value=17.420299285,
                  covariate=136),
            Point(timestamp=19122447,
                  value=16.075633207,
                  covariate=369),
            Point(timestamp=19122448,
                  value=18.082861418,
                  covariate=234),
            Point(timestamp=19122449,
                  value=19.851269726,
                  covariate=121),
            Point(timestamp=19122450,
                  value=20.570846326,
                  covariate=72),
            Point(timestamp=19122451,
                  value=20.787251115,
                  covariate=255)
      ],
      forecast=[
            Point(timestamp=19122451,
                  value=10.867426872253418,
                  covariate=None)
      ]
)
```
And out of the box support for `pandas`.
```python
>>> client.models.predict(cid=my_cid, to_dataframe=True)
    timestamp      value  covariate
0    19122420  22.230395      119.0
1    19122421  21.227253      201.0
2    19122422  21.579048      112.0
3    19122423  20.766538      123.0
4    19122424  20.623809      135.0
5    19122425  22.092613      121.0
6    19122426  21.859050       96.0
7    19122427  20.265461      192.0
8    19122428  20.609428      101.0
9    19122429  23.008345      114.0
10   19122429  10.818775        NaN
```

## Documentation

Check out our [Documentation](https://docs.spice.ai/sdks/python-sdk) to learn more about how to use the Python SDK.
