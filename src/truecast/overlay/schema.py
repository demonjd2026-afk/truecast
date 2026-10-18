"""Overlay packet: the machine-readable output a rendering partner consumes.

Each aired moment produces one overlay packet — timed, typed, and carrying
the evidence that backs it — so it can be dropped onto a live feed as a
synchronised graphic. The persona variants travel inside the packet, letting
the rendering layer pick the line for each viewer's chosen experience.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# How an overlay should be shown; a rendering partner maps these to templates.
TEMPLATE_BY_KIND = {
    "goal": "lower_third_goal",
    "big_chance": "stat_flash",
    "shot": "stat_flash",
    "save": "stat_flash",
    "momentum_shift": "momentum_bar",
    "control_spell": "momentum_bar",
    "pressure_build": "momentum_bar",
    "milestone": "player_card",
}


@dataclass
class OverlayPacket:
    overlay_id: str
    match_id: str
    clock: str
    period: int
    kind: str
    template: str
    priority: float
    duration_s: float
    headline: str                       # persona-neutral on-screen headline
    variants: dict[str, str]            # persona key -> line
    data: dict[str, Any]
    evidence: list[str]                 # event ids backing this overlay
    verified: bool

    def to_dict(self) -> dict:
        return asdict(self)


def duration_for(kind: str, priority: float) -> float:
    base = {"goal": 8.0}.get(kind, 5.0)
    return round(base + 2.0 * priority, 1)


def headline_for(fact_kind: str, data: dict) -> str:
    if fact_kind == "goal":
        return f"GOAL — {data.get('scorer','')}"
    if fact_kind in ("big_chance", "shot"):
        return f"Chance — {data.get('shooter','')} ({data.get('xg','')} xG)"
    if fact_kind == "save":
        return f"Save — {data.get('keeper','')}"
    if fact_kind == "momentum_shift":
        return f"Momentum — {data.get('team','')}"
    if fact_kind == "control_spell":
        return f"In control — {data.get('team','')}"
    if fact_kind == "pressure_build":
        return f"Pressing — {data.get('team','')}"
    if fact_kind == "milestone":
        return f"Milestone — {data.get('player','')}"
    return fact_kind
