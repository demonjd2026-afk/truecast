"""Train the xG and live win-probability models on simulated matches.

Run:  python -m truecast.ml.train --matches 400

Trains two scikit-learn logistic models, prints held-out metrics, and writes
compact JSON artifacts to ml/models/ for the pure-Python runtime to load.
Training is split by match (not by row) so no match leaks across train/test.
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, brier_score_loss, log_loss,
                             roc_auc_score)
from sklearn.preprocessing import StandardScaler

from ..engine.metrics import shot_geometry
from ..generator.simulator import generate_match
from .features import WINPROB_FEATURES, XG_FEATURES

_DIR = os.path.join(os.path.dirname(__file__), "models")
SAMPLE_EVERY_MIN = 5


def _shot_rows(seed: int):
    _, events = generate_match(seed)
    goal_shots = {e.detail.get("shot_event") for e in events if e.type == "goal"}
    rows = []
    for e in events:
        if e.type != "shot":
            continue
        dist, angle = shot_geometry(e.x, e.y)
        rows.append((
            [dist, angle,
             1.0 if e.detail.get("body_part") == "head" else 0.0,
             1.0 if e.detail.get("big_chance") else 0.0,
             1.0 if e.detail.get("under_pressure") else 0.0],
            1 if e.event_id in goal_shots else 0,
        ))
    return rows


def _winprob_rows(seed: int):
    from ..engine.state import MatchState  # imported after xG artifact exists

    meta, events = generate_match(seed)
    st = MatchState(meta)
    gh = sum(1 for e in events if e.type == "goal" and e.team_id == meta.home.team_id)
    ga = sum(1 for e in events if e.type == "goal" and e.team_id == meta.away.team_id)
    result = "home" if gh > ga else ("away" if ga > gh else "draw")

    rows = []
    next_min = SAMPLE_EVERY_MIN
    for e in events:
        st.apply(e)
        minute = (st.period - 1) * 45 + st.clock_s / 60.0
        if minute >= next_min:
            h, a = st.teams[st.home_id], st.teams[st.away_id]
            poss = st.possession_pct()
            rows.append((
                [minute, h.goals - a.goals, round(h.xg - a.xg, 3),
                 h.shots - a.shots, st.idx.momentum(),
                 poss.get(st.home_id, 50) - poss.get(st.away_id, 50)],
                result,
            ))
            next_min += SAMPLE_EVERY_MIN
    return rows


def _export_binary(path, scaler, clf, features, metrics):
    art = {
        "type": "logistic", "features": features,
        "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
        "coef": clf.coef_[0].tolist(), "intercept": float(clf.intercept_[0]),
        "metrics": metrics,
    }
    with open(path, "w") as f:
        json.dump(art, f, indent=2)


def _export_multinomial(path, scaler, clf, features, metrics):
    art = {
        "type": "multinomial_logistic", "features": features,
        "classes": list(clf.classes_),
        "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
        "coef": clf.coef_.tolist(), "intercept": clf.intercept_.tolist(),
        "metrics": metrics,
    }
    with open(path, "w") as f:
        json.dump(art, f, indent=2)


def _collect(seeds, rowfn):
    X, y = [], []
    for s in seeds:
        for feat, lab in rowfn(s):
            X.append(feat)
            y.append(lab)
    return X, y


def train_xg(seeds_train, seeds_test) -> dict:
    Xtr, ytr = _collect(seeds_train, _shot_rows)
    Xte, yte = _collect(seeds_test, _shot_rows)
    scaler = StandardScaler().fit(Xtr)
    clf = LogisticRegression(max_iter=2000).fit(scaler.transform(Xtr), ytr)
    p = clf.predict_proba(scaler.transform(Xte))[:, 1]
    metrics = {
        "n_train": len(ytr), "n_test": len(yte),
        "brier": round(brier_score_loss(yte, p), 4),
        "auc": round(roc_auc_score(yte, p), 4),
        "log_loss": round(log_loss(yte, p), 4),
    }
    os.makedirs(_DIR, exist_ok=True)
    _export_binary(os.path.join(_DIR, "xg.json"), scaler, clf, XG_FEATURES, metrics)
    print("xG model:", metrics)
    return metrics


def train_winprob(seeds_train, seeds_test) -> dict:
    Xtr, ytr = _collect(seeds_train, _winprob_rows)
    Xte, yte = _collect(seeds_test, _winprob_rows)
    scaler = StandardScaler().fit(Xtr)
    clf = LogisticRegression(max_iter=3000).fit(scaler.transform(Xtr), ytr)
    proba = clf.predict_proba(scaler.transform(Xte))
    preds = clf.predict(scaler.transform(Xte))
    metrics = {
        "n_train": len(ytr), "n_test": len(yte),
        "classes": list(clf.classes_),
        "accuracy": round(accuracy_score(yte, preds), 4),
        "log_loss": round(log_loss(yte, proba, labels=list(clf.classes_)), 4),
    }
    _export_multinomial(os.path.join(_DIR, "winprob.json"), scaler, clf,
                        WINPROB_FEATURES, metrics)
    print("win-prob model:", metrics)
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", type=int, default=400)
    args = ap.parse_args()
    seeds = list(range(1, args.matches + 1))
    cut = int(len(seeds) * 0.8)
    tr, te = seeds[:cut], seeds[cut:]

    train_xg(tr, te)
    # Reset caches so win-prob replay uses the freshly trained xG model.
    import truecast.ml.winprob as wp
    import truecast.ml.xgmodel as xm
    xm._MODEL = None
    wp._MODEL = None
    train_winprob(tr, te)


if __name__ == "__main__":
    main()
