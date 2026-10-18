"""Runtime configuration, read once from the environment.

The system runs in two modes:

* offline  - no external calls; the deterministic narrator produces every
             line. This is the default so the demo always works.
* foundry  - narrative generation is delegated to a model hosted on
             Azure AI Foundry. Enabled automatically when the Foundry
             endpoint + key are present in the environment.

Nothing else in the codebase reads os.environ directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # LLM / Foundry
    foundry_endpoint: str = ""
    foundry_api_key: str = ""
    foundry_deployment: str = "gpt-4o-mini"
    foundry_api_version: str = "2024-10-21"

    # Stream pacing (seconds of wall time per minute of match time)
    speed: float = float(os.getenv("CR_SPEED", "6.0"))

    # Verifier strictness: max share of a narrative line's tokens that may be
    # unsupported before it is rejected and sent back for a rewrite.
    verifier_tolerance: float = float(os.getenv("CR_VERIFIER_TOLERANCE", "0.0"))

    @property
    def mode(self) -> str:
        return "foundry" if self.foundry_endpoint and self.foundry_api_key else "offline"


def load_settings() -> Settings:
    return Settings(
        foundry_endpoint=os.getenv("AZURE_AI_FOUNDRY_ENDPOINT", "").rstrip("/"),
        foundry_api_key=os.getenv("AZURE_AI_FOUNDRY_API_KEY", ""),
        foundry_deployment=os.getenv("AZURE_AI_FOUNDRY_DEPLOYMENT", "gpt-4o-mini"),
        foundry_api_version=os.getenv("AZURE_AI_FOUNDRY_API_VERSION", "2024-10-21"),
    )


SETTINGS = load_settings()
