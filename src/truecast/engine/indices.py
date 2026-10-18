"""Explainability indices computed over a rolling window of events.

These are the numbers that let the system say *why* a phase of play matters
rather than only what happened:

* momentum        - which team the game is flowing toward right now (-1..1,
                    positive = home).
* control         - how controlled each team's play is (completed build-up
                    vs turnovers); the inverse, aggregated, is "chaos".
* pressure        - defensive pressure intensity each team is applying.
* tempo           - game rhythm, in on-ball actions per minute.

All are derived purely from the event window, so every index value can be
traced back to the events that produced it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from ..models import Event

# How much each event nudges momentum toward the acting team.
_MOMENTUM_WEIGHT = {
    "goal": 6.0,
    "shot": 3.0,
    "save": 1.5,          # credited to defending team (the saver's team)
    "interception": 1.2,
    "tackle": 1.0,
    "carry": 0.4,
    "pass": 0.3,
    "pressure": 0.6,
}

WINDOW_SECONDS = 150.0


@dataclass
class _Window:
    events: deque = field(default_factory=deque)

    def add(self, ev: Event, now: float) -> None:
        self.events.append((now, ev))
        cutoff = now - WINDOW_SECONDS
        while self.events and self.events[0][0] < cutoff:
            self.events.popleft()


class IndexEngine:
    def __init__(self, home_id: str, away_id: str) -> None:
        self.home_id = home_id
        self.away_id = away_id
        self._win = _Window()

    def update(self, ev: Event, abs_time: float) -> None:
        self._win.add(ev, abs_time)

    # -- indices ---------------------------------------------------------
    def momentum(self) -> float:
        net = 0.0
        total = 0.0
        for _, ev in self._win.events:
            w = _MOMENTUM_WEIGHT.get(ev.type, 0.0)
            if w == 0.0:
                continue
            # Only reward passes/carries made in the attacking half.
            if ev.type in ("pass", "carry") and (ev.x or 0) < 55:
                w *= 0.4
            total += w
            sign = 1.0 if ev.team_id == self.home_id else -1.0
            net += sign * w
        if total == 0:
            return 0.0
        return round(max(-1.0, min(1.0, net / total)), 3)

    def control(self) -> dict[str, float]:
        """Per-team control score in 0..1 over the window."""
        out = {}
        for tid in (self.home_id, self.away_id):
            good = bad = 0.0
            for _, ev in self._win.events:
                if ev.team_id != tid:
                    continue
                if ev.type == "pass":
                    if ev.outcome == "complete":
                        good += 1
                    else:
                        bad += 1.5
                elif ev.type == "carry":
                    good += 0.8
            # Turnovers conceded to the opponent count as chaos against tid.
            for _, ev in self._win.events:
                if ev.team_id == tid:
                    continue
                if ev.type in ("interception", "tackle") and ev.outcome == "won":
                    bad += 1.0
            denom = good + bad
            out[tid] = round(good / denom, 3) if denom else 0.5
        return out

    def chaos(self) -> float:
        """Match-level chaos: turnovers per minute in the window, 0..1."""
        turnovers = sum(
            1 for _, ev in self._win.events
            if ev.type in ("interception", "tackle", "possession_change")
            or (ev.type == "pass" and ev.outcome == "incomplete")
        )
        span = min(WINDOW_SECONDS, max(30.0, self._window_span()))
        per_min = turnovers / (span / 60.0)
        return round(min(1.0, per_min / 12.0), 3)

    def pressure(self) -> dict[str, float]:
        out = {self.home_id: 0.0, self.away_id: 0.0}
        for _, ev in self._win.events:
            if ev.type == "pressure":
                out[ev.team_id] = out.get(ev.team_id, 0.0) + ev.detail.get("intensity", 0.5)
        span = max(1.0, self._window_span() / 60.0)
        return {k: round(v / span, 2) for k, v in out.items()}

    def tempo(self) -> float:
        on_ball = sum(
            1 for _, ev in self._win.events if ev.type in ("pass", "carry", "shot")
        )
        span = max(0.5, self._window_span() / 60.0)
        return round(on_ball / span, 1)

    def _window_span(self) -> float:
        if len(self._win.events) < 2:
            return 30.0
        return self._win.events[-1][0] - self._win.events[0][0]

    def snapshot(self) -> dict:
        ctrl = self.control()
        pres = self.pressure()
        return {
            "momentum": self.momentum(),
            "chaos": self.chaos(),
            "tempo": self.tempo(),
            "control": ctrl,
            "pressure": pres,
        }
