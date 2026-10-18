"""Azure AI Foundry narrative provider.

Delegates line generation to a chat model deployed on Azure AI Foundry
(Azure OpenAI-compatible endpoint). The prompt is deliberately strict: the
model may only phrase the facts and numbers it is given, never add new ones.
Whatever it returns still passes through the Verifier, so a model that drifts
is caught rather than trusted.

If the call fails for any reason, generation degrades gracefully to the
offline narrator — a live feed must never stall on a model error.

Credentials come from Settings by default; they can be passed explicitly,
which is what makes the HTTP path unit-testable against a mock endpoint.
"""

from __future__ import annotations

import json

import httpx

from ..config import SETTINGS
from .offline import OfflineNarrator
from .provider import NarrativeProvider, NarrativeRequest

_SYSTEM = (
    "You are a football broadcast writer in a live control room. "
    "Write ONE short, natural commentary line for the given moment. "
    "You may ONLY use the facts and numbers provided. Do not invent players, "
    "stats, times, or events. Do not add numbers that are not in the data. "
    "Match the requested audience tone. Return only the line, no quotes."
)


class FoundryNarrator(NarrativeProvider):
    mode = "foundry"

    def __init__(self, endpoint: str | None = None, api_key: str | None = None,
                 deployment: str | None = None, api_version: str | None = None,
                 timeout: float = 8.0) -> None:
        self.endpoint = (endpoint if endpoint is not None else SETTINGS.foundry_endpoint).rstrip("/")
        self.api_key = api_key if api_key is not None else SETTINGS.foundry_api_key
        self.deployment = deployment or SETTINGS.foundry_deployment
        self.api_version = api_version or SETTINGS.foundry_api_version
        self.timeout = timeout
        self._fallback = OfflineNarrator()

    @property
    def url(self) -> str:
        return (
            f"{self.endpoint}/openai/deployments/{self.deployment}"
            f"/chat/completions?api-version={self.api_version}"
        )

    def narrate(self, req: NarrativeRequest) -> str:
        try:
            return self._call(self._system(), self._user_prompt(req))
        except Exception:
            # Graceful degradation keeps the feed alive.
            return self._fallback.narrate(req)

    def health(self) -> dict:
        """Lightweight connectivity/credentials probe for the CLI runbook."""
        if not self.endpoint or not self.api_key:
            return {"ok": False, "mode": "offline",
                    "detail": "no Foundry endpoint/key set; using offline narrator"}
        try:
            line = self._call(
                "Reply with exactly: OK",
                "Health check. Reply with exactly: OK",
                max_tokens=5, temperature=0.0,
            )
            return {"ok": True, "mode": "foundry", "deployment": self.deployment,
                    "detail": f"model responded ({line[:20]!r})"}
        except Exception as e:  # pragma: no cover - network dependent
            return {"ok": False, "mode": "foundry",
                    "detail": f"{type(e).__name__}: {e}"}

    # -- internals -------------------------------------------------------
    def _call(self, system: str, user: str, max_tokens: int = 90,
              temperature: float = 0.6) -> str:
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        r = httpx.post(
            self.url,
            headers={"api-key": self.api_key, "content-type": "application/json"},
            content=json.dumps(payload),
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()

    @staticmethod
    def _system() -> str:
        return _SYSTEM

    def _user_prompt(self, req: NarrativeRequest) -> str:
        return json.dumps({
            "audience": {"persona": req.persona.label, "tone": req.persona.tone},
            "clock": req.fact.clock_label,
            "score": req.score_line,
            "fact": req.fact.text,
            "verified_numbers": req.numbers,
            "language": req.language,
        }, separators=(",", ":"))
