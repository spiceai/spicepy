from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from typing import Any, List, Dict, Optional, Union

from ._http import HttpRequests

@dataclass
class Quote:
    prices: Dict[str, float] = field(default_factory=dict)
    
    min_price: Optional[float] = field(default=None, metadata={'json': 'minPrice'})
    max_price: Optional[float] = field(default=None, metadata={'json': 'maxPrice'})
    mean_price: Optional[float] = field(default=None, metadata={'json': 'avePrice'})
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Quote":
        d['min_price'] = float(d.get('minPrice')) if d.get('minPrice') is not None else None
        d['max_price'] = float(d.get('maxPrice')) if d.get('maxPrice') is not None else None
        d['mean_price'] = float(d.get('meanPrice')) if d.get('meanPrice') is not None else None
        
        d['prices'] = {key: float(value) for key, value in d.get('prices', {}).items()}
        
        return Quote(**{k: v for k, v in d.items() if k in Quote.__annotations__})

@dataclass
class Price:
    timestamp: Optional[datetime] = None
    price: float = 0.0
    high: float = 0.0
    low: float = 0.0
    open: float = 0.0
    close: float = 0.0

    def __post_init__(self):
        if self.timestamp:
            self.timestamp = datetime.fromisoformat(self.timestamp.replace("Z", "")).replace(tzinfo=timezone.utc)

class PriceCollection:
    def __init__(self, client: HttpRequests):
        self.client = client

    def get_latest(self, pairs: List[str]) -> Dict[str, Quote]:
        if not pairs:
            return {}
        
        if isinstance(pairs, str):
            pairs = [pairs]

        resp = self.client.send_request("GET", "/v1/prices/latest", param={"pair" : pairs})
        return {pair: Quote.from_dict(q) for (pair, q) in resp.items() }
        
    def get(self,
        pairs: Union[str, List[str]],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        granularity: Optional[timedelta] = None
    ) -> Dict[str, List[Price]]:
        if not pairs:
            return {}

        if isinstance(pairs, str):
            pairs = [pairs]
        
        resp = self.client.send_request("GET", "/v1/prices", param={
            "pair" : pairs,
            "start": start,
            "end": end,
            "granularity": granularity
        })
        return {pair: [Price(**p) for p in prices] for (pair, prices) in resp.items() }