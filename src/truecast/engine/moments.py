"""Moment detection: turn the event stream into verifiable Facts.

A Fact is a neutral, machine-checkable statement with the event ids that
justify it. Downstream, agents may only speak about Facts, and the Verifier
confirms each narrative line against the Fact's evidence. This is what keeps
on-screen narratives grounded: nothing is said that the event log cannot back.

The detector holds light cooldown state so it surfaces the moments that
matter without flooding the feed with every pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Event, Fact
from .state import MatchState

_PASS_MILESTONES = (50, 75)
_DIST_MILESTONES_KM = (10.0,)


@dataclass
class MomentDetector:
    state: MatchState
    _fact_no: int = 0
    _last_momentum_fact: float = -999.0
    _last_control_fact: float = -999.0
    _last_pressure_fact: float = -999.0
    _pass_done: set = field(default_factory=set)
    _dist_done: set = field(default_factory=set)
    _dist_leader_done: bool = False
    _prev_momentum: float = 0.0

    def _fid(self) -> str:
        self._fact_no += 1
        return f"f{self._fact_no:04d}"

    def _name(self, pid: str | None) -> str:
        if pid and pid in self.state.players:
            return self.state.players[pid].name
        return "a player"

    def _team_name(self, tid: str) -> str:
        return self.state.meta.team(tid).name

    def observe(self, ev: Event) -> list[Fact]:
        """Return any Facts triggered by this event (state already updated)."""
        facts: list[Fact] = []
        now = (ev.period - 1) * 45 * 60 + ev.clock_s
        clk = ev.clock_label

        if ev.type == "goal":
            facts.append(self._goal_fact(ev, clk))
        elif ev.type == "shot":
            f = self._shot_fact(ev, clk)
            if f:
                facts.append(f)
        elif ev.type == "save":
            facts.append(self._save_fact(ev, clk))

        # Index-driven moments (checked on substantive on-ball events).
        if ev.type in ("pass", "carry", "shot", "goal", "interception", "tackle"):
            facts += self._index_facts(ev, now, clk)
            facts += self._milestone_facts(ev, clk)

        self._prev_momentum = self.state.idx.momentum()
        return facts

    # -- individual detectors -------------------------------------------
    def _goal_fact(self, ev: Event, clk: str) -> Fact:
        h, a = self.state.score()
        scorer = self._name(ev.player_id)
        team = self._team_name(ev.team_id)
        xg = ev.detail.get("xg", 0.0)
        evidence = [ev.event_id]
        if ev.detail.get("shot_event"):
            evidence.append(ev.detail["shot_event"])
        return Fact(
            fact_id=self._fid(), kind="goal", subject_team=ev.team_id,
            subject_player=ev.player_id, clock_label=clk,
            text=f"{scorer} scored for {team} at {clk}; score {h}-{a}. Shot xG was {xg}.",
            evidence=evidence,
            data={"scorer": scorer, "team": team, "score_home": h, "score_away": a, "xg": xg},
            importance=0.98,
        )

    def _shot_fact(self, ev: Event, clk: str) -> Fact | None:
        xg = ev.detail.get("xg", 0.0)
        big = xg >= 0.30 or ev.detail.get("big_chance")
        if not big and ev.outcome == "off_target":
            return None  # skip routine off-target efforts
        shooter = self._name(ev.player_id)
        team = self._team_name(ev.team_id)
        kind = "big_chance" if big else "shot"
        outcome_txt = {"on_target": "on target", "off_target": "off target",
                       "blocked": "blocked"}.get(ev.outcome or "", ev.outcome or "")
        imp = 0.72 if big else 0.34
        return Fact(
            fact_id=self._fid(), kind=kind, subject_team=ev.team_id,
            subject_player=ev.player_id, clock_label=clk,
            text=f"{shooter} ({team}) had a shot {outcome_txt} at {clk}, xG {xg}.",
            evidence=[ev.event_id],
            data={"shooter": shooter, "team": team, "xg": xg, "outcome": ev.outcome,
                  "distance_m": ev.detail.get("distance_m")},
            importance=imp,
        )

    def _save_fact(self, ev: Event, clk: str) -> Fact:
        keeper = self._name(ev.player_id)
        team = self._team_name(ev.team_id)
        return Fact(
            fact_id=self._fid(), kind="save", subject_team=ev.team_id,
            subject_player=ev.player_id, clock_label=clk,
            text=f"{keeper} ({team}) made a save at {clk}.",
            evidence=[ev.event_id],
            data={"keeper": keeper, "team": team},
            importance=0.5,
        )

    def _index_facts(self, ev: Event, now: float, clk: str) -> list[Fact]:
        out: list[Fact] = []
        # Need a settled window before trusting index-based moments.
        if len(self.state.idx._win.events) < 18 or now < 90:
            return out
        snap = self.state.idx.snapshot()
        mom = snap["momentum"]
        # Momentum shift: strong flow that has grown since last check.
        if abs(mom) >= 0.4 and abs(mom) - abs(self._prev_momentum) >= 0.10 \
                and now - self._last_momentum_fact > 120:
            tid = self.state.home_id if mom > 0 else self.state.away_id
            team = self._team_name(tid)
            self._last_momentum_fact = now
            out.append(Fact(
                fact_id=self._fid(), kind="momentum_shift", subject_team=tid,
                subject_player=None, clock_label=clk,
                text=f"Momentum has swung toward {team} around {clk} "
                     f"(momentum index {mom:+.2f}).",
                evidence=self._recent_ids(tid, 6),
                data={"team": team, "momentum": mom, "tempo": snap["tempo"]},
                importance=0.55,
            ))
        # Control spell.
        ctrl = snap["control"]
        for tid, c in ctrl.items():
            if c >= 0.78 and now - self._last_control_fact > 150:
                team = self._team_name(tid)
                self._last_control_fact = now
                out.append(Fact(
                    fact_id=self._fid(), kind="control_spell", subject_team=tid,
                    subject_player=None, clock_label=clk,
                    text=f"{team} are controlling this phase at {clk} "
                         f"(control {int(c*100)}%, chaos {snap['chaos']:.2f}).",
                    evidence=self._recent_ids(tid, 6),
                    data={"team": team, "control": c, "chaos": snap["chaos"]},
                    importance=0.42,
                ))
                break
        # Pressure build.
        pres = snap["pressure"]
        for tid, p in pres.items():
            if p >= 6.0 and now - self._last_pressure_fact > 150:
                team = self._team_name(tid)
                self._last_pressure_fact = now
                out.append(Fact(
                    fact_id=self._fid(), kind="pressure_build", subject_team=tid,
                    subject_player=None, clock_label=clk,
                    text=f"{team} are pressing hard at {clk} "
                         f"(pressure index {p:.1f} per min).",
                    evidence=self._recent_ids(tid, 5, kind="pressure"),
                    data={"team": team, "pressure": p},
                    importance=0.38,
                ))
                break
        return out

    def _milestone_facts(self, ev: Event, clk: str) -> list[Fact]:
        out: list[Fact] = []
        if not ev.player_id or ev.player_id not in self.state.players:
            return out
        ps = self.state.players[ev.player_id]
        for m in _PASS_MILESTONES:
            key = (ps.player_id, "pass", m)
            if ps.passes_completed >= m and key not in self._pass_done:
                self._pass_done.add(key)
                out.append(Fact(
                    fact_id=self._fid(), kind="milestone", subject_team=ps.team_id,
                    subject_player=ps.player_id, clock_label=clk,
                    text=f"{ps.name} has completed {m} passes by {clk} "
                         f"({ps.pass_accuracy}% accuracy).",
                    evidence=self._recent_ids(ps.team_id, 4, player=ps.player_id),
                    data={"player": ps.name, "passes": m, "accuracy": ps.pass_accuracy},
                    importance=0.33,
                ))
        # Distance milestone fires once per match, for whoever reaches it
        # first — a genuine talking point rather than a line per player.
        km = ps.distance_m / 1000.0
        if not self._dist_leader_done and km >= _DIST_MILESTONES_KM[0]:
            self._dist_leader_done = True
            m = _DIST_MILESTONES_KM[0]
            out.append(Fact(
                fact_id=self._fid(), kind="milestone", subject_team=ps.team_id,
                subject_player=ps.player_id, clock_label=clk,
                text=f"{ps.name} is first past {m:.0f} km covered, by {clk}.",
                evidence=[ev.event_id],
                data={"player": ps.name, "distance_km": m},
                importance=0.35,
            ))
        return out

    def _recent_ids(self, team_id: str, n: int, kind: str | None = None,
                    player: str | None = None) -> list[str]:
        ids: list[str] = []
        for _, ev in reversed(self.state.idx._win.events):
            if ev.team_id != team_id:
                continue
            if kind and ev.type != kind:
                continue
            if player and ev.player_id != player:
                continue
            ids.append(ev.event_id)
            if len(ids) >= n:
                break
        return list(reversed(ids))
