from fastapi.testclient import TestClient

from truecast.api.server import app

client = TestClient(app)


def test_meta():
    r = client.get("/api/meta?seed=21")
    assert r.status_code == 200
    d = r.json()
    assert len(d["home"]["players"]) == 11
    assert d["mode"] in ("offline", "foundry")


def test_recap():
    r = client.get("/api/recap?seed=21")
    assert r.status_code == 200
    assert r.json()["moments"]


def test_overlays_export():
    r = client.get("/api/overlays?seed=21")
    assert r.status_code == 200
    ov = r.json()["overlays"]
    assert ov and all("evidence" in o for o in ov)


def test_personalize():
    ov = client.get("/api/overlays?seed=21").json()["overlays"]
    goal = next(o for o in ov if o["kind"] == "goal")
    r = client.get(f"/api/personalize?seed=21&overlay_id={goal['overlay_id']}&mode=club&team_id=KGS")
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is True
    assert body["text"]


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "Control" in r.text
