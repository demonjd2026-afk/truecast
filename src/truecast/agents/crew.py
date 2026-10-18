"""The control-room crew: orchestration across the six agents.

Pipeline per detected moment:

    Spotter -> Analyst -> Explainer -> Verifier -> (Explainer on reject)
            -> Personalizer -> Director

Each stage is a distinct agent with one responsibility; they share one
Blackboard and hand off explicitly. The Verifier can send work back to the
Explainer, which is the crew's failure-recovery path. The end-to-end outcome —
a verified, personalised, broadcast-ready overlay with its evidence — is
something no single agent produces alone.
"""

from __future__ import annotations

from .analyst import Analyst
from .base import Blackboard
from .director import Director
from .explainer import Explainer
from .personalizer import Personalizer
from .spotter import Spotter
from .verifier import Verifier
from ..engine.moments import MomentDetector
from ..engine.state import MatchState
from ..llm.provider import NarrativeProvider, PersonaSpec, get_provider
from ..models import Event, MatchMeta
from ..personas import default_personas


class Truecast:
    """Wraps the engine + agent crew behind a single `ingest(event)` call."""

    def __init__(self, meta: MatchMeta,
                 provider: NarrativeProvider | None = None,
                 personas: list[PersonaSpec] | None = None) -> None:
        self.state = MatchState(meta)
        self.detector = MomentDetector(self.state)
        self.bb = Blackboard(
            meta=meta, state=self.state,
            provider=provider or get_provider(),
            personas=personas or default_personas(),
        )
        self.spotter = Spotter(self.bb)
        self.analyst = Analyst(self.bb)
        self.explainer = Explainer(self.bb)
        self.verifier = Verifier(self.bb)
        self.personalizer = Personalizer(self.bb, self.explainer, self.verifier)
        self.director = Director(self.bb)

    @property
    def mode(self) -> str:
        return self.bb.provider.mode

    def ingest(self, ev: Event) -> list[dict]:
        """Process one event; return any new feed entries it produced."""
        self.state.apply(ev)
        before = len(self.bb.feed)
        for fact in self.detector.observe(ev):
            item = self.spotter.assess(fact)
            if item is None:
                continue
            packet = self.analyst.analyze(item)
            variants = self.personalizer.render(item, packet)
            self.director.direct(item, packet, variants)
        return self.bb.feed[before:]

    # -- summary / recap -------------------------------------------------
    def snapshot(self) -> dict:
        snap = self.state.snapshot()
        snap["mode"] = self.mode
        snap["stats"] = dict(self.bb.stats)
        return snap

    def recap(self, max_items: int = 8) -> dict:
        """End-of-match recap: the highest-salience aired moments, in order."""
        items = sorted(self.bb.feed, key=lambda f: -f["salience"])[:max_items]
        items = sorted(items, key=lambda f: f["clock"])
        return {
            "match_id": self.bb.meta.match_id,
            "fixture": f"{self.bb.meta.home.name} vs {self.bb.meta.away.name}",
            "final_score": self.bb.score_line(),
            "moments": items,
            "stats": dict(self.bb.stats),
        }
