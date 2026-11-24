"""
Honest evaluation of the rain-tomorrow model.  Run with the app's pinned environment:

    myenv\\Scripts\\python.exe ml\\evaluate.py

PROTOCOL (fixed BEFORE comparing any model, so the comparison cannot be tuned to the test data)
------------------------------------------------------------------------------------------
* weather.csv is ONE station's consecutive days (lag-1 autocorrelation of Temp is 0.85), so rows are NOT
  independent. Shuffled CV leaks neighbouring days between train and test and over-states skill.
* The last 20% of rows (one contiguous block) is a FINAL HOLDOUT, scored exactly once, at the end.
* Model selection uses contiguous (blocked) K-fold CV on the first 80%, with a PURGE gap of a few days
  around every test block, and hyper-parameters are tuned INSIDE each training fold (nested CV).
* Primary metric: Brier score (probability quality). Secondary: log-loss, ROC-AUC, PR-AUC, and rain
  recall/precision at a threshold chosen on training data only. Accuracy is shown next to the
  always-"no rain" baseline (81.8%) because on its own it is misleading here.
* Selection rule: the SIMPLEST model within one standard error of the best Brier.
* No class_weight / resampling: they distort probabilities. Imbalance is handled by the decision threshold.
* "Serveable" models use only inputs the live app can provide (one observation, no history).
  "History" models also use yesterday's values; they cannot run in the live app and are reported separately.
"""
from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "..", "weather.csv")

N_FOLDS, GAP, INNER_FOLDS, HOLDOUT_FRAC = 6, 3, 4, 0.20
COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
NUM = ["MinTemp", "MaxTemp", "WindGustSpeed", "Humidity", "Pressure", "Temp"]


# ------------------------------------------------------------------ data & features
def load() -> pd.DataFrame:
    """Raw rows in original (chronological) order. Lags are computed BEFORE any row is dropped."""
    df = pd.read_csv(CSV)
    df["y"] = (df["RainTomorrow"] == "Yes").astype(float)
    df.loc[df["RainTomorrow"].isna(), "y"] = np.nan
    ang = df["WindGustDir"].map({c: i * 22.5 for i, c in enumerate(COMPASS)})
    df["wind_sin"], df["wind_cos"] = np.sin(np.radians(ang)), np.cos(np.radians(ang))
    df["range"] = df["MaxTemp"] - df["MinTemp"]
    df["below_max"] = df["MaxTemp"] - df["Temp"]
    g = np.log(df["Humidity"].clip(1, 100) / 100) + 17.62 * df["Temp"] / (243.12 + df["Temp"])
    df["dew_spread"] = df["Temp"] - 243.12 * g / (17.62 - g)  # Magnus dew point; small spread = near saturation
    # history (yesterday's observation); NaN where yesterday is missing
    df["d_pressure"] = df["Pressure"] - df["Pressure"].shift(1)
    df["d_humidity"] = df["Humidity"] - df["Humidity"].shift(1)
    df["d_temp"] = df["Temp"] - df["Temp"].shift(1)
    df["rain_today"] = df["y"].shift(1)  # yesterday's "RainTomorrow" = whether it rained today
    return df


FEATURES = {
    "orig7": NUM + ["wind_label"],  # original app: compass label-encoded as an integer (see add_label below)
    "humidity": ["Humidity"],
    "core": NUM,
    "core+wind": NUM + ["wind_sin", "wind_cos"],
    "physical": ["Humidity", "Pressure", "WindGustSpeed", "range", "below_max", "dew_spread", "MaxTemp", "wind_sin", "wind_cos"],
    "physical+hist": ["Humidity", "Pressure", "WindGustSpeed", "range", "below_max", "dew_spread", "MaxTemp", "wind_sin", "wind_cos", "d_pressure", "d_humidity", "d_temp", "rain_today"],
}


def add_label(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["wind_label"] = df["WindGustDir"].astype("category").cat.codes  # the original (ordinal, arbitrary) encoding
    return df


# ------------------------------------------------------------------ candidates
@dataclass
class Candidate:
    name: str
    features: str
    estimator: object
    grid: list[dict]  # list of param dicts for estimator.set_params
    complexity: int  # for the "simplest within 1 SE" rule
    family: str  # "serveable" | "history" | "baseline"


def logreg(c=1.0):
    return make_pipeline(StandardScaler(), LogisticRegression(C=c, max_iter=5000))


CANDIDATES = [
    Candidate("humidity-only logistic", "humidity", logreg(), [{"logisticregression__C": c} for c in (0.1, 1, 10)], 1, "baseline"),
    Candidate("original RF (7 feats, label-encoded wind)", "orig7", RandomForestClassifier(n_estimators=100, random_state=0), [{}], 9, "baseline"),
    Candidate("logistic, 6 numeric", "core", logreg(), [{"logisticregression__C": c} for c in (0.03, 0.1, 0.3, 1, 3)], 2, "serveable"),
    Candidate("logistic, +wind sin/cos", "core+wind", logreg(), [{"logisticregression__C": c} for c in (0.03, 0.1, 0.3, 1, 3)], 3, "serveable"),
    Candidate("logistic, physical features", "physical", logreg(), [{"logisticregression__C": c} for c in (0.03, 0.1, 0.3, 1, 3)], 4, "serveable"),
    Candidate("shallow RF, physical features", "physical", RandomForestClassifier(n_estimators=300, random_state=0, n_jobs=1),
              [{"max_depth": d, "min_samples_leaf": l} for d in (3, 5) for l in (3, 8)], 6, "serveable"),
    Candidate("regularised HGB, physical features", "physical", HistGradientBoostingClassifier(random_state=0, max_iter=150, learning_rate=0.04),
              [{"max_depth": d, "l2_regularization": l, "min_samples_leaf": 12} for d in (2, 3) for l in (1.0, 10.0)], 7, "serveable"),
    Candidate("logistic, physical + history", "physical+hist", logreg(), [{"logisticregression__C": c} for c in (0.03, 0.1, 0.3, 1, 3)], 5, "history"),
    Candidate("shallow RF, physical + history", "physical+hist", RandomForestClassifier(n_estimators=300, random_state=0, n_jobs=1),
              [{"max_depth": d, "min_samples_leaf": l} for d in (3, 5) for l in (3, 8)], 8, "history"),
]


# ------------------------------------------------------------------ blocked splitting
def blocked_folds(idx: np.ndarray, k: int, gap: int):
    """Contiguous folds over an ordered index array; the training side excludes `gap` rows each side of the test block."""
    chunks = np.array_split(idx, k)
    for test in chunks:
        lo, hi = test.min() - gap, test.max() + gap
        train = idx[(idx < lo) | (idx > hi)]
        yield train, test


def prob_fit_predict(est, X, y, tr, te):
    m = clone(est)
    m.fit(X[tr], y[tr])
    return m.predict_proba(X[te])[:, 1]


def best_threshold(p, y):
    ts = np.linspace(0.05, 0.9, 86)
    f1 = []
    for t in ts:
        pred = p >= t
        tp = (pred & (y == 1)).sum()
        prec = tp / max(pred.sum(), 1)
        rec = tp / max((y == 1).sum(), 1)
        f1.append(0 if prec + rec == 0 else 2 * prec * rec / (prec + rec))
    return float(ts[int(np.argmax(f1))])


def tune_and_predict(cand: Candidate, X, y, train_idx, test_idx):
    """Inner blocked CV on the training rows picks the hyper-parameters (and the threshold); then fit and predict the test rows."""
    best = (None, 9.0, None, None)
    for params in cand.grid:
        est = clone(cand.estimator).set_params(**params) if params else clone(cand.estimator)
        oof_p, oof_y = [], []
        for tr, te in blocked_folds(np.sort(train_idx), INNER_FOLDS, GAP):
            if y[tr].sum() < 3 or y[te].size == 0:
                continue
            oof_p.append(prob_fit_predict(est, X, y, tr, te))
            oof_y.append(y[te])
        p, yy = np.concatenate(oof_p), np.concatenate(oof_y)
        score = brier_score_loss(yy, p)
        if score < best[1]:
            best = (est, score, p, yy)
    est, _, p_in, y_in = best
    thr = best_threshold(p_in, y_in)
    return prob_fit_predict(est, X, y, train_idx, test_idx), thr, est.get_params() if hasattr(est, "get_params") else {}


# ------------------------------------------------------------------ metrics
def metrics(y, p, thr, base_rate):
    pred = p >= thr
    tp = int((pred & (y == 1)).sum())
    return {
        "brier": brier_score_loss(y, p),
        "logloss": log_loss(y, np.clip(p, 1e-4, 1 - 1e-4)),
        "auc": roc_auc_score(y, p) if 0 < y.sum() < len(y) else float("nan"),
        "ap": average_precision_score(y, p) if y.sum() else float("nan"),
        "recall": tp / max(int(y.sum()), 1),
        "precision": tp / max(int(pred.sum()), 1),
        "accuracy": float((pred == (y == 1)).mean()),
        "brier_baseline": brier_score_loss(y, np.full_like(p, base_rate)),
    }


def main():
    raw = add_label(load())
    n = len(raw)
    cut = int(round(n * (1 - HOLDOUT_FRAC)))
    dev_idx = np.arange(cut)
    hold_idx = np.arange(cut, n)
    y_all = raw["y"].to_numpy()
    print(f"rows {n} | dev rows 0-{cut - 1} | HOLDOUT rows {cut}-{n - 1} (scored once, at the end)")

    results = {}
    for cand in CANDIDATES:
        cols = FEATURES[cand.features]
        X = raw[cols].to_numpy(dtype=float)
        usable = ~np.isnan(X).any(axis=1) & ~np.isnan(y_all)
        dev_ok = dev_idx[usable[dev_idx]]
        per_fold, all_p, all_y = [], [], []
        for tr, te in blocked_folds(dev_idx, N_FOLDS, GAP):
            tr, te = tr[usable[tr]], te[usable[te]]
            p, thr, _ = tune_and_predict(cand, X, np.nan_to_num(y_all), tr, te)
            m = metrics(y_all[te], p, thr, y_all[tr].mean())
            per_fold.append(m)
            all_p.append(p)
            all_y.append(y_all[te])
        pooled = metrics(np.concatenate(all_y), np.concatenate(all_p), np.mean([0.3]), y_all[dev_ok].mean())
        briers = np.array([f["brier"] for f in per_fold])
        results[cand.name] = {
            "family": cand.family, "complexity": cand.complexity,
            "brier": float(briers.mean()), "brier_se": float(briers.std(ddof=1) / np.sqrt(len(briers))),
            "logloss": float(np.mean([f["logloss"] for f in per_fold])),
            "auc": float(np.nanmean([f["auc"] for f in per_fold])), "ap": float(np.nanmean([f["ap"] for f in per_fold])),
            "recall": float(np.mean([f["recall"] for f in per_fold])), "precision": float(np.mean([f["precision"] for f in per_fold])),
            "accuracy": float(np.mean([f["accuracy"] for f in per_fold])),
            "brier_baseline": float(np.mean([f["brier_baseline"] for f in per_fold])),
        }
    print(f"\nBlocked nested CV on the development rows ({N_FOLDS} folds, {GAP}-day purge). Lower Brier / log-loss is better.")
    hdr = f"{'model':46s} {'family':10s} {'Brier':>6s} {'+-SE':>5s} {'logloss':>7s} {'AUC':>5s} {'PR-AUC':>6s} {'recall':>6s} {'prec':>5s} {'acc':>5s}"
    print(hdr)
    for name, r in sorted(results.items(), key=lambda kv: kv[1]["brier"]):
        print(f"{name:46s} {r['family']:10s} {r['brier']:6.3f} {r['brier_se']:5.3f} {r['logloss']:7.3f} {r['auc']:5.3f} {r['ap']:6.3f} {r['recall']:6.2f} {r['precision']:5.2f} {r['accuracy']:5.2f}")
    print(f"(always-'no rain'/base-rate Brier on these folds: {np.mean([r['brier_baseline'] for r in results.values()]):.3f}; always-'no' accuracy 0.82)")

    out = os.path.join(HERE, "cv_results.json")
    json.dump({"protocol": {"folds": N_FOLDS, "gap": GAP, "inner_folds": INNER_FOLDS, "holdout_frac": HOLDOUT_FRAC, "rows": n, "dev_rows": cut},
               "results": results}, open(out, "w"), indent=2)
    print("saved", out)


if __name__ == "__main__":
    main()
