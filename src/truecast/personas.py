"""Audience personas.

The same match intelligence is rendered differently for each. Analyst and
casual are always produced for the live feed; club- and player-focused
variants are rendered on demand for a given team or player, which is how a
viewer tailors the broadcast to their side or their favourite.
"""

from __future__ import annotations

from .llm.provider import PersonaSpec
from .models import MatchMeta

ANALYST = PersonaSpec(
    key="analyst", label="Analyst",
    tone="precise and data-led; include the supporting numbers",
)
CASUAL = PersonaSpec(
    key="casual", label="Casual fan",
    tone="warm, plain-language, light on jargon",
)


def default_personas() -> list[PersonaSpec]:
    return [ANALYST, CASUAL]


def club_persona(meta: MatchMeta, team_id: str) -> PersonaSpec:
    team = meta.team(team_id)
    return PersonaSpec(
        key=f"club_{team_id}", label=f"{team.name} fan",
        tone=f"a supporter of {team.name}; celebrate their moments",
        team_id=team_id,
    )


def player_persona(meta: MatchMeta, player_id: str) -> PersonaSpec:
    name = player_id
    for t in (meta.home, meta.away):
        for p in t.players:
            if p.player_id == player_id:
                name = p.name
    return PersonaSpec(
        key=f"player_{player_id}", label=f"{name} focus",
        tone=f"follow {name} throughout the match; highlight their involvement",
        player_id=player_id,
    )
