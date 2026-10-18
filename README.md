<h1 align="center">Truecast</h1>
<p align="center"><strong>Match intelligence you can prove.</strong></p>
<p align="center">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="Tests" src="https://img.shields.io/badge/tests-33%20passing-brightgreen">
</p>

Truecast turns a stream of synthetic football events into broadcast-ready match
intelligence — live stats, the moments that matter, *why* they matter, and a
different telling of the same match for every kind of viewer. A crew of
specialised agents produces every on-air line, and a **Verifier** agent checks
each line against the event log before it airs. Nothing reaches the screen that
the data cannot back.

> Built for the Microsoft × Premier League *Inside the Game: Developer
> Hackathon*. All data is synthetic. No real match data or club trademarks are
> used.

---

## The one idea

Live broadcast graphics have to be right. A generated line that invents a stat,
a speed, or the wrong scorer is worse than no line at all — and no broadcaster
will put an unverifiable number on air. Most "AI commentary" demos generate
fluent text and hope it's accurate.

Truecast makes grounding a hard guarantee. The pipeline only ever speaks about
**Facts** — neutral, machine-checkable statements, each carrying the event IDs
that justify it. Before any line airs, the Verifier rebuilds an allow-list from
those events and rejects the line if it contains a number or a player it cannot
support. A rejected line is handed back to the Explainer to rewrite; the worst
case is a plainer true sentence, never a confident false one.

A real moment from match #21, and the events behind it:

```
04:55  ✓  [goal]  GOAL. Kai Enright finds the net for Kingsmoor City at 04:55.
                  It's KGS 1-0 STB. That chance was worth 0.494 xG.
       └─ evidence: e00147 (goal), e00146 (the shot)   → every figure traceable
```

---

## Pipeline

The brief asks for one pipeline with five stages. Truecast maps onto them
directly:

| Stage | What happens | Where |
|------|---------------|-------|
| **Ingest** | synthetic events arrive (passes, shots, tackles, pressure, possession) | `generator/`, `engine/state.py` |
| **Interpret** | live stats, xG, momentum, control-vs-chaos, pressure, tempo | `engine/` |
| **Explain** | why the moment matters, written and then verified | `agents/explainer.py`, `agents/verifier.py` |
| **Render** | timed, machine-readable overlay packets for a rendering partner | `overlay/`, `agents/director.py` |
| **Personalize** | the same moment for analyst, casual, club, or player focus | `agents/personalizer.py`, `personas.py` |

A match that only produces metrics has no audience; one that only personalises
has nothing to personalise. Truecast does both.

---

## The agent crew

Six single-purpose agents share one blackboard and hand work to each other
explicitly:

```
 Spotter ─▶ Analyst ─▶ Explainer ─▶ Verifier ─┐
   │           │           ▲                   │ reject
 finds       attaches    writes ◀──────────────┘  (rewrite / recover)
 moments     the numbers  the line
                               │ pass
                               ▼
                        Personalizer ─▶ Director ─▶ on air + overlay packet
```

| Agent | Responsibility |
|-------|----------------|
| **Spotter** | salience — which detected moments deserve attention |
| **Analyst** | attaches the exact supporting numbers from live state |
| **Explainer** | writes the line (Azure AI Foundry, or the offline narrator) |
| **Verifier** | checks every claim against the evidence; can bounce it back |
| **Personalizer** | renders the moment per audience |
| **Director** | puts the chosen line on air and emits the overlay packet |

Every handoff is recorded on the blackboard, so the collaboration is
inspectable — and the end-to-end outcome (a verified, personalised,
broadcast-ready overlay with its evidence) is something no single agent produces
alone.

---

## Quickstart

Runs fully offline — no API key, no cloud.

```bash
pip install -r requirements.txt
pip install -e .

truecast replay --seed 21      # run the crew over a match, print the recap
truecast serve                 # launch the live broadcast UI → http://127.0.0.1:8000
truecast generate --seed 21    # write raw synthetic match data to data/
```

---

## HTTP API

| Endpoint | Purpose |
|----------|---------|
| `GET /api/meta?seed=21` | squads, colours, narrator mode |
| `GET /api/stream?seed=21&speed=60` | SSE live feed: scoreboard ticks, aired lines, overlays |
| `GET /api/overlays?seed=21` | full machine-readable overlay timeline (rendering-partner export) |
| `GET /api/personalize?seed=21&overlay_id=ov0002&mode=club&team_id=KGS` | re-render one moment for a viewer |
| `GET /api/recap?seed=21` | end-of-match recap |
| `GET /healthz` | liveness/readiness probe |

---

## Azure AI Foundry

Set the Foundry endpoint and key (see `.env.example`) and the Explainer
delegates line-writing to your hosted model. The prompt is constrained to the
supplied facts, and output still passes through the Verifier — so a model that
drifts is caught, not trusted. If Foundry is unreachable, generation degrades to
the offline narrator and the feed keeps running.

```bash
truecast check-foundry     # verify credentials; prints OK when the model responds
```

Zero-to-live (account → Foundry model → Container Apps → demo) is in
[`AZURE_SETUP.md`](AZURE_SETUP.md). Foundry-only setup is in
[`infra/FOUNDRY_RUNBOOK.md`](infra/FOUNDRY_RUNBOOK.md); the infrastructure-as-code
path is [`infra/main.bicep`](infra/main.bicep) (see [`infra/deploy.md`](infra/deploy.md)).

---

## Tests

```bash
pytest          # 33 tests
```

Covers the generator (reproducibility, schema, xG geometry), the engine
(possession, distances, index bounds), the full crew, the API, the Foundry HTTP
path against a mock endpoint, and — most importantly — the Verifier: that
grounded lines pass and invented numbers, invented stats, and wrong players are
all rejected.

---

## Layout

```
src/truecast/
  generator/   synthetic match simulator (fictional clubs, seeded events)
  engine/      live state, metrics, explainability indices, moment detection
  agents/      the six-agent crew + orchestration
  llm/         narrative providers (offline + Azure AI Foundry)
  overlay/     machine-readable overlay packet schema
  api/         FastAPI server (SSE stream, personalize, export, health)
  cli.py       replay / serve / generate / check-foundry
web/           broadcast UI
infra/         Bicep for Azure Container Apps + Foundry runbook
tests/         pytest suite
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the data contract, the grounding
mechanism in detail, and how the crew maps to the Microsoft Agent Framework.

---

## Synthetic data

The generator produces full matches from a possession-based model: fictional
clubs and squads, realistic event sequences, xG from shot geometry, pass
difficulty, ball and player speeds, and off-ball running that brings players to
realistic match distances (~10–11 km). Every seed is reproducible byte-for-byte;
the schema is documented in `src/truecast/models.py`.

## License

MIT — see [`LICENSE`](LICENSE).
