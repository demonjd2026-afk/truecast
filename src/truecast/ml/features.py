"""Feature specifications shared by training and runtime inference.

Keeping the feature order and construction in one place guarantees the live
service builds inputs exactly as the models were trained on.
"""

from __future__ import annotations

import math

# Live win-probability model (home-team perspective).
WINPROB_FEATURES = ["minute", "score_diff", "xg_diff", "shots_diff", "momentum", "poss_diff"]


def winprob_vector(minute: float, score_diff: int, xg_diff: float,
                   shots_diff: int, momentum: float, poss_diff: float) -> list[float]:
    return [float(minute), float(score_diff), float(xg_diff),
            float(shots_diff), float(momentum), float(poss_diff)]


# Shot xG model.
XG_FEATURES = ["distance", "angle", "is_header", "big_chance", "under_pressure"]


def xg_vector(distance_m: float, angle_rad: float, is_header: bool,
              big_chance: bool, under_pressure: bool) -> list[float]:
    return [float(distance_m), float(angle_rad), 1.0 if is_header else 0.0,
            1.0 if big_chance else 0.0, 1.0 if under_pressure else 0.0]


def softmax(logits: list[float]) -> list[float]:
    m = max(logits)
    exps = [math.exp(v - m) for v in logits]
    s = sum(exps) or 1.0
    return [e / s for e in exps]


def sigmoid(z: float) -> float:
    if z < 0:
        e = math.exp(z)
        return e / (1.0 + e)
    return 1.0 / (1.0 + math.exp(-z))
