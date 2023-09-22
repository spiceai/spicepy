from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
from typing import Any, List, Dict, Optional

from ._http import HttpRequests


@dataclass
class Quote:
    prices: Dict[str, str] = field(default_factory=dict)
    
    min_price: Optional[str] = field(default=None, metadata={'json': 'minPrice'})
    max_price: Optional[str] = field(default=None, metadata={'json': 'maxPrice'})
    mean_price: Optional[str] = field(default=None, metadata={'json': 'avePrice'})
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Quote":
        return Quote(
            prices=d.get('prices'),
            min_price=d.get('minPrice'),
            max_price=d.get('maxPrice'),
            mean_price=d.get('meanPrice')
        )

@dataclass
class Price:
    timestamp: Optional[datetime] = None
    price: float = 0.0
    high: float = 0.0
    low: float = 0.0
    open: float = 0.0
    close: float = 0.0

@dataclass
class QuoteHistorical:
    pair: Optional[str] = None
    prices: List[Price] = field(default_factory=list)

@dataclass
class QuotesRequest:
    symbols: List[str] = field(default_factory=list)
    convert: Optional[str] = None

@dataclass
class PricePairsRequest:
    start: Optional[int] = None
    end: Optional[int] = None
    granularity: Optional[timedelta] = None
    pairs: List[str] = field(default_factory=list)


class PriceCollection:
    def __init__(self, client: HttpRequests):
        self.client = client

    def get_latest(self, pairs: List[str]) -> Dict[str, Quote]:
        if not pairs:
            return {}

        resp = self.client.send_request("GET", "/v1/prices/latest", param={"pair" : pairs})
        return {pair: Quote.from_dict(q) for (pair, q) in resp.items() }
        
    def get(self,
        pairs: List[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        granularity: Optional[timedelta] = None
    ) -> Dict[str, List[Price]]:
        if not pairs:
            return {}
    
        resp = self.client.send_request("GET", "/v1/prices", param={
            "pair" : pairs,
            "start": start_time,
            "end": end_time,
            "granularity": granularity
        })
        return {pair: [Price(**p) for p in prices] for (pair, prices) in resp.items() }