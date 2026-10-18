"""Tests for the trained models and the analytics they feed into the snapshot."""

from truecast.agents.crew import Truecast
from truecast.generator.simulator import generate_match
from truecast.ml.winprob import get_winprob_model
from truecast.ml.xgmodel import get_xg_model


def test_xg_model_loaded_and_monotonic():
    m = get_xg_model()
    assert m.trained, "xg.json artifact should ship with the package"
    near = m.predict(6.0, 0.8, is_header=False, big_chance=True, under_pressure=False)
    far = m.predict(30.0, 0.1, is_header=False, big_chance=False, under_pressure=True)
    assert 0.0 < far < near < 1.0


def test_xg_metrics_present():
    m = get_xg_model()
    assert {"brier", "auc", "log_loss"} <= set(m.metrics)
    assert 0.5 < m.metrics["auc"] <= 1.0


def test_winprob_sums_to_one_and_tracks_state():
    wp = get_winprob_model()
    assert wp.trained
    for mins, sd in [(10, 0), (80, 2), (85, -1)]:
        p = wp.predict(mins, sd, 0.0, 0, 0.0, 0)
        assert abs(sum(p.values()) - 1.0) < 0.01  # 3-dp rounding tolerance
    leading = wp.predict(85, 2, 1.0, 5, 0.3, 10)
    trailing = wp.predict(85, -2, -1.0, -5, -0.3, -10)
    assert leading["home"] > 0.6
    assert trailing["away"] > 0.6


def test_snapshot_carries_winprob_and_shots():
    meta, events = generate_match(21)
    cr = Truecast(meta)
    for ev in events:
        cr.ingest(ev)
    snap = cr.snapshot()
    assert set(snap["win_prob"]) == {"home", "draw", "away"}
    assert snap["shots"], "shot map should be populated"
    s = snap["shots"][0]
    assert {"x", "y", "xg", "team", "goal"} <= set(s)
    # final win-prob should favour the team that actually won
    h, a = cr.state.score()
    if a > h:
        assert snap["win_prob"]["away"] > snap["win_prob"]["home"]


def test_goals_marked_on_shot_map():
    meta, events = generate_match(21)
    cr = Truecast(meta)
    for ev in events:
        cr.ingest(ev)
    goals_on_map = sum(1 for s in cr.state.shots if s["goal"])
    assert goals_on_map == sum(cr.state.teams[t].goals for t in cr.state.teams)
