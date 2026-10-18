"""Runtime live win-probability inference (pure Python).

Multinomial logistic over home/draw/away, trained by ml/train.py on snapshots
sampled from simulated matches. Falls back to a simple score/time heuristic if
the artifact is missing.
"""

from __future__ import annotations

import json
import os

from .features import softmax, winprob_vector

_ARTIFACT = os.path.join(os.path.dirname(__file__), "models", "winprob.json")


class WinProbModel:
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

    def predict(self, minute: float, score_diff: int, xg_diff: float,
                shots_diff: int, momentum: float, poss_diff: float) -> dict:
        if self._m is None:
            return self._fallback(minute, score_diff)
        x = winprob_vector(minute, score_diff, xg_diff, shots_diff, momentum, poss_diff)
        z = self._standardise(x)
        logits = [b + sum(c * zi for c, zi in zip(row, z))
                  for row, b in zip(self._m["coef"], self._m["intercept"])]
        probs = softmax(logits)
        out = dict(zip(self._m["classes"], probs))
        return {
            "home": round(out.get("home", 0.0), 3),
            "draw": round(out.get("draw", 0.0), 3),
            "away": round(out.get("away", 0.0), 3),
        }

    def _standardise(self, x: list[float]) -> list[float]:
        mean, scale = self._m["mean"], self._m["scale"]
        return [(xi - m) / (s or 1.0) for xi, m, s in zip(x, mean, scale)]

    @staticmethod
    def _fallback(minute: float, score_diff: int) -> dict:
        # Crude time-decayed score heuristic; only used if no artifact.
        weight = 0.3 + 0.7 * min(1.0, minute / 90.0)
        edge = max(-1.0, min(1.0, score_diff * weight))
        home = 0.4 + 0.5 * edge
        away = 0.4 - 0.5 * edge
        draw = max(0.05, 1.0 - home - away)
        tot = home + draw + away
        return {"home": round(home / tot, 3), "draw": round(draw / tot, 3),
                "away": round(away / tot, 3)}


_MODEL: WinProbModel | None = None


def get_winprob_model() -> WinProbModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = WinProbModel()
    return _MODEL
