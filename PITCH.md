# Truecast — Project Pitch

## What we built

Truecast is a live match-intelligence system for football broadcast. It ingests
a stream of synthetic match events and turns them into on-air intelligence:
real-time stats and explainability indices, the moments that matter with an
explanation of *why*, timed machine-readable overlay packets for a rendering
partner, and a different telling of the same match for every kind of viewer.

What sets it apart is that it is **evidence-grounded**. A crew of six agents
produces every line, and a dedicated Verifier agent checks each line against the
event log before it airs — rejecting any invented number, stat, or player. A
broadcaster can automate commentary graphics without risking a hallucinated stat
going out live.

## The problem it solves

Broadcast graphics must be correct. Generated commentary that invents a figure or
names the wrong scorer is unusable on air, and manual verification doesn't scale
to a live feed. Truecast makes grounding a hard guarantee rather than a hope: the
system only speaks about facts it can trace to specific events, and proves it on
every line.

## How it works

One pipeline, five stages — ingest, interpret, explain, render, personalize —
driven by a multi-agent crew (Spotter, Analyst, Explainer, Verifier,
Personalizer, Director) that shares state and hands off explicitly, including a
Verifier→Explainer rewrite path for failure recovery.

## Microsoft and Azure technologies

- **Azure AI Foundry** — hosts the narrative model the Explainer uses; the system
  runs offline with a deterministic narrator and switches to Foundry when
  configured, with graceful fallback and a `check-foundry` health probe.
- **Microsoft Agent Framework** — the crew is structured to its agent /
  shared-thread / handoff model (see ARCHITECTURE.md); it runs dependency-free
  and binds to Foundry-hosted agents by swapping the provider.
- **Azure Container Apps** — serverless, autoscaling host for the app, with
  liveness/readiness probes (Bicep in `infra/`).
- **Azure Container Registry** and **Log Analytics** — image storage and logs.

## What it demonstrates

- Real-time match intelligence: xG, possession, pass accuracy, player speed and
  distance, plus momentum, control-vs-chaos, pressure, and tempo indices.
- Narrative generation: key moments, player context, milestones, and recaps.
- Explainability: every index and line is traceable to its events.
- Data innovation: a seeded, reproducible synthetic match generator.
- Personalization: analyst, casual, club, and player-focus experiences from one feed.

## Status

Fully working end-to-end offline; Foundry-ready; 33 tests green, including tests
that prove the Verifier blocks hallucinated numbers and wrong players, and that
the Foundry HTTP path works against a mock endpoint. All data synthetic; no club
trademarks used.
