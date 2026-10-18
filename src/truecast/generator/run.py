"""CLI: generate one or more synthetic matches to data/ as JSONL + meta."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict

from ..models import dumps
from .simulator import generate_match


def write_match(seed: int, out_dir: str) -> dict:
    meta, events = generate_match(seed)
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, meta.match_id)
    with open(f"{base}.events.jsonl", "w") as f:
        for ev in events:
            f.write(ev.to_json() + "\n")
    with open(f"{base}.meta.json", "w") as f:
        f.write(dumps(meta.to_public()))
    summary = {
        "match_id": meta.match_id,
        "fixture": f"{meta.home.name} vs {meta.away.name}",
        "events": len(events),
        "score": {
            meta.home.short_name: sum(
                1 for e in events if e.type == "goal" and e.team_id == meta.home.team_id
            ),
            meta.away.short_name: sum(
                1 for e in events if e.type == "goal" and e.team_id == meta.away.team_id
            ),
        },
    }
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic football matches")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--out", default="data")
    args = ap.parse_args()
    for i in range(args.count):
        s = args.seed + i
        print(json.dumps(write_match(s, args.out)))


if __name__ == "__main__":
    main()
