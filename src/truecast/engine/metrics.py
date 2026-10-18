"""Stateless football metrics used by the engine and the generator.

Kept separate so the numbers that appear in narratives (xG, pass
difficulty, speeds) are computed in exactly one place and can be unit
tested on their own.
"""

from __future__ import annotations

import math

from ..models import GOAL_X, GOAL_Y, GOAL_WIDTH

HALF_POST = GOAL_WIDTH / 2.0


def shot_geometry(x: float, y: float) -> tuple[float, float]:
    dist = math.hypot(GOAL_X - x, GOAL_Y - y)
    v1 = (GOAL_X - x, (GOAL_Y - HALF_POST) - y)
    v2 = (GOAL_X - x, (GOAL_Y + HALF_POST) - y)
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    m1 = math.hypot(*v1) or 1e-6
    m2 = math.hypot(*v2) or 1e-6
    cos_a = max(-1.0, min(1.0, dot / (m1 * m2)))
    return dist, math.acos(cos_a)


def pass_difficulty(length_m: float, zone: float, under_pressure: bool) -> float:
    d = 0.03 * length_m + 0.35 * zone + (0.25 if under_pressure else 0.0)
    return round(max(0.0, min(1.0, d)), 2)


def kmh(ms: float) -> float:
    return round(ms * 3.6, 1)
