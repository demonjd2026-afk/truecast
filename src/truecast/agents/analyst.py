"""Analyst: attach the exact supporting numbers.

Takes a spotted moment and pulls the precise figures that back it from live
match state — team xG, shot counts, possession, the player's own tallies —
storing display-ready values so that anything later spoken on air is a number
that already exists in the data. These numbers become the Verifier's allow-list.
"""

from __future__ import annotations

from .base import Agent, AnalysisPacket, SpottedItem


class Analyst(Agent):
    name = "Analyst"

    def analyze(self, item: SpottedItem) -> AnalysisPacket:
        fact = item.fact
        st = self.bb.state
        numbers: dict = dict(fact.data)  # start from the fact's own figures

        tid = fact.subject_team
        if tid and tid in st.teams:
            ts = st.teams[tid]
            numbers["team_xg"] = round(ts.xg, 2)
            numbers["team_shots"] = ts.shots
            numbers["possession"] = st.possession_pct().get(tid, 0)

        pid = fact.subject_player
        if pid and pid in st.players:
            ps = st.players[pid]
            numbers["player_passes"] = ps.passes_completed
            numbers["player_distance_km"] = round(ps.distance_m / 1000.0, 1)
            numbers["player_top_speed_kmh"] = round(ps.top_speed_ms * 3.6, 1)

        packet = AnalysisPacket(fact=fact, numbers=numbers, evidence=list(fact.evidence))
        self.bb.analyses[fact.fact_id] = packet
        self.bb.handoff(self.name, "Explainer", f"packet for {fact.kind}", fact.fact_id)
        return packet
