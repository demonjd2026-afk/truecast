"""Runtime xG inference from a trained logistic model (pure Python).

Loads the artifact written by ml/train.py. If the artifact is missing it falls
back to a closed-form logistic so the service still runs.
"""

from __future__ import annotations

import json
import math
import os

from .features import sigmoid, xg_vector

_ARTIFACT = os.path.join(os.path.dirname(__file__), "models", "xg.json")


class XGModel:
    def __init__(self) -> None:
        self._m = None
        try:
            with open(_ARTIFACT) as f:
                self._m = json.load(f)
        except Exception:
            self._m = None

    @property
    def trained(self) -> bool:
        return self._m is not None

    @property
    def metrics(self) -> dict:
        return (self._m or {}).get("metrics", {})

    def predict(self, distance_m: float, angle_rad: float, is_header: bool,
                big_chance: bool, under_pressure: bool) -> float:
        if self._m is None:
            return self._fallback(distance_m, angle_rad, is_header, big_chance)
        x = xg_vector(distance_m, angle_rad, is_header, big_chance, under_pressure)
        z = self._standardise(x)
        logit = self._m["intercept"] + sum(c * zi for c, zi in zip(self._m["coef"], z))
        return round(max(0.01, min(0.99, sigmoid(logit))), 3)

    def _standardise(self, x: list[float]) -> list[float]:
        mean, scale = self._m["mean"], self._m["scale"]
        return [(xi - m) / (s or 1.0) for xi, m, s in zip(x, mean, scale)]

    @staticmethod
    def _fallback(distance_m: float, angle_rad: float, is_header: bool, big_chance: bool) -> float:
        log_odds = -0.62 + 2.6 * angle_rad - 0.10 * distance_m
        if is_header:
            log_odds -= 0.65
        if big_chance:
            log_odds += 1.1
        return round(max(0.01, min(0.97, 1.0 / (1.0 + math.exp(-log_odds)))), 3)


_MODEL: XGModel | None = None


def get_xg_model() -> XGModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = XGModel()
    return _MODEL
