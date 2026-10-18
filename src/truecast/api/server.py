"""FastAPI server: live stream, personalization, overlay export, recap.

The /stream endpoint replays a synthetic match through the control-room crew in
accelerated real time and pushes three kinds of server-sent events: periodic
scoreboard/index snapshots, each aired broadcast line, and the machine-readable
overlay packet behind it. The UI in web/ consumes this directly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from ..agents.crew import Truecast
from ..config import SETTINGS
from ..engine.state import abs_time
from ..generator.simulator import generate_match
from ..personas import club_persona, default_personas, player_persona

log = logging.getLogger("truecast")

app = FastAPI(title="Truecast", version="1.0")

def _find_web_dir() -> str:
    """Locate the web/ folder across layouts: editable source tree, an
    installed package where web/ sits beside the app (container WORKDIR), or an
    explicit override. Returns the first that exists."""
    candidates = [
        os.environ.get("TRUECAST_WEB_DIR"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "web")),
        os.path.abspath(os.path.join(os.getcwd(), "web")),
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    return candidates[1]


_WEB = _find_web_dir()

DEFAULT_SEED = 21
MAX_SLEEP = 1.0


def _build(seed: int) -> tuple[Truecast, list]:
    meta, events = generate_match(seed)
    # Always carry both club lines so a viewer can switch side instantly.
    personas = default_personas() + [
        club_persona(meta, meta.home.team_id),
        club_persona(meta, meta.away.team_id),
    ]
    return Truecast(meta, personas=personas), events


@app.get("/api/meta")
def meta(seed: int = DEFAULT_SEED) -> JSONResponse:
    m, _ = generate_match(seed)
    data = m.to_public()
    cr = Truecast(m)
    data["mode"] = cr.mode
    return JSONResponse(data)


@app.get("/api/stream")
async def stream(seed: int = DEFAULT_SEED, speed: float = 40.0):
    cr, events = _build(seed)

    async def gen():
        yield {"event": "meta", "data": json.dumps({
            "fixture": f"{cr.bb.meta.home.name} vs {cr.bb.meta.away.name}",
            "home": cr.bb.meta.home.short_name, "away": cr.bb.meta.away.short_name,
            "home_id": cr.bb.meta.home.team_id, "away_id": cr.bb.meta.away.team_id,
            "mode": cr.mode,
        })}
        last_abs = 0.0
        last_tick_min = -1
        for ev in events:
            now = abs_time(ev.period, ev.clock_s)
            if speed > 0:
                dt = min(MAX_SLEEP, max(0.0, (now - last_abs) / speed))
                if dt:
                    await asyncio.sleep(dt)
            last_abs = now

            new_items = cr.ingest(ev)

            minute = int(now // 60)
            if minute != last_tick_min:
                last_tick_min = minute
                yield {"event": "tick", "data": json.dumps(cr.snapshot())}
            for item in new_items:
                yield {"event": "air", "data": json.dumps(item)}

        yield {"event": "tick", "data": json.dumps(cr.snapshot())}
        yield {"event": "recap", "data": json.dumps(cr.recap())}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(gen())


@app.get("/api/recap")
def recap(seed: int = DEFAULT_SEED) -> JSONResponse:
    cr, events = _build(seed)
    for ev in events:
        cr.ingest(ev)
    return JSONResponse(cr.recap(max_items=10))


@app.get("/api/overlays")
def overlays(seed: int = DEFAULT_SEED) -> JSONResponse:
    """Full machine-readable overlay timeline for a rendering partner."""
    cr, events = _build(seed)
    for ev in events:
        cr.ingest(ev)
    return JSONResponse({"match_id": cr.bb.meta.match_id, "overlays": cr.bb.overlays})


@app.get("/api/personalize")
def personalize(seed: int = DEFAULT_SEED, overlay_id: str = "", mode: str = "club",
                team_id: str = "", player_id: str = "") -> JSONResponse:
    """Re-render one aired moment for a club- or player-focused viewer."""
    cr, events = _build(seed)
    for ev in events:
        cr.ingest(ev)
    overlay = next((o for o in cr.bb.overlays if o["overlay_id"] == overlay_id), None)
    if overlay is None:
        return JSONResponse({"error": "overlay not found"}, status_code=404)

    # Find the stored analysis packet behind this overlay.
    fact_id = None
    for fid, pkt in cr.bb.analyses.items():
        if pkt.evidence == overlay["evidence"]:
            fact_id = fid
            break
    if fact_id is None:
        return JSONResponse({"error": "analysis not found"}, status_code=404)
    packet = cr.bb.analyses[fact_id]

    if mode == "player":
        persona = player_persona(cr.bb.meta, player_id or packet.fact.subject_player or "")
    else:
        persona = club_persona(cr.bb.meta, team_id or packet.fact.subject_team or cr.bb.meta.home.team_id)

    line = cr.explainer.recover(persona, packet, cr.bb.score_line())
    res = cr.verifier.verify(line, packet, cr.bb.score_line())
    return JSONResponse({
        "overlay_id": overlay_id, "persona": persona.label,
        "text": line, "verified": res.ok,
    })


@app.get("/healthz")
def healthz() -> JSONResponse:
    """Liveness probe for container orchestration."""
    return JSONResponse({"status": "ok", "narrator": SETTINGS.mode})


@app.get("/api/models")
def models() -> JSONResponse:
    """Trained-model provenance and held-out metrics (for the UI)."""
    from ..ml.winprob import get_winprob_model
    from ..ml.xgmodel import get_xg_model
    xg, wp = get_xg_model(), get_winprob_model()
    return JSONResponse({
        "xg": {"trained": xg.trained, **xg.metrics},
        "win_prob": {"trained": wp.trained, **wp.metrics},
    })


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(_WEB, "index.html"))


if os.path.isdir(_WEB):
    app.mount("/web", StaticFiles(directory=_WEB), name="web")
