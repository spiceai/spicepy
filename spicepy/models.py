from dataclasses import dataclass, asdict
from typing import Dict, Optional, List

import pandas as pd

from ._http import HttpRequests


@dataclass
class PredictionRequest:
    cid: Optional[str]
    model_id: Optional[str] = None
    return_lookback_data: bool = True

    def to_dict(self) -> Dict:
        return dict(filter(lambda e: e[1] is not None, asdict(self).items()))


@dataclass
class Point:
    timestamp: float
    value: float
    covariate: float


@dataclass
class Prediction:
    now: float
    lookback: Optional[List[Point]]
    forecast: List[Point]

    @classmethod
    def from_dict(cls, pred_dict: Dict) -> "Prediction":
        lookback = pred_dict.get("lookback", None)
        if lookback is not None:
            lookback = [
                Point(look["timestamp"], look["value"], look.get("covariate", None)) for look in lookback
            ]

        try:
            return Prediction(
                now=pred_dict["now"],
                lookback=lookback,
                forecast=[
                    Point(look["timestamp"], look["value"], look.get("covariate", None))
                    for look in pred_dict["forecast"]
                ],
            )
        except KeyError as exc:
            raise ValueError(f"Cannot create `Prediction` from dict={pred_dict}") from exc


class ModelsCollection:
    def __init__(self, client: HttpRequests):
        self.client = client

    def predict(
        self,
        cid: Optional[str] = None,
        model_id: Optional[str] = None,
        return_lookback_data: bool = True,
        to_dataframe: bool = False,
    ) -> Prediction:
        assert not (
            model_id is None and cid is None
        ), "One of 'cid' and 'model_id' is required"
        assert not (
            model_id is not None and cid is not None
        ), "Only one of 'cid' and 'model_id' should be provided"

        resp = self.client.send_request(
            "POST",
            "/v1/predictions",
            body=PredictionRequest(
                model_id=model_id, cid=cid, return_lookback_data=return_lookback_data
            ).to_dict(),
        )
        assert (
            "data" in resp.keys()
        ), f"Invalid JSON response from API. Expected key `data` in response={resp}"
        assert (
            "duration_ms" in resp.keys()
        ), f"Invalid JSON response from API. Expected key `duration_ms` in response={resp}"

        if to_dataframe:
            data = resp["data"].get("lookback", []) + resp["data"]["forecast"]
            return pd.DataFrame(
                data=map(
                    lambda x: [x["timestamp"], x["value"], x.get("covariate")], data
                ),
                columns=["timestamp", "value", "covariate"],
            )
        return Prediction.from_dict(resp["data"])
