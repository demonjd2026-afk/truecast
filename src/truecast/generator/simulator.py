"""Possession-based synthetic match simulator.

The simulator walks a match possession by possession. Within a possession a
team strings together passes and carries that tend to advance toward the
opponent goal; the defending team applies pressure and occasionally wins the
ball back through tackles or interceptions. When play reaches the final third
a shot may follow, with its quality (xG) derived from the shot geometry.

Coordinates are stored in the possessing team's attacking frame: x runs from
0 (own goal line) to 105 (opponent goal line), so distance and angle to goal
are always measured against x = 105. This matches how real event feeds
normalise direction and keeps the downstream metrics direction-independent.

Everything is seeded, so a given seed reproduces the same match exactly.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone

from ..models import (
    GOAL_WIDTH,
    GOAL_X,
    GOAL_Y,
    PITCH_LENGTH,
    PITCH_WIDTH,
    Event,
    EventType,
    MatchMeta,
    Player,
    Team,
)
from .entities import build_teams

PERIOD_SECONDS = 45 * 60
HALF_POST = GOAL_WIDTH / 2.0


def shot_geometry(x: float, y: float) -> tuple[float, float]:
    """Return (distance_m, open_angle_rad) of the goal mouth from (x, y)."""
    dist = math.hypot(GOAL_X - x, GOAL_Y - y)
    # Angle subtended by the two posts at the shot location.
    p1 = (GOAL_X, GOAL_Y - HALF_POST)
    p2 = (GOAL_X, GOAL_Y + HALF_POST)
    v1 = (p1[0] - x, p1[1] - y)
    v2 = (p2[0] - x, p2[1] - y)
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    m1 = math.hypot(*v1) or 1e-6
    m2 = math.hypot(*v2) or 1e-6
    cos_a = max(-1.0, min(1.0, dot / (m1 * m2)))
    return dist, math.acos(cos_a)


def expected_goals(x: float, y: float, body_part: str, big_chance: bool) -> float:
    """Logistic xG from shot geometry, tuned to realistic ranges."""
    dist, angle = shot_geometry(x, y)
    log_odds = -0.62 + 2.6 * angle - 0.10 * dist
    if body_part == "head":
        log_odds -= 0.65
    if big_chance:
        log_odds += 1.1
    xg = 1.0 / (1.0 + math.exp(-log_odds))
    return round(max(0.01, min(0.97, xg)), 3)


class _Clock:
    def __init__(self) -> None:
        self.period = 1
        self.t = 0.0

    def tick(self, seconds: float) -> None:
        self.t += seconds

    def expired(self) -> bool:
        return self.t >= PERIOD_SECONDS


class MatchSimulator:
    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.home, self.away = build_teams(self.rng)
        # Mild, fixed quality asymmetry so matches have a shape.
        self.strength = {
            self.home.team_id: 1.0 + self.rng.uniform(-0.12, 0.12),
            self.away.team_id: 1.0 + self.rng.uniform(-0.12, 0.12),
        }
        self.match_id = f"m_{seed:04d}"
        self._seq = 0
        self._eid = 0
        self.events: list[Event] = []
        self.score = {self.home.team_id: 0, self.away.team_id: 0}
        self.distance: dict[str, float] = {}

    # -- helpers ---------------------------------------------------------
    def _next_ids(self) -> tuple[str, int]:
        self._eid += 1
        self._seq += 1
        return f"e{self._eid:05d}", self._seq

    def _emit(self, clock: _Clock, **kw) -> Event:
        eid, seq = self._next_ids()
        ev = Event(
            event_id=eid,
            match_id=self.match_id,
            sequence=seq,
            period=clock.period,
            clock_s=round(clock.t, 1),
            **kw,
        )
        self.events.append(ev)
        return ev

    def _team(self, tid: str) -> Team:
        return self.home if tid == self.home.team_id else self.away

    def _pick(self, team: Team, zone: float) -> Player:
        """Pick a plausible player given how advanced play is (0..1)."""
        if zone < 0.33:
            pool = [p for p in team.players if p.position in ("GK", "DEF")]
        elif zone < 0.66:
            pool = [p for p in team.players if p.position in ("DEF", "MID")]
        else:
            pool = [p for p in team.players if p.position in ("MID", "FWD")]
        return self.rng.choice(pool or team.players)

    def _accrue(self, player: Player, metres: float) -> None:
        self.distance[player.player_id] = self.distance.get(player.player_id, 0.0) + metres

    # -- possession ------------------------------------------------------
    def _possession(self, clock: _Clock, attacking: str) -> str:
        """Simulate one possession; return the team that has the ball next."""
        atk = self._team(attacking)
        defending = self.away.team_id if attacking == self.home.team_id else self.home.team_id
        deff = self._team(defending)
        s_atk = self.strength[attacking]

        x = self.rng.uniform(18.0, 42.0)
        y = self.rng.uniform(14.0, PITCH_WIDTH - 14.0)
        carrier = self._pick(atk, x / PITCH_LENGTH)

        for _ in range(self.rng.randint(2, 9)):
            if clock.expired():
                return attacking
            zone = x / PITCH_LENGTH
            under_pressure = self.rng.random() < 0.22 + 0.25 * zone

            if under_pressure:
                presser = self._pick(deff, 1.0 - zone)
                self._emit(
                    clock,
                    type=EventType.PRESSURE,
                    team_id=defending,
                    player_id=presser.player_id,
                    x=round(PITCH_LENGTH - x, 1),
                    y=round(PITCH_WIDTH - y, 1),
                    detail={"intensity": round(self.rng.uniform(0.4, 1.0), 2)},
                )
                clock.tick(self.rng.uniform(0.5, 1.5))

            # Shot opportunity in the final third.
            if zone > 0.72 and self.rng.random() < 0.28 + 0.2 * (zone - 0.72):
                nxt = self._take_shot(clock, atk, deff, carrier, x, y, under_pressure)
                return nxt

            # Otherwise pass or carry.
            if self.rng.random() < 0.72:
                nxt = self._attempt_pass(clock, atk, deff, carrier, x, y, zone, under_pressure, s_atk)
            else:
                nxt = self._carry(clock, atk, deff, carrier, x, y, zone, under_pressure)

            if nxt is None:
                return defending  # turnover
            carrier, x, y = nxt

        return defending  # possession fizzles out

    @staticmethod
    def _pass_difficulty(length: float, zone: float, pressure: bool) -> float:
        """0 (simple) .. 1 (very hard), from distance, area and pressure."""
        d = 0.03 * length + 0.35 * zone + (0.25 if pressure else 0.0)
        return round(max(0.0, min(1.0, d)), 2)

    def _attempt_pass(self, clock, atk, deff, carrier, x, y, zone, pressure, strength):
        receiver = self._pick(atk, min(1.0, zone + self.rng.uniform(0.0, 0.25)))
        gain = self.rng.uniform(4.0, 22.0) * (1.1 if not pressure else 0.8)
        ex = min(PITCH_LENGTH - 1.0, x + gain)
        ey = min(PITCH_WIDTH - 2.0, max(2.0, y + self.rng.uniform(-18.0, 18.0)))
        length = math.hypot(ex - x, ey - y)
        difficulty = self._pass_difficulty(length, zone, pressure)
        base = 0.90 - 0.45 * difficulty
        completed = self.rng.random() < max(0.25, base * (0.9 + 0.2 * strength))
        ball_speed = round(self.rng.uniform(12.0, 18.0) + length * 0.25, 1)
        self._accrue(carrier, length * 0.4)
        self._emit(
            clock,
            type=EventType.PASS,
            team_id=atk.team_id,
            player_id=carrier.player_id,
            receiver_id=receiver.player_id if completed else None,
            x=round(x, 1), y=round(y, 1),
            end_x=round(ex, 1), end_y=round(ey, 1),
            outcome="complete" if completed else "incomplete",
            detail={
                "length_m": round(length, 1),
                "difficulty": difficulty,
                "under_pressure": pressure,
                "ball_speed_ms": ball_speed,
            },
        )
        clock.tick(self.rng.uniform(1.6, 3.8))
        if completed:
            return receiver, ex, ey
        # Incomplete: defending team may intercept cleanly.
        if self.rng.random() < 0.5:
            picker = self._pick(deff, 1.0 - zone)
            self._emit(
                clock, type=EventType.INTERCEPTION, team_id=deff.team_id,
                player_id=picker.player_id,
                x=round(PITCH_LENGTH - ex, 1), y=round(PITCH_WIDTH - ey, 1),
                outcome="won",
            )
            clock.tick(self.rng.uniform(0.8, 1.6))
        return None

    def _carry(self, clock, atk, deff, carrier, x, y, zone, pressure):
        gain = self.rng.uniform(3.0, 14.0) * (0.7 if pressure else 1.0)
        ex = min(PITCH_LENGTH - 1.0, x + gain)
        ey = min(PITCH_WIDTH - 2.0, max(2.0, y + self.rng.uniform(-6.0, 6.0)))
        dist = math.hypot(ex - x, ey - y)
        self._accrue(carrier, dist)
        speed = round(self.rng.uniform(4.5, 8.6), 1)
        self._emit(
            clock, type=EventType.CARRY, team_id=atk.team_id, player_id=carrier.player_id,
            x=round(x, 1), y=round(y, 1), end_x=round(ex, 1), end_y=round(ey, 1),
            outcome="complete",
            detail={"distance_m": round(dist, 1), "speed_ms": speed, "under_pressure": pressure},
        )
        clock.tick(self.rng.uniform(1.2, 3.0))
        # A carry under pressure can be tackled.
        if pressure and self.rng.random() < 0.3:
            tackler = self._pick(deff, 1.0 - zone)
            won = self.rng.random() < 0.6
            self._emit(
                clock, type=EventType.TACKLE, team_id=deff.team_id, player_id=tackler.player_id,
                x=round(PITCH_LENGTH - ex, 1), y=round(PITCH_WIDTH - ey, 1),
                outcome="won" if won else "lost",
            )
            clock.tick(self.rng.uniform(0.8, 1.8))
            if won:
                return None
        return carrier, ex, ey

    def _take_shot(self, clock, atk, deff, carrier, x, y, pressure):
        shooter = self._pick(atk, 1.0)
        body = "head" if self.rng.random() < 0.18 else "foot"
        big_chance = (not pressure) and x > 92 and abs(y - GOAL_Y) < 10 and self.rng.random() < 0.5
        xg = expected_goals(x, y, body, big_chance)
        shot_speed = round(self.rng.uniform(18.0, 33.0), 1)
        on_target_p = 0.35 + 0.4 * xg
        on_target = self.rng.random() < on_target_p
        blocked = (not on_target) and self.rng.random() < 0.3
        outcome = "on_target" if on_target else ("blocked" if blocked else "off_target")
        shot_ev = self._emit(
            clock, type=EventType.SHOT, team_id=atk.team_id, player_id=shooter.player_id,
            x=round(x, 1), y=round(y, 1), outcome=outcome,
            detail={
                "xg": xg, "body_part": body, "shot_speed_ms": shot_speed,
                "big_chance": big_chance, "under_pressure": pressure,
                "distance_m": round(shot_geometry(x, y)[0], 1),
            },
        )
        clock.tick(self.rng.uniform(1.0, 1.8))

        if on_target:
            keeper = next((p for p in deff.players if p.position == "GK"), deff.players[0])
            # Convert so that overall conversion ≈ xG: P(goal) = P(on_target)·P(goal|on_target).
            goal_given_on_target = min(0.95, xg / max(0.2, on_target_p))
            scored = self.rng.random() < goal_given_on_target
            if scored:
                self.score[atk.team_id] += 1
                self._emit(
                    clock, type=EventType.GOAL, team_id=atk.team_id, player_id=shooter.player_id,
                    x=round(x, 1), y=round(y, 1),
                    detail={
                        "xg": xg, "shot_event": shot_ev.event_id,
                        "score_home": self.score[self.home.team_id],
                        "score_away": self.score[self.away.team_id],
                    },
                )
                clock.tick(self.rng.uniform(25.0, 45.0))  # celebration + restart
                return self.home.team_id if atk.team_id == self.away.team_id else self.away.team_id
            # Saved.
            self._emit(
                clock, type=EventType.SAVE, team_id=deff.team_id, player_id=keeper.player_id,
                x=round(PITCH_LENGTH - x, 1), y=round(PITCH_WIDTH - y, 1), outcome="won",
                detail={"shot_event": shot_ev.event_id},
            )
            clock.tick(self.rng.uniform(2.0, 4.0))
        return deff.team_id

    # -- driver ----------------------------------------------------------
    def run(self) -> tuple[MatchMeta, list[Event]]:
        meta = MatchMeta(
            match_id=self.match_id,
            competition="Synthetic Premier Series",
            home=self.home,
            away=self.away,
            venue=f"{self.home.name} Stadium",
            kickoff_iso=datetime.now(timezone.utc).isoformat(),
            seed=self.seed,
        )
        for period in (1, 2):
            clock = _Clock()
            clock.period = period
            attacking = self.home.team_id if period == 1 else self.away.team_id
            self._emit(clock, type=EventType.KICKOFF, team_id=attacking)
            clock.tick(1.0)
            while not clock.expired():
                attacking = self._possession(clock, attacking)
            self._emit(
                clock, type=EventType.PERIOD_END, team_id=attacking,
                detail={"period": period,
                        "score_home": self.score[self.home.team_id],
                        "score_away": self.score[self.away.team_id]},
            )
        return meta, self.events


def generate_match(seed: int = 7) -> tuple[MatchMeta, list[Event]]:
    return MatchSimulator(seed).run()
