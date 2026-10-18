"""Deterministic broadcast narrator.

Produces persona-shaped commentary lines from the Fact and the Analyst's
vetted numbers, with no external calls. Lines are assembled only from values
present in the request, so they always pass the Verifier. Seeded phrase
choice keeps output varied but reproducible.
"""

from __future__ import annotations

import random
import re

from .provider import NarrativeProvider, NarrativeRequest

# Technical fragments a casual viewer doesn't need; removing them only drops
# numbers, so the line stays grounded.
_CASUAL_STRIP = [
    re.compile(r"\s*\[[^\]]*\]"),                      # analyst tail
    re.compile(r",?\s*an? [\d.]+ xG opportunity"),     # "a 0.49 xG opportunity"
    re.compile(r"\s*\([\d.+-]+ xG\)"),                 # "(0.07 xG)"
    re.compile(r"\.?\s*That chance was worth [\d.]+ xG"),
    re.compile(r"\s*\(momentum index [\d.+-]+[^)]*\)"),
]


class OfflineNarrator(NarrativeProvider):
    mode = "offline"

    def narrate(self, req: NarrativeRequest) -> str:
        rng = random.Random(req.fact.fact_id + req.persona.key)
        fn = getattr(self, f"_{req.fact.kind}", self._generic)
        line = fn(req, rng)
        return self._shape(line, req, rng)

    # -- per-kind lines (facts/figures only) ----------------------------
    def _goal(self, req, rng):
        d = req.fact.data
        openers = ["GOAL.", "It's in!", "They've scored."]
        o = rng.choice(openers)
        return (f"{o} {d['scorer']} finds the net for {d['team']} at "
                f"{req.fact.clock_label}. It's {req.score_line}. "
                f"That chance was worth {d['xg']} xG.")

    def _big_chance(self, req, rng):
        d = req.fact.data
        verb = {"on_target": "forces a save", "off_target": "drags it wide",
                "blocked": "sees it blocked"}.get(d.get("outcome"), "goes close")
        return (f"Big chance — {d['shooter']} {verb} for {d['team']} at "
                f"{req.fact.clock_label}, a {d['xg']} xG opportunity.")

    def _shot(self, req, rng):
        d = req.fact.data
        return (f"{d['shooter']} has a go for {d['team']} at "
                f"{req.fact.clock_label} ({d['xg']} xG).")

    def _save(self, req, rng):
        d = req.fact.data
        return f"Save by {d['keeper']} to keep it {req.score_line} at {req.fact.clock_label}."

    def _momentum_shift(self, req, rng):
        d = req.fact.data
        return (f"The flow of this game is with {d['team']} right now "
                f"({req.fact.clock_label}). Momentum index {d['momentum']:+.2f}, "
                f"tempo up at {d['tempo']} actions a minute.")

    def _control_spell(self, req, rng):
        d = req.fact.data
        return (f"{d['team']} have settled into control around "
                f"{req.fact.clock_label} — {int(d['control']*100)}% control of this "
                f"phase against a chaos reading of {d['chaos']:.2f}.")

    def _pressure_build(self, req, rng):
        d = req.fact.data
        return (f"{d['team']} are turning the screw at {req.fact.clock_label}, "
                f"pressing at {d['pressure']:.1f} actions a minute.")

    def _milestone(self, req, rng):
        d = req.fact.data
        if "passes" in d:
            return (f"{d['player']} ticks past {d['passes']} completed passes "
                    f"({d['accuracy']}%) by {req.fact.clock_label}.")
        return f"{d['player']} has now covered {d['distance_km']:.0f} km by {req.fact.clock_label}."

    def _generic(self, req, rng):
        return req.fact.text

    # -- persona shaping (never introduces new facts) -------------------
    def _shape(self, line: str, req, rng) -> str:
        p = req.persona
        if p.key == "analyst":
            tail = self._analyst_tail(req)
            return f"{line}{tail}" if tail else line
        if p.key == "casual":
            out = line
            for pat in _CASUAL_STRIP:
                out = pat.sub("", out)
            out = re.sub(r"\s+([.,])", r"\1", out).strip()
            if out and not out.endswith((".", "!")):
                out += "."
            return out
        if p.key.startswith("club") and p.team_id:
            if req.fact.subject_team == p.team_id and req.fact.kind in ("goal", "big_chance"):
                return line + " Get in!"
            return line
        if p.key.startswith("player") and p.player_id:
            if req.fact.subject_player == p.player_id:
                return "★ " + line
            return line
        return line

    def _analyst_tail(self, req) -> str:
        n = req.numbers
        bits = []
        if "team_xg" in n:
            bits.append(f"team xG {n['team_xg']}")
        if "team_shots" in n:
            bits.append(f"{n['team_shots']} shots")
        if "possession" in n:
            bits.append(f"{n['possession']}% possession")
        return f" [{', '.join(bits)}]" if bits else ""
