"""Core data structures shared across the pipeline.

Everything that moves between stages — raw events, derived state, agent
output, overlay packets — is defined here so the contract is in one place.
Events are kept as plain dataclasses that serialise to compact JSON lines;
the generator writes them, the engine reads them, and the agents reason
over the state the engine builds.

Pitch coordinates are in metres on a 105 x 68 field. Origin (0, 0) is the
bottom-left corner. Each team always attacks toward increasing x in its own
frame of reference, so x is normalised per possessing team to make the
geometry (distance/angle to goal) direction-independent.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0
GOAL_X = 105.0
GOAL_Y = 34.0
GOAL_WIDTH = 7.32


class EventType(str, Enum):
    KICKOFF = "kickoff"
    PASS = "pass"
    CARRY = "carry"
    SHOT = "shot"
    GOAL = "goal"
    SAVE = "save"
    TACKLE = "tackle"
    DUEL = "duel"
    INTERCEPTION = "interception"
    PRESSURE = "pressure"
    POSSESSION_CHANGE = "possession_change"
    FOUL = "foul"
    OUT = "out"
    PERIOD_END = "period_end"


# Outcomes are deliberately open strings per type; these are the common ones.
OUTCOME_COMPLETE = "complete"
OUTCOME_INCOMPLETE = "incomplete"
OUTCOME_ON_TARGET = "on_target"
OUTCOME_OFF_TARGET = "off_target"
OUTCOME_BLOCKED = "blocked"
OUTCOME_WON = "won"
OUTCOME_LOST = "lost"


@dataclass
class Player:
    player_id: str
    name: str
    number: int
    position: str          # GK, DEF, MID, FWD
    team_id: str


@dataclass
class Team:
    team_id: str
    name: str
    short_name: str
    color: str
    players: list[Player] = field(default_factory=list)


@dataclass
class MatchMeta:
    match_id: str
    competition: str
    home: Team
    away: Team
    venue: str
    kickoff_iso: str
    seed: int

    def team(self, team_id: str) -> Team:
        return self.home if team_id == self.home.team_id else self.away

    def opponent(self, team_id: str) -> Team:
        return self.away if team_id == self.home.team_id else self.home

    def to_public(self) -> dict[str, Any]:
        """Roster/meta for API clients (no seed internals needed on wire)."""
        def _team(t: Team) -> dict[str, Any]:
            return {
                "team_id": t.team_id,
                "name": t.name,
                "short_name": t.short_name,
                "color": t.color,
                "players": [asdict(p) for p in t.players],
            }

        return {
            "match_id": self.match_id,
            "competition": self.competition,
            "venue": self.venue,
            "kickoff_iso": self.kickoff_iso,
            "home": _team(self.home),
            "away": _team(self.away),
        }


@dataclass
class Event:
    event_id: str
    match_id: str
    sequence: int
    period: int
    clock_s: float                 # seconds elapsed within the period
    type: str
    team_id: str
    player_id: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    end_x: Optional[float] = None
    end_y: Optional[float] = None
    receiver_id: Optional[str] = None
    outcome: Optional[str] = None
    detail: dict[str, Any] = field(default_factory=dict)
    # Wall-clock send time, stamped only when an event is streamed; 0.0 in
    # generated data so a given seed reproduces byte-for-byte.
    wall_ts: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @staticmethod
    def from_json(line: str) -> "Event":
        return Event(**json.loads(line))

    @property
    def clock_label(self) -> str:
        base = 0 if self.period == 1 else 45
        total = base * 60 + self.clock_s
        m = int(total // 60)
        s = int(total % 60)
        return f"{m:02d}:{s:02d}"


@dataclass
class Fact:
    """A single verifiable claim derived from the event log.

    Agents are only allowed to speak about Facts. Each Fact names the
    event(s) that justify it, which is what lets the Verifier confirm a
    narrative line is grounded rather than invented.
    """

    fact_id: str
    kind: str                      # e.g. "shot", "momentum_shift", "milestone"
    subject_team: Optional[str]
    subject_player: Optional[str]
    clock_label: str
    text: str                      # neutral, machine statement of the fact
    evidence: list[str]            # event_ids backing this fact
    data: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.0        # 0..1, used by the Director to prioritise


def dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), default=_default)


def _default(o: Any) -> Any:
    if hasattr(o, "__dict__") or hasattr(o, "__dataclass_fields__"):
        return asdict(o)
    raise TypeError(f"not serialisable: {type(o)}")
