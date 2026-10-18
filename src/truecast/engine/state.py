"""Live match state built incrementally from the event stream.

`MatchState.apply(event)` is the single ingest point: every event updates
team tallies, per-player stats, possession time and the rolling indices.
A `snapshot()` is a complete, JSON-safe picture of the match at that instant,
which is what the agents and the UI consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Event, MatchMeta
from ..ml.winprob import get_winprob_model
from ..ml.xgmodel import get_xg_model
from .indices import IndexEngine
from .metrics import shot_geometry


def abs_time(period: int, clock_s: float) -> float:
    return (period - 1) * 45 * 60 + clock_s


@dataclass
class TeamStats:
    goals: int = 0
    shots: int = 0
    shots_on_target: int = 0
    xg: float = 0.0
    passes: int = 0
    passes_completed: int = 0
    tackles_won: int = 0
    interceptions: int = 0
    possession_s: float = 0.0

    @property
    def pass_accuracy(self) -> float:
        return round(100 * self.passes_completed / self.passes, 1) if self.passes else 0.0


@dataclass
class PlayerStats:
    player_id: str
    name: str
    team_id: str
    position: str
    distance_m: float = 0.0
    top_speed_ms: float = 0.0
    passes: int = 0
    passes_completed: int = 0
    shots: int = 0
    goals: int = 0

    @property
    def pass_accuracy(self) -> float:
        return round(100 * self.passes_completed / self.passes, 1) if self.passes else 0.0


class MatchState:
    def __init__(self, meta: MatchMeta) -> None:
        self.meta = meta
        self.home_id = meta.home.team_id
        self.away_id = meta.away.team_id
        self.teams: dict[str, TeamStats] = {self.home_id: TeamStats(), self.away_id: TeamStats()}
        self.players: dict[str, PlayerStats] = {}
        for t in (meta.home, meta.away):
            for p in t.players:
                self.players[p.player_id] = PlayerStats(p.player_id, p.name, t.team_id, p.position)
        self.idx = IndexEngine(self.home_id, self.away_id)
        self.period = 1
        self.clock_s = 0.0
        self._last_abs: float | None = None
        self._possessor: str | None = None
        self.last_event: Event | None = None
        # Shot map + per-shot model xG (keyed by shot event id).
        self.shots: list[dict] = []
        self._shot_xg: dict[str, float] = {}
        # Off-ball running: a steady baseline so players reach realistic
        # season-like distances (~10-11 km) on top of on-ball movement.
        import random as _r
        _rng = _r.Random(meta.seed + 1)
        self._baseline_speed: dict[str, float] = {}
        for p in self.players.values():
            self._baseline_speed[p.player_id] = 0.5 if p.position == "GK" \
                else _rng.uniform(1.75, 2.05)

    # -- ingest ----------------------------------------------------------
    def apply(self, ev: Event) -> None:
        self.period = ev.period
        self.clock_s = ev.clock_s
        now = abs_time(ev.period, ev.clock_s)

        # Possession time: credit elapsed wall-of-play to the last possessor.
        if self._last_abs is not None:
            delta = max(0.0, now - self._last_abs)
            if delta < 60:  # ignore stoppages/celebrations
                if self._possessor is not None:
                    self.teams[self._possessor].possession_s += delta
                for p in self.players.values():
                    p.distance_m += self._baseline_speed[p.player_id] * delta
        self._last_abs = now
        if ev.team_id in self.teams and ev.type in ("pass", "carry", "kickoff", "shot"):
            self._possessor = ev.team_id

        ts = self.teams.get(ev.team_id)
        ps = self.players.get(ev.player_id) if ev.player_id else None

        if ev.type == "pass" and ts:
            ts.passes += 1
            if ps:
                ps.passes += 1
            if ev.outcome == "complete":
                ts.passes_completed += 1
                if ps:
                    ps.passes_completed += 1
            if ps and ev.end_x is not None:
                ps.distance_m += 0.4 * ev.detail.get("length_m", 0.0)
        elif ev.type == "carry" and ps:
            ps.distance_m += ev.detail.get("distance_m", 0.0)
            ps.top_speed_ms = max(ps.top_speed_ms, ev.detail.get("speed_ms", 0.0))
        elif ev.type == "shot" and ts:
            # Displayed/narrated xG comes from the trained model, estimated from
            # the shot's features (the generator's own value only drove whether
            # the goal was scored at generation time).
            mxg = self._model_xg(ev)
            ev.detail["xg"] = mxg
            self._shot_xg[ev.event_id] = mxg
            ts.shots += 1
            ts.xg = round(ts.xg + mxg, 3)
            if ev.outcome == "on_target":
                ts.shots_on_target += 1
            if ps:
                ps.shots += 1
            self.shots.append({
                "event_id": ev.event_id, "team": ev.team_id,
                "x": ev.x, "y": ev.y, "xg": mxg,
                "on_target": ev.outcome == "on_target", "goal": False,
            })
        elif ev.type == "goal" and ts:
            ts.goals += 1
            if ps:
                ps.goals += 1
            se = ev.detail.get("shot_event")
            if se in self._shot_xg:
                ev.detail["xg"] = self._shot_xg[se]
                for s in self.shots:
                    if s["event_id"] == se:
                        s["goal"] = True
                        break
        elif ev.type == "tackle" and ts and ev.outcome == "won":
            ts.tackles_won += 1
        elif ev.type == "interception" and ts:
            ts.interceptions += 1
            self._possessor = ev.team_id

        self.idx.update(ev, now)
        self.last_event = ev

    def _model_xg(self, ev: Event) -> float:
        dist, angle = shot_geometry(ev.x or 0.0, ev.y or 34.0)
        d = ev.detail
        return get_xg_model().predict(
            dist, angle,
            is_header=d.get("body_part") == "head",
            big_chance=bool(d.get("big_chance")),
            under_pressure=bool(d.get("under_pressure")),
        )

    def win_prob(self) -> dict:
        h = self.teams[self.home_id]
        a = self.teams[self.away_id]
        poss = self.possession_pct()
        minute = (self.period - 1) * 45 + self.clock_s / 60.0
        return get_winprob_model().predict(
            minute=minute,
            score_diff=h.goals - a.goals,
            xg_diff=round(h.xg - a.xg, 3),
            shots_diff=h.shots - a.shots,
            momentum=self.idx.momentum(),
            poss_diff=poss.get(self.home_id, 50) - poss.get(self.away_id, 50),
        )

    # -- read ------------------------------------------------------------
    def score(self) -> tuple[int, int]:
        return self.teams[self.home_id].goals, self.teams[self.away_id].goals

    def possession_pct(self) -> dict[str, int]:
        total = sum(t.possession_s for t in self.teams.values()) or 1.0
        return {tid: round(100 * t.possession_s / total) for tid, t in self.teams.items()}

    def top_player(self, metric: str, team_id: str | None = None) -> PlayerStats | None:
        pool = [p for p in self.players.values() if team_id is None or p.team_id == team_id]
        if not pool:
            return None
        return max(pool, key=lambda p: getattr(p, metric, 0))

    def clock_label(self) -> str:
        base = 0 if self.period == 1 else 45
        total = base * 60 + self.clock_s
        return f"{int(total // 60):02d}:{int(total % 60):02d}"

    def snapshot(self) -> dict:
        hp = self.possession_pct()
        return {
            "clock": self.clock_label(),
            "period": self.period,
            "score": {self.home_id: self.teams[self.home_id].goals,
                      self.away_id: self.teams[self.away_id].goals},
            "possession": hp,
            "teams": {
                tid: {
                    "shots": t.shots, "shots_on_target": t.shots_on_target,
                    "xg": round(t.xg, 2), "passes": t.passes,
                    "pass_accuracy": t.pass_accuracy,
                    "tackles_won": t.tackles_won, "interceptions": t.interceptions,
                }
                for tid, t in self.teams.items()
            },
            "indices": self.idx.snapshot(),
            "win_prob": self.win_prob(),
            "shots": self.shots,
        }
