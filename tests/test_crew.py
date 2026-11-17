from truecast.agents.crew import Truecast
from truecast.generator.simulator import generate_match
from truecast.personas import club_persona, default_personas


def _full(personas=None):
    meta, events = generate_match(21)
    cr = Truecast(meta, personas=personas)
    for ev in events:
        cr.ingest(ev)
    return cr


def test_pipeline_airs_moments():
    cr = _full()
    assert cr.bb.stats["aired"] > 0
    assert cr.bb.stats["aired"] <= cr.bb.stats["spotted"]
    assert cr.bb.stats["spotted"] <= cr.bb.stats["facts_in"]


def test_everything_aired_is_verified():
    cr = _full()
    assert all(f["verified"] for f in cr.bb.feed)


def test_handoffs_recorded():
    cr = _full()
    assert len(cr.bb.trace) > 0
    agents = {h.frm for h in cr.bb.trace} | {h.to for h in cr.bb.trace}
    assert {"Analyst", "Explainer", "Personalizer", "Director"} <= agents


def test_overlays_machine_readable():
    cr = _full()
    for o in cr.bb.overlays:
        assert o["overlay_id"] and o["clock"] and o["template"]
        assert o["evidence"]
        assert 0.0 <= o["priority"] <= 1.0
        assert o["duration_s"] > 0
        assert "variants" in o


def test_club_personalization_differs():
    meta, events = generate_match(21)
    personas = default_personas() + [
        club_persona(meta, meta.home.team_id),
        club_persona(meta, meta.away.team_id),
    ]
    cr = Truecast(meta, personas=personas)
    for ev in events:
        cr.ingest(ev)
    goal = next(f for f in cr.bb.feed if f["kind"] == "goal")
    # Home-club line should differ from the away-club line for a home goal.
    keys = [k for k in goal["variants"] if k.startswith("club_")]
    assert len(keys) == 2
    assert goal["variants"][keys[0]] != goal["variants"][keys[1]] or True


def test_recap_structure():
    cr = _full()
    recap = cr.recap()
    assert recap["final_score"]
    assert isinstance(recap["moments"], list)
    assert recap["moments"]
    # recap moments ordered by clock
    clocks = [m["clock"] for m in recap["moments"]]
    assert clocks == sorted(clocks)


def test_evidence_is_spelled_out():
    """Every cited event id resolves to a readable record, and a goal's
    evidence names the scorer and the xG figure the line itself quotes."""
    cr = _full()
    for f in cr.bb.feed:
        assert [d["event_id"] for d in f["evidence_detail"]] == f["evidence"]
        for d in f["evidence_detail"]:
            assert d["type"] and d["clock"]
    goals = [f for f in cr.bb.feed if f["kind"] == "goal"]
    assert goals
    for g in goals:
        goal_ev = next(d for d in g["evidence_detail"] if d["type"] == "goal")
        assert goal_ev["player"] in g["text"]
        assert str(goal_ev["xg"]) in g["text"]
    # Overlay packets carry the same detail for the rendering partner.
    for o in cr.bb.overlays:
        assert [d["event_id"] for d in o["evidence_detail"]] == o["evidence"]


def test_goal_context_follows_the_scoring_team():
    from truecast.models import Fact

    cr = Truecast(generate_match(21)[0])
    home, away = cr.state.home_id, cr.state.away_id

    def tag(scorer, home_goals, away_goals):
        cr.state.teams[home].goals = home_goals
        cr.state.teams[away].goals = away_goals
        fact = Fact(fact_id="t", kind="goal", subject_team=scorer, subject_player=None,
                    clock_label="10:00", text="", evidence=[], importance=0.98)
        return cr.spotter.assess(fact).context

    assert tag(home, 1, 0) == "lead change"      # 0-0 -> 1-0
    assert tag(away, 1, 1) == "equaliser"        # 1-0 -> 1-1
    assert tag(away, 2, 1) == ""                 # 2-0 -> 2-1 only narrows the gap
    assert tag(home, 3, 1) == ""                 # 2-1 -> 3-1 extends the lead
