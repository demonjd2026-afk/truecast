"""Verifier: the grounding guarantee.

Checks that a generated line says nothing the data cannot support. It builds an
allow-list of numbers (every figure in the fact and the Analyst's packet, plus
the clock and scoreline, with common % / rounding transforms) and of player and
team names (only those tied to this moment's evidence). Any number or name in
the line outside the allow-list is an unsupported claim, and the line is
rejected so the Explainer can rewrite it.

This is what makes the output safe to put on a live broadcast: an invented stat
never reaches air, whether it came from a template bug or a drifting model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .base import Agent, AnalysisPacket

# A leading sign only counts when it is not wedged between two digits, so a
# scoreline like "2-3" reads as 2 and 3, never as 2 and -3.
_NUM = re.compile(r"(?<!\d)[-+]?\d+(?:\.\d+)?")
_NAME = re.compile(r"\b[A-Z][a-z]+\s[A-Z][a-z]+(?:-[A-Z][a-z]+)?\b")


@dataclass
class VerifierResult:
    ok: bool
    unsupported: list[str]
    reason: str


class Verifier(Agent):
    name = "Verifier"

    def __init__(self, bb) -> None:
        super().__init__(bb)
        self._roster = {p.name for p in bb.state.players.values()}

    def verify(self, line: str, packet: AnalysisPacket, score_line: str) -> VerifierResult:
        allowed_floats = self._allowed_floats(packet, score_line)
        allowed_names = self._allowed_names(packet)

        unsupported: list[str] = []

        # Numbers: every number in the line must be supported.
        for tok in _NUM.findall(line):
            val = float(tok)
            if not self._supported(val, allowed_floats):
                unsupported.append(f"number:{tok}")

        # Names: a roster name in the line must belong to this moment.
        for name in _NAME.findall(line):
            if name in self._roster and name not in allowed_names:
                unsupported.append(f"name:{name}")

        ok = len(unsupported) == 0
        reason = "grounded" if ok else f"{len(unsupported)} unsupported claim(s)"
        return VerifierResult(ok=ok, unsupported=unsupported, reason=reason)

    # -- allow-list construction ----------------------------------------
    def _allowed_floats(self, packet: AnalysisPacket, score_line: str) -> set[float]:
        vals: set[float] = set()

        def add(v: float) -> None:
            vals.add(round(v, 2))
            vals.add(round(v, 1))
            vals.add(float(round(v)))
            if 0.0 <= v <= 1.0:
                # fraction -> percentage, both floor and rounded, since callers
                # may display either int(v*100) or round(v*100).
                vals.add(float(int(v * 100)))
                vals.add(float(round(v * 100)))

        self._walk_numbers(packet.numbers, add)
        self._walk_numbers(packet.fact.data, add)
        # Clock components and score digits are always fair game.
        for part in re.findall(r"\d+", packet.fact.clock_label):
            add(float(part))
        for part in re.findall(r"\d+", score_line):
            add(float(part))
        return vals

    def _walk_numbers(self, obj, add) -> None:
        if isinstance(obj, bool):
            return
        if isinstance(obj, (int, float)):
            add(float(obj))
        elif isinstance(obj, dict):
            for v in obj.values():
                self._walk_numbers(v, add)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                self._walk_numbers(v, add)

    def _allowed_names(self, packet: AnalysisPacket) -> set[str]:
        names: set[str] = set()
        for v in packet.numbers.values():
            if isinstance(v, str) and v in self._roster:
                names.add(v)
        for v in packet.fact.data.values():
            if isinstance(v, str) and v in self._roster:
                names.add(v)
        return names

    @staticmethod
    def _supported(val: float, allowed: set[float], tol: float = 0.01) -> bool:
        if round(val, 2) in allowed or round(val, 1) in allowed or float(round(val)) in allowed:
            return True
        return any(abs(val - a) <= tol for a in allowed)
