"""Spotter: the producer's ear.

Decides which detected Facts are worth the control room's attention, scoring
salience from the fact's own importance plus live context (is the game level,
is this a lead change, has it gone quiet). Low-value chatter is dropped here so
the rest of the crew only works on moments that matter.
"""

from __future__ import annotations

from .base import Agent, Blackboard, SpottedItem
from ..models import Fact

_MIN_SALIENCE = 0.3


class Spotter(Agent):
    name = "Spotter"

    def __init__(self, bb: Blackboard) -> None:
        super().__init__(bb)
        self._last_aired_clock_by_kind: dict[str, float] = {}

    def assess(self, fact: Fact) -> SpottedItem | None:
        self.bb.stats["facts_in"] += 1
        salience = fact.importance
        context_bits: list[str] = []

        h, a = self.bb.state.score()
        if fact.kind == "goal":
            if h == a:
                salience = min(1.0, salience + 0.02)
                context_bits.append("equaliser")
            elif abs(h - a) == 1:
                context_bits.append("lead change" if fact.data.get("score_home") is not None else "")
        if fact.kind in ("control_spell", "pressure_build", "milestone"):
            # These matter less when the game is wide open.
            if self.bb.state.idx.chaos() > 0.6:
                salience -= 0.08

        if salience < _MIN_SALIENCE:
            return None

        self.bb.stats["spotted"] += 1
        ctx = ", ".join(b for b in context_bits if b)
        return SpottedItem(fact=fact, salience=round(min(1.0, salience), 3), context=ctx)
