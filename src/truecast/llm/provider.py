"""Narrative provider abstraction.

The Explainer agent asks a provider to turn a verified Fact (plus the exact
supporting numbers the Analyst attached) into one broadcast line, written for
a specific persona. Two providers implement the same contract:

* OfflineNarrator - deterministic, template-driven, no network. Default.
* FoundryNarrator - delegates to a model on Azure AI Foundry.

Because both return a single line built only from the supplied facts, the
Verifier can check either one the same way.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..models import Fact


@dataclass
class PersonaSpec:
    key: str                 # analyst | casual | club | player
    label: str
    tone: str                # short description for the LLM / template switch
    team_id: str | None = None
    player_id: str | None = None


@dataclass
class NarrativeRequest:
    fact: Fact
    numbers: dict[str, Any]          # vetted figures the Analyst supplied
    persona: PersonaSpec
    score_line: str                  # e.g. "KGS 2-3 STB"
    language: str = "en"


class NarrativeProvider(ABC):
    mode: str = "base"

    @abstractmethod
    def narrate(self, req: NarrativeRequest) -> str:
        ...


def get_provider() -> NarrativeProvider:
    """Pick Foundry when configured, else the offline narrator."""
    from ..config import SETTINGS
    if SETTINGS.mode == "foundry":
        from .foundry import FoundryNarrator
        return FoundryNarrator()
    from .offline import OfflineNarrator
    return OfflineNarrator()
