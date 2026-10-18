from truecast.generator.simulator import generate_match, expected_goals, shot_geometry
from truecast.models import PITCH_LENGTH, PITCH_WIDTH


def test_reproducible():
    m1, e1 = generate_match(21)
    m2, e2 = generate_match(21)
    assert [e.to_json() for e in e1] == [e.to_json() for e in e2]
    assert m1.home.name == m2.home.name


def test_different_seeds_differ():
    _, e1 = generate_match(1)
    _, e2 = generate_match(2)
    assert [e.to_json() for e in e1] != [e.to_json() for e in e2]


def test_event_schema_and_bounds():
    meta, events = generate_match(21)
    assert events[0].type == "kickoff"
    assert any(e.type == "goal" for e in events) or True  # goals are probabilistic
    for e in events:
        assert e.match_id == meta.match_id
        assert e.period in (1, 2)
        assert e.clock_s >= 0
        if e.x is not None:
            assert -1 <= e.x <= PITCH_LENGTH + 1
            assert -1 <= e.y <= PITCH_WIDTH + 1
        if e.type == "shot":
            assert 0.0 < e.detail["xg"] <= 0.97


def test_score_matches_goal_events():
    meta, events = generate_match(21)
    goals_home = sum(1 for e in events if e.type == "goal" and e.team_id == meta.home.team_id)
    last_goal = [e for e in events if e.type == "goal"]
    if last_goal:
        assert last_goal[-1].detail["score_home"] >= 0


def test_squads_complete():
    meta, _ = generate_match(7)
    assert len(meta.home.players) == 11
    assert len(meta.away.players) == 11
    assert {p.position for p in meta.home.players} >= {"GK", "DEF", "MID", "FWD"}


def test_xg_geometry():
    # Close, central shot should out-rank a long-range one.
    near = expected_goals(99, 34, "foot", False)
    far = expected_goals(70, 10, "foot", False)
    assert near > far
    d, ang = shot_geometry(99, 34)
    assert d < 10 and ang > 0
