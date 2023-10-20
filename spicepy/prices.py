from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, List, Dict, Optional, Union

from ._http import HttpRequests


@dataclass
class Quote:
    prices: Dict[str, float] = field(default_factory=dict)

    min_price: Optional[float] = field(default=None, metadata={"json": "minPrice"})
    max_price: Optional[float] = field(default=None, metadata={"json": "maxPrice"})
    mean_price: Optional[float] = field(default=None, metadata={"json": "avePrice"})

    @classmethod
    def from_dict(cls, _dict: Dict[str, Any]) -> "Quote":
        _dict["min_price"] = (
            float(_dict.get("minPrice")) if _dict.get("minPrice") is not None else None
        )
        _dict["max_price"] = (
            float(_dict.get("maxPrice")) if _dict.get("maxPrice") is not None else None
        )
        _dict["mean_price"] = (
            float(_dict.get("meanPrice")) if _dict.get("meanPrice") is not None else None
        )

        _dict["prices"] = {key: float(value) for key, value in _dict.get("prices", {}).items()}

        return Quote(**{k: v for k, v in _dict.items() if k in Quote.__annotations__})  # pylint: disable=E1101


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
            self.timestamp = datetime.fromisoformat(
                self.timestamp.replace("Z", "")
            ).replace(tzinfo=timezone.utc)


class PriceCollection:
    def __init__(self, client: HttpRequests):
        self.client = client

    def get_latest(self, pairs: List[str]) -> Dict[str, Quote]:
        if not pairs:
            return {}

        if isinstance(pairs, str):
            pairs = [pairs]

        resp = self.client.send_request(
            "GET", "/v1/prices", param={"pairs": pairs}
        )
        return {pair: Quote.from_dict(q) for (pair, q) in resp.items()}

    def get(
        self,
        pairs: Union[str, List[str]],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        granularity: Optional[timedelta] = None,
    ) -> Dict[str, List[Price]]:
        if not pairs:
            return {}

        if isinstance(pairs, str):
            pairs = [pairs]

        resp = self.client.send_request(
            "GET",
            "/v1/prices/historical",
            param={
                "pairs": pairs,
                "start": start,
                "end": end,
                "granularity": granularity,
            },
        )
        return {pair: [Price(**p) for p in prices] for (pair, prices) in resp.items()}
