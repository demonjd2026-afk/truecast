"""Director: decide what goes on air and package it.

Takes a moment's verified variants and produces the two outputs that leave the
system: an entry on the broadcast feed (the line a given viewer sees) and a
machine-readable overlay packet for the rendering partner, timed and carrying
its evidence. Priority comes from the Spotter's salience, so bigger moments get
longer, higher-priority graphics.
"""

from __future__ import annotations

from .base import Agent, AnalysisPacket, SpottedItem, Variant
from ..overlay.schema import OverlayPacket, duration_for, headline_for


class Director(Agent):
    name = "Director"

    def __init__(self, bb) -> None:
        super().__init__(bb)
        self._n = 0

    def direct(self, item: SpottedItem, packet: AnalysisPacket, variants: list[Variant]) -> OverlayPacket:
        self._n += 1
        fact = item.fact
        var_map = {v.persona: v.text for v in variants}
        all_verified = all(v.verified for v in variants)
        evidence_detail = [self.bb.state.describe_event(i) for i in packet.evidence]

        from ..overlay.schema import TEMPLATE_BY_KIND
        overlay = OverlayPacket(
            overlay_id=f"ov{self._n:04d}",
            match_id=self.bb.meta.match_id,
            clock=fact.clock_label,
            period=self.bb.state.period,
            kind=fact.kind,
            template=TEMPLATE_BY_KIND.get(fact.kind, "stat_flash"),
            priority=item.salience,
            duration_s=duration_for(fact.kind, item.salience),
            headline=headline_for(fact.kind, fact.data),
            variants=var_map,
            data=packet.numbers,
            evidence=packet.evidence,
            verified=all_verified,
            evidence_detail=evidence_detail,
        )
        self.bb.overlays.append(overlay.to_dict())

        # Feed entry: the analyst line is the default "on air" text.
        air_text = var_map.get("analyst") or next(iter(var_map.values()), fact.text)
        self.bb.feed.append({
            "overlay_id": overlay.overlay_id,
            "clock": fact.clock_label,
            "kind": fact.kind,
            "salience": item.salience,
            "context": item.context,
            "headline": overlay.headline,
            "text": air_text,
            "variants": var_map,
            "evidence": packet.evidence,
            "evidence_detail": evidence_detail,
            "verified": all_verified,
            "team_id": fact.subject_team,
            "player_id": fact.subject_player,
        })
        self.bb.stats["aired"] += 1
        return overlay
