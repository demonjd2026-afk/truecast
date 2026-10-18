"""Explainer: turn a vetted moment into a broadcast line.

`draft` asks the active provider (Foundry or offline) for a persona-shaped
line. `recover` is the fallback the Verifier triggers on a rejected draft: it
uses the deterministic narrator, which composes only from the supplied figures
and is grounded by construction. The last-resort line is the Fact's own neutral
text, which cannot contain an unsupported claim.
"""

from __future__ import annotations

from .base import Agent, AnalysisPacket
from ..llm.offline import OfflineNarrator
from ..llm.provider import NarrativeRequest, PersonaSpec


class Explainer(Agent):
    name = "Explainer"

    def __init__(self, bb) -> None:
        super().__init__(bb)
        self._grounded = OfflineNarrator()

    def _request(self, persona: PersonaSpec, packet: AnalysisPacket, score_line: str) -> NarrativeRequest:
        return NarrativeRequest(
            fact=packet.fact, numbers=packet.numbers,
            persona=persona, score_line=score_line,
        )

    def draft(self, persona: PersonaSpec, packet: AnalysisPacket, score_line: str) -> str:
        return self.bb.provider.narrate(self._request(persona, packet, score_line))

    def recover(self, persona: PersonaSpec, packet: AnalysisPacket, score_line: str) -> str:
        return self._grounded.narrate(self._request(persona, packet, score_line))

    @staticmethod
    def last_resort(packet: AnalysisPacket) -> str:
        return packet.fact.text
