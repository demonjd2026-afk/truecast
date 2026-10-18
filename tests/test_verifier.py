"""The Verifier is the project's safety guarantee, so it gets the most scrutiny.

These tests prove it accepts grounded lines and rejects three classes of
hallucination: an invented number, a made-up stat, and a player who was not
part of the moment — while not tripping over scorelines and clocks.
"""

from truecast.agents.crew import Truecast
from truecast.generator.simulator import generate_match


def _room_with_goal():
    meta, events = generate_match(21)
    cr = Truecast(meta)
    for ev in events:
        cr.ingest(ev)
    # grab a stored analysis packet for a goal
    goal_fid = next(fid for fid, p in cr.bb.analyses.items() if p.fact.kind == "goal")
    return cr, cr.bb.analyses[goal_fid]


def test_grounded_line_passes():
    cr, packet = _room_with_goal()
    line = packet.fact.text  # neutral, fully grounded
    res = cr.verifier.verify(line, packet, cr.bb.score_line())
    assert res.ok, res.unsupported


def test_offline_narrator_output_passes():
    cr, packet = _room_with_goal()
    from truecast.personas import ANALYST
    line = cr.explainer.recover(ANALYST, packet, cr.bb.score_line())
    res = cr.verifier.verify(line, packet, cr.bb.score_line())
    assert res.ok, res.unsupported


def test_invented_number_rejected():
    cr, packet = _room_with_goal()
    scorer = packet.fact.data["scorer"]
    # A plausible but unsupported stat: a sprint speed that is nowhere in the data.
    bad = f"{scorer} hit 38.7 km/h in the build-up."
    res = cr.verifier.verify(bad, packet, cr.bb.score_line())
    assert not res.ok
    assert any(u.startswith("number:") for u in res.unsupported)


def test_wrong_player_rejected():
    cr, packet = _room_with_goal()
    # A real roster player who is not the scorer and not in the evidence.
    scorer = packet.fact.data["scorer"]
    other = next(p.name for p in cr.bb.state.players.values()
                 if p.name != scorer)
    bad = f"{other} finishes it off."
    res = cr.verifier.verify(bad, packet, cr.bb.score_line())
    assert not res.ok
    assert any(u == f"name:{other}" for u in res.unsupported)


def test_scoreline_not_falsely_flagged():
    cr, packet = _room_with_goal()
    # Hyphenated score must not read as a negative number.
    line = f"It's {cr.bb.score_line()} at {packet.fact.clock_label}."
    res = cr.verifier.verify(line, packet, cr.bb.score_line())
    assert res.ok, res.unsupported


def test_recovery_on_rejection_counts():
    """A deliberately broken provider forces the Verifier->Explainer path."""
    from truecast.llm.provider import NarrativeProvider

    class Hallucinator(NarrativeProvider):
        mode = "test"
        def narrate(self, req):
            return f"{req.fact.data.get('scorer','Someone')} ran 99.9 km/h there."

    meta, events = generate_match(21)
    cr = Truecast(meta)
    cr.bb.provider = Hallucinator()
    cr.explainer.bb.provider = cr.bb.provider  # explainer reads provider via bb
    for ev in events:
        cr.ingest(ev)
    # The bad drafts must have been caught and rewritten, not aired as-is.
    assert cr.bb.stats["rewrites"] > 0
    assert all(f["verified"] for f in cr.bb.feed)
