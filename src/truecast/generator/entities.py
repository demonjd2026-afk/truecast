"""Fictional clubs and squads.

All names are invented. The hackathon forbids redistributing real match
data and the demo video cannot show real club trademarks, so the whole
world here is synthetic but shaped to behave like a real league fixture.
"""

from __future__ import annotations

import random

from ..models import Player, Team

_FORMATION = [
    ("GK", 1),
    ("DEF", 2), ("DEF", 3), ("DEF", 4), ("DEF", 5),
    ("MID", 6), ("MID", 8), ("MID", 10),
    ("FWD", 7), ("FWD", 9), ("FWD", 11),
]

_FIRST_NAMES = [
    "Marcus", "Elias", "Tobias", "Dontae", "Rafferty", "Kai", "Niall",
    "Bex", "Idris", "Sol", "Teddy", "Caleb", "Ronan", "Jules", "Amos",
    "Kofi", "Luka", "Senan", "Diego", "Ezra", "Finn", "Hugo", "Oisin",
    "Mateo", "Noah", "Reuben", "Samir", "Theo", "Vince", "Wes",
]

_LAST_NAMES = [
    "Ashford", "Beckworth", "Calloway", "Deveraux", "Enright", "Fairbanks",
    "Grimaldi", "Hartley", "Ingram", "Juszczak", "Kessler", "Lindqvist",
    "Moreno", "Nakamura", "Okafor", "Pennington", "Quintero", "Rosenthal",
    "Silvestri", "Travers", "Underhill", "Vasquez", "Whitlock", "Yarwood",
    "Zielinski", "Abara", "Bianchi", "Costa", "Dembele", "Falk",
]

# Club identities: name, short code, shirt colour.
_CLUBS = [
    ("Harbourside United", "HAR", "#0b6cff"),
    ("Kingsmoor City", "KGS", "#e11d48"),
    ("Ravenhill Athletic", "RAV", "#7c3aed"),
    ("Stonebridge Rovers", "STB", "#059669"),
    ("Eastvale Town", "EVT", "#f59e0b"),
    ("Northgate FC", "NGT", "#0ea5e9"),
]


def _make_squad(team_id: str, rng: random.Random) -> list[Player]:
    firsts = rng.sample(_FIRST_NAMES, 11)
    lasts = rng.sample(_LAST_NAMES, 11)
    squad: list[Player] = []
    numbers = {"GK": 1, "DEF": 2, "MID": 6, "FWD": 7}
    for idx, (pos, shirt) in enumerate(_FORMATION):
        name = f"{firsts[idx]} {lasts[idx]}"
        squad.append(
            Player(
                player_id=f"{team_id}_{shirt}",
                name=name,
                number=shirt,
                position=pos,
                team_id=team_id,
            )
        )
    return squad


def build_teams(rng: random.Random) -> tuple[Team, Team]:
    (hn, hc, hcol), (an, ac, acol) = rng.sample(_CLUBS, 2)
    home = Team(team_id=hc, name=hn, short_name=hc, color=hcol)
    away = Team(team_id=ac, name=an, short_name=ac, color=acol)
    home.players = _make_squad(hc, rng)
    away.players = _make_squad(ac, rng)
    return home, away
