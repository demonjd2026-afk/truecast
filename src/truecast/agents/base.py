"""Shared state and primitives for the control-room agent crew.

The crew is a small, explicit orchestration: specialised agents read and write
one shared Blackboard and hand work to each other in a fixed pipeline, with the
Verifier able to bounce a line back to the Explainer. Every handoff is recorded
on the Blackboard's trace so the collaboration is inspectable — which is both an
explainability feature and the evidence of real multi-agent coordination.

The structure maps onto the Microsoft Agent Framework's agent/shared-thread
model (see ARCHITECTURE.md); it is implemented directly here so the system
runs with no cloud dependency, and swaps to Foundry-hosted agents by changing
only the provider.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..engine.state import MatchState
from ..llm.provider import NarrativeProvider, PersonaSpec
from ..models import Fact, MatchMeta


@dataclass
class Handoff:
    frm: str
    to: str
    note: str
    fact_id: str
    ts: float = field(default_factory=time.time)


@dataclass
class SpottedItem:
    fact: Fact
    salience: float
    context: str


@dataclass
class AnalysisPacket:
    fact: Fact
    numbers: dict[str, Any]
    evidence: list[str]


@dataclass
class Variant:
    persona: str
    label: str
    text: str
    verified: bool
    rewrites: int
    unsupported: list[str] = field(default_factory=list)


@dataclass
class Blackboard:
    meta: MatchMeta
    state: MatchState
    provider: NarrativeProvider
    personas: list[PersonaSpec]
    trace: list[Handoff] = field(default_factory=list)
    feed: list[dict] = field(default_factory=list)
    overlays: list[dict] = field(default_factory=list)
    analyses: dict[str, AnalysisPacket] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=lambda: {
        "facts_in": 0, "spotted": 0, "aired": 0, "rewrites": 0, "rejected": 0,
    })

    def handoff(self, frm: str, to: str, note: str, fact_id: str) -> None:
        self.trace.append(Handoff(frm, to, note, fact_id))

    def score_line(self) -> str:
        h, a = self.state.score()
        return f"{self.meta.home.short_name} {h}-{a} {self.meta.away.short_name}"


class Agent:
    name: str = "agent"

    def __init__(self, bb: Blackboard) -> None:
        self.bb = bb
