from truecast.engine.metrics import pass_difficulty
from truecast.engine.state import MatchState
from truecast.engine.moments import MomentDetector
from truecast.generator.simulator import generate_match


def _run():
    meta, events = generate_match(21)
    st = MatchState(meta)
    det = MomentDetector(st)
    facts = []
    for ev in events:
        st.apply(ev)
        facts += det.observe(ev)
    return meta, st, facts


def test_pass_difficulty_bounds():
    assert pass_difficulty(5, 0.1, False) < pass_difficulty(40, 0.9, True)
    assert 0.0 <= pass_difficulty(100, 1.0, True) <= 1.0


def test_possession_sums_to_100():
    _, st, _ = _run()
    pos = st.possession_pct()
    assert abs(sum(pos.values()) - 100) <= 1


def test_player_distances_realistic():
    _, st, _ = _run()
    outfield = [p for p in st.players.values() if p.position != "GK"]
    dists = [p.distance_m / 1000 for p in outfield]
    assert 7.0 <= max(dists) <= 14.0
    assert min(dists) >= 5.0


def test_indices_in_range():
    _, st, _ = _run()
    snap = st.idx.snapshot()
    assert -1.0 <= snap["momentum"] <= 1.0
    assert 0.0 <= snap["chaos"] <= 1.0
    for v in snap["control"].values():
        assert 0.0 <= v <= 1.0


def test_facts_have_evidence():
    _, _, facts = _run()
    assert facts
    for f in facts:
        assert f.evidence, f"fact {f.kind} has no evidence"
        assert f.text


def test_goal_facts_present():
    _, _, facts = _run()
    assert any(f.kind == "goal" for f in facts)
