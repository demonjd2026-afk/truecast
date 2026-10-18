# Architecture

Truecast is a streaming pipeline with a multi-agent crew at its centre. Raw
synthetic events go in; verified, personalised, broadcast-ready match
intelligence comes out, in two forms: human-readable lines for each audience and
machine-readable overlay packets for a rendering partner.

```
events ─▶ engine (state + indices) ─▶ moment detection (Facts)
                                            │
                                            ▼
                         Spotter ▸ Analyst ▸ Explainer ▸ Verifier
                                            │                 │ reject ↺
                                            ▼                 │
                                     Personalizer ◀───────────┘
                                            │
                                            ▼
                                        Director ─▶ feed + overlay packets
```

## Data contract (`models.py`)

Everything that crosses a stage boundary is defined in one place.

- **Event** — one synthetic match event. Coordinates are in metres on a 105×68
  pitch, normalised to the possessing team's attacking direction, so distance
  and angle to goal are direction-independent. `wall_ts` is stamped only when an
  event is streamed, so a seed reproduces byte-for-byte.
- **Fact** — a neutral, machine-checkable statement with the event IDs that
  justify it, an importance score, and the structured numbers behind it. Agents
  may only ever speak about Facts.

This is the central design decision: natural language is generated *from* Facts
and checked *against* their evidence, rather than generated freely and trusted.

## Engine (`engine/`)

`state.py` ingests events incrementally and maintains team tallies, per-player
stats, possession time, and off-ball distance (a steady per-player baseline on
top of on-ball movement, so players reach realistic ~10–11 km totals).

`indices.py` computes the explainability indices over a rolling 150-second
window:

| Index | Meaning |
|-------|---------|
| momentum (−1…+1) | which team the game is flowing toward, from weighted recent events |
| control (0…1 per team) | completed build-up vs turnovers conceded |
| chaos (0…1) | turnovers per minute across the window |
| pressure (per team) | defensive pressure intensity |
| tempo | on-ball actions per minute |

`moments.py` watches the stream and emits Facts for goals, big chances, saves,
momentum shifts, control spells, pressure build-ups, and milestones, with
cooldowns so the feed surfaces what matters instead of every touch.

`metrics.py` holds the stateless formulas shared with the generator (xG from
shot geometry, pass difficulty, unit conversions) so a number is computed in
exactly one place.

## The crew (`agents/`)

Each agent has one responsibility and shares the `Blackboard`:

1. **Spotter** — salience filtering and context (equaliser, lead change, quiet spell).
2. **Analyst** — attaches exact supporting numbers from live state; these become the Verifier's allow-list.
3. **Explainer** — asks the active provider for a persona-shaped line; exposes a deterministic `recover()` path for rewrites.
4. **Verifier** — see below.
5. **Personalizer** — runs Explainer→Verifier once per persona, with the rewrite/recover loop.
6. **Director** — selects the on-air line and emits the overlay packet.

`crew.py` wires them behind a single `ingest(event)` call and exposes
`snapshot()` and `recap()`.

### The Verifier (`agents/verifier.py`)

The Verifier builds an allow-list and rejects anything outside it:

- **Numbers** — every figure in the Fact and the Analyst's packet, plus the clock
  and scoreline, expanded with the transforms a line might legitimately use
  (1- and 2-dp rounding, integer, and fraction→percentage). A scoreline like
  `2-3` is tokenised as 2 and 3, never as 2 and −3.
- **Names** — only the player and team names tied to this moment's Fact. A roster
  player who was not part of the moment is flagged.

Any number or name in a line that falls outside the allow-list is an unsupported
claim and the line is rejected. This is what makes output safe for a live feed:
an invented stat never reaches air, whether it came from a template bug or a
drifting model. Three unit tests pin this down — an invented number, an invented
stat, and a wrong player are each rejected, while scorelines and clocks are not.

### Failure recovery

When the Verifier rejects a line it is handed back to the Explainer (recorded as
a `Verifier → Explainer` handoff). The Explainer's recovery path uses the
deterministic narrator, which composes only from supplied figures and is grounded
by construction. If even that fails, the line falls back to the Fact's neutral
text, which cannot contain an unsupported claim. The feed never airs an
unverified line and never stalls.

### Mapping to the Microsoft Agent Framework

The crew is implemented directly so it runs with no cloud dependency, but it is
structured to match the Agent Framework's model: each agent is a single-purpose
agent, the `Blackboard` is the shared thread/state, and `Blackboard.handoff()`
records the explicit agent-to-agent handoffs the framework formalises. Moving to
Foundry-hosted agents means swapping the provider and binding each agent class to
a framework agent — the orchestration shape is unchanged. This is a deliberate
mapping, not a dependency: Truecast does not import the framework, so the claim
is "ready for" it, not "requires" it.

## Narrative providers (`llm/`)

`provider.py` defines one contract — turn a Fact plus vetted numbers into one
line for a persona. Two implementations:

- **OfflineNarrator** — deterministic, template-driven, no network; grounded by
  construction. The default, so demos always work.
- **FoundryNarrator** — delegates to a chat model on Azure AI Foundry with a
  strict prompt, degrades to offline on any error, and exposes `health()` for the
  `check-foundry` command. Credentials can be injected, which is what makes the
  HTTP path unit-testable against a mock endpoint.

Because both return a single line built from the same inputs, the Verifier
checks either identically.

## Overlay packets (`overlay/schema.py`)

Each aired moment produces one `OverlayPacket`: a timed, typed, priority-ranked
graphic with a headline, the persona variants, the backing data, the evidence
event IDs, and a verified flag. A rendering partner maps `template` to its own
graphics and picks the variant for each viewer's chosen mode. `GET /api/overlays`
exports the full timeline.

## Personalization (`personas.py`)

Analyst and casual are always produced for the live feed; club-focused (per team)
and player-focused variants are rendered on demand. Player focus also filters the
feed to a chosen player — the "follow one player through the match" mode.

## API (`api/server.py`)

FastAPI. `/api/stream` replays a match through the crew in accelerated real time
and pushes server-sent events: periodic scoreboard/index snapshots, each aired
line, and the overlay packet behind it. `/healthz` backs the container liveness
and readiness probes.

## Trained models (`ml/`)

Two scikit-learn models are trained offline on simulated matches (`ml/train.py`)
and deployed as compact JSON artifacts (`ml/models/*.json`). Runtime inference is
pure-Python (`ml/winprob.py`, `ml/xgmodel.py`), so the container needs no ML
dependency and the models load instantly; both fall back to a closed form if an
artifact is missing.

- **Live win probability** — multinomial logistic over home/draw/away, from
  features (minute, score diff, xG diff, shots diff, momentum, possession diff)
  sampled at 5-minute intervals across matches. The simulator has no explicit
  win-probability function, so the model learns an emergent relationship; held
  out by match, it reaches ~67% accuracy / 0.71 log-loss. The engine evaluates it
  every tick and the UI renders it as the win-probability ribbon.
- **xG** — logistic regression on shot features (distance, angle, header,
  big-chance, under-pressure). It recovers the generator's conversion function —
  the same workflow a real xG model uses on event data — at Brier 0.07 / AUC 0.80.
  The engine uses it for the displayed xG on the shot map and the team totals; the
  generator keeps its own internal value as the data-generating "ground truth."

`GET /api/models` exposes provenance and metrics, which the UI surfaces in the
production panel.

Training splits by match, never by row, so no match leaks across train/test.

## Why multi-agent

A single model prompt could draft commentary, but it could not separate *finding*
a moment from *quantifying* it from *writing* it from *checking* it from
*adapting* it — and it could not give an auditable guarantee that nothing
invented reached air. Splitting these into agents with a shared blackboard and an
explicit verification handoff is what makes the output both trustworthy and
inspectable.
