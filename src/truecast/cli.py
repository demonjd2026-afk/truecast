"""Command-line entry point.

    truecast generate --seed 21        write a synthetic match to data/
    truecast replay   --seed 21        run the crew over a match, print recap
    truecast serve    --port 8000      launch the live API + UI
"""

from __future__ import annotations

import argparse
import json


def _replay(args) -> None:
    from .agents.crew import Truecast
    from .generator.simulator import generate_match

    meta, events = generate_match(args.seed)
    cr = Truecast(meta)
    for ev in events:
        cr.ingest(ev)
    recap = cr.recap(max_items=args.top)
    print(f"{recap['fixture']}  —  {recap['final_score']}  [{cr.mode}]")
    print(f"moments read {recap['stats']['facts_in']} | "
          f"on air {recap['stats']['aired']} | "
          f"rewritten {recap['stats']['rewrites']} | "
          f"blocked {recap['stats']['rejected']}")
    print("-" * 72)
    for m in recap["moments"]:
        tag = "✓" if m["verified"] else "✗"
        print(f"{m['clock']}  {tag}  [{m['kind']}]  {m['text']}")


def _generate(args) -> None:
    from .generator.run import write_match
    for i in range(args.count):
        print(json.dumps(write_match(args.seed + i, args.out)))


def _serve(args) -> None:
    import uvicorn
    uvicorn.run("truecast.api.server:app", host=args.host, port=args.port)


def _check_foundry(args) -> None:
    from .config import SETTINGS
    from .llm.foundry import FoundryNarrator

    print(f"configured mode: {SETTINGS.mode}")
    if SETTINGS.mode == "offline":
        print("No Foundry endpoint/key in the environment — the offline narrator "
              "will be used. Set AZURE_AI_FOUNDRY_ENDPOINT and "
              "AZURE_AI_FOUNDRY_API_KEY to enable Foundry (see .env.example).")
        return
    print(f"endpoint:   {SETTINGS.foundry_endpoint}")
    print(f"deployment: {SETTINGS.foundry_deployment}")
    h = FoundryNarrator().health()
    status = "OK" if h["ok"] else "FAILED"
    print(f"probe:      {status} — {h['detail']}")
    raise SystemExit(0 if h["ok"] else 1)


def main() -> None:
    ap = argparse.ArgumentParser(prog="truecast")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write synthetic match data")
    g.add_argument("--seed", type=int, default=21)
    g.add_argument("--count", type=int, default=1)
    g.add_argument("--out", default="data")
    g.set_defaults(func=_generate)

    r = sub.add_parser("replay", help="run the crew over a match and print the recap")
    r.add_argument("--seed", type=int, default=21)
    r.add_argument("--top", type=int, default=12)
    r.set_defaults(func=_replay)

    s = sub.add_parser("serve", help="launch the live API and UI")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=_serve)

    c = sub.add_parser("check-foundry", help="verify Azure AI Foundry credentials")
    c.set_defaults(func=_check_foundry)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
