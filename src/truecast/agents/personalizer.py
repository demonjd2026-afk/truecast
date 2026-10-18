"""Personalizer: render the same moment for every audience.

Drives the Explainer/Verifier loop once per persona. A rejected draft is
handed back to the Explainer to rewrite (recorded as a Verifier -> Explainer
handoff); if it still fails, the line falls back to the Fact's neutral text.
The result is a set of verified, audience-specific lines for one moment — the
personalization stage of the pipeline.
"""

from __future__ import annotations

from .base import Agent, AnalysisPacket, SpottedItem, Variant
from .explainer import Explainer
from .verifier import Verifier
from ..llm.provider import PersonaSpec

MAX_REWRITES = 2


class Personalizer(Agent):
    name = "Personalizer"

    def __init__(self, bb, explainer: Explainer, verifier: Verifier) -> None:
        super().__init__(bb)
        self.explainer = explainer
        self.verifier = verifier

    def render_one(self, packet: AnalysisPacket, persona: PersonaSpec) -> Variant:
        score_line = self.bb.score_line()
        text = self.explainer.draft(persona, packet, score_line)
        res = self.verifier.verify(text, packet, score_line)
        rewrites = 0
        while not res.ok and rewrites < MAX_REWRITES:
            self.bb.handoff(
                "Verifier", "Explainer",
                f"rejected ({res.reason}); rewrite", packet.fact.fact_id,
            )
            self.bb.stats["rewrites"] += 1
            text = self.explainer.recover(persona, packet, score_line)
            res = self.verifier.verify(text, packet, score_line)
            rewrites += 1
        if not res.ok:
            # Guaranteed-grounded neutral statement.
            text = self.explainer.last_resort(packet)
            res = self.verifier.verify(text, packet, score_line)
            self.bb.stats["rejected"] += 1
        return Variant(
            persona=persona.key, label=persona.label, text=text,
            verified=res.ok, rewrites=rewrites, unsupported=res.unsupported,
        )

    def render(self, item: SpottedItem, packet: AnalysisPacket) -> list[Variant]:
        variants = [self.render_one(packet, p) for p in self.bb.personas]
        self.bb.handoff(self.name, "Director", f"{len(variants)} variants", packet.fact.fact_id)
        return variants
