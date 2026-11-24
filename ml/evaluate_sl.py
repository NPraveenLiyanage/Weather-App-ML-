"""
Sri Lanka multi-city forecast evaluation.   myenv\\Scripts\\python.exe ml\\evaluate_sl.py

PROTOCOL (fixed before comparing models)
* Rows: (city, origin day). All cities pooled in ONE model; city identity is only lat/lon/elevation.
* Population: days with a genuine day-ahead NWP forecast (2024-03 onward).
* FINAL HOLDOUT: origin days on/after HOLDOUT_START, scored once at the end. DEV = before it.
* Selection: time-blocked K-fold on DEV (all cities share a date block), 3-day purge on each side, hyper-parameters tuned
  inside each training fold. Primary metric Brier (rain), MAE (temperature). Simplest model within 1 SE of the best wins.
* Baselines every model must beat: climatology, persistence, and the raw NWP forecast (recalibrated).
* Truth = ERA5 reanalysis, NOT gauge readings: it is a model-based estimate (known drizzle bias, so rain = >= 2.5 mm).
"""
from __future__ import annotations

import json
import os
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, mean_absolute_error, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dataset as D  # noqa: E402

HOLDOUT_START = pd.Timestamp("2025-10-01")
N_BLOCKS, GAP_DAYS, INNER_BLOCKS = 6, 3, 4

CORE_OBS = ["lat", "lon", "elev", "precip", "rh", "pressure", "cloud", "d_pressure", "precip_3d", "precip_30d", "wet_days_7", "doy_sin", "doy_cos"]
LOGIT_NWP = ["nwp_precip_mean_log", "nwp_wet_frac", "nwp_rh_mean", "nwp_pressure_delta"]


def table(only=None) -> pd.DataFrame:
    d = D.build(only)
    d = d.dropna(subset=D.NWP_FEATURES + ["rain_next", "tmax_next", "tmin_next"]).copy()
    d["nwp_precip_mean_log"] = np.log1p(d["nwp_precip_mean"])
    d["nwp_precip_max_log"] = np.log1p(d["nwp_precip_max"])
    d["month"] = d["date"].dt.month
    d = d.dropna(subset=D.OBS_FEATURES).reset_index(drop=True)
    return d


def block_splits(dates: pd.Series, k: int, gap: int):
    """Time blocks over the sorted unique dates; training excludes `gap` days either side of the test block."""
    u = np.sort(dates.unique())
    for chunk in np.array_split(u, k):
        lo, hi = chunk.min() - np.timedelta64(gap, "D"), chunk.max() + np.timedelta64(gap, "D")
        d = dates.to_numpy()
        yield np.where((d < lo) | (d > hi))[0], np.where((d >= chunk.min()) & (d <= chunk.max()))[0]


# ------------------------------------------------------------- baselines (fit on training rows only)
class Climatology:
    """P(rain) = training rate for the same city and month."""
    def __init__(self, target): self.t = target
    def fit(self, df): self.r = df.groupby(["city", "month"])[self.t].mean(); self.g = df[self.t].mean(); return self
    def predict_proba(self, df): return np.array([self.r.get((c, m), self.g) for c, m in zip(df["city"], df["month"])])


class FeatLogit:
    """Logistic regression on a column list (standardised)."""
    def __init__(self, cols, target, C=1.0): self.cols, self.t, self.C = cols, target, C
    def fit(self, df): self.m = make_pipeline(StandardScaler(), LogisticRegression(C=self.C, max_iter=5000)).fit(df[self.cols], df[self.t]); return self
    def predict_proba(self, df): return self.m.predict_proba(df[self.cols])[:, 1]


class FeatHGB:
    def __init__(self, cols, target, **kw): self.cols, self.t, self.kw = cols, target, kw
    def fit(self, df):
        self.m = HistGradientBoostingClassifier(random_state=0, max_iter=200, learning_rate=0.05, **self.kw).fit(df[self.cols], df[self.t]); return self
    def predict_proba(self, df): return self.m.predict_proba(df[self.cols])[:, 1]


def rain_candidates(target):
    obs, nwp = D.OBS_FEATURES, D.NWP_FEATURES + ["nwp_precip_mean_log", "nwp_precip_max_log"]
    return {
        "climatology (city x month)": ("baseline", 0, [lambda: Climatology(target)]),
        "persistence (rained today?)": ("baseline", 1, [lambda c=c: FeatLogit(["wet_days_7", "precip"], target, c) for c in (1.0,)]),
        "raw forecast, recalibrated": ("baseline", 2, [lambda c=c: FeatLogit(LOGIT_NWP, target, c) for c in (0.1, 1.0)]),
        "observations only (HGB)": ("serveable", 5, [lambda d=d, l=l: FeatHGB(obs, target, max_depth=d, l2_regularization=l, min_samples_leaf=40) for d in (3, 5) for l in (1.0, 10.0)]),
        "MOS logistic (forecast + core obs)": ("serveable", 3, [lambda c=c: FeatLogit(CORE_OBS + nwp, target, c) for c in (0.03, 0.1, 0.3, 1.0)]),
        "MOS gradient boosting (all)": ("serveable", 6, [lambda d=d, l=l: FeatHGB(obs + nwp, target, max_depth=d, l2_regularization=l, min_samples_leaf=40) for d in (3, 5) for l in (1.0, 10.0)]),
    }


def tune_fit(factories, df, train_idx, target):
    """Inner time-blocked CV chooses the factory (hyper-parameters) by Brier; refit on all training rows."""
    best, best_s = None, 9.0
    tr_df = df.iloc[train_idx]
    for make in factories:
        if len(factories) == 1:
            best = make
            break
        ps, ys = [], []
        for a, b in block_splits(tr_df["date"].reset_index(drop=True), INNER_BLOCKS, GAP_DAYS):
            if tr_df.iloc[a][target].sum() < 5:
                continue
            ps.append(make().fit(tr_df.iloc[a]).predict_proba(tr_df.iloc[b])); ys.append(tr_df.iloc[b][target].to_numpy())
        s = brier_score_loss(np.concatenate(ys), np.concatenate(ps))
        if s < best_s:
            best, best_s = make, s
    return best().fit(tr_df)


def rain_metrics(y, p, base):
    return {"brier": brier_score_loss(y, p), "logloss": log_loss(y, np.clip(p, 1e-4, 1 - 1e-4)), "auc": roc_auc_score(y, p), "ap": average_precision_score(y, p),
            "bss": 1 - brier_score_loss(y, p) / brier_score_loss(y, np.full_like(p, base))}


def run_rain(df, target, label):
    dev = df[df["date"] < HOLDOUT_START].reset_index(drop=True)
    out = {}
    for name, (family, cx, factories) in rain_candidates(target).items():
        folds = []
        for tr, te in block_splits(dev["date"], N_BLOCKS, GAP_DAYS):
            m = tune_fit(factories, dev, tr, target)
            p = m.predict_proba(dev.iloc[te])
            folds.append(rain_metrics(dev.iloc[te][target].to_numpy(), p, dev.iloc[tr][target].mean()))
        b = np.array([f["brier"] for f in folds])
        out[name] = {"family": family, "cx": cx, "brier": float(b.mean()), "se": float(b.std(ddof=1) / np.sqrt(len(b))),
                     **{k: float(np.mean([f[k] for f in folds])) for k in ("logloss", "auc", "ap", "bss")}}
    print(f"\n=== {label}: blocked nested CV on DEV ({dev['date'].min().date()} -> {dev['date'].max().date()}, {len(dev)} rows, rain rate {dev[target].mean():.2f}) ===")
    print(f"{'model':38s} {'Brier':>6s} {'+-SE':>5s} {'skill':>6s} {'logloss':>7s} {'AUC':>5s} {'PR-AUC':>6s}")
    for n, r in sorted(out.items(), key=lambda kv: kv[1]["brier"]):
        print(f"{n:38s} {r['brier']:6.3f} {r['se']:5.3f} {r['bss']:6.2f} {r['logloss']:7.3f} {r['auc']:5.3f} {r['ap']:6.3f}")
    return out


# ------------------------------------------------------------- temperature
def run_temp(df, target, nwp_col, label):
    dev = df[df["date"] < HOLDOUT_START].reset_index(drop=True)
    feats = D.OBS_FEATURES + D.NWP_FEATURES + ["nwp_precip_mean_log"]
    res = {k: [] for k in ("persistence", "climatology (city x month)", "raw forecast", "raw forecast, bias-corrected", "MOS gradient boosting")}
    for tr, te in block_splits(dev["date"], N_BLOCKS, GAP_DAYS):
        a, b = dev.iloc[tr], dev.iloc[te]
        y = b[target].to_numpy()
        res["persistence"].append(mean_absolute_error(y, b["tmax" if target == "tmax_next" else "tmin"]))
        clim = a.groupby(["city", "month"])[target].mean()
        res["climatology (city x month)"].append(mean_absolute_error(y, [clim.get((c, m), a[target].mean()) for c, m in zip(b["city"], b["month"])]))
        res["raw forecast"].append(mean_absolute_error(y, b[nwp_col]))
        bias = Ridge(alpha=1.0).fit(a[[nwp_col, "lat", "elev"]], a[target])
        res["raw forecast, bias-corrected"].append(mean_absolute_error(y, bias.predict(b[[nwp_col, "lat", "elev"]])))
        g = HistGradientBoostingRegressor(random_state=0, max_iter=250, learning_rate=0.05, max_depth=4, l2_regularization=5.0, min_samples_leaf=40).fit(a[feats], a[target] - a[nwp_col])
        res["MOS gradient boosting"].append(mean_absolute_error(y, b[nwp_col] + g.predict(b[feats])))
    print(f"\n=== {label}: MAE in deg C (lower is better), DEV ===")
    for n, v in sorted(res.items(), key=lambda kv: np.mean(kv[1])):
        print(f"{n:38s} {np.mean(v):5.2f}  (+-{np.std(v, ddof=1) / np.sqrt(len(v)):.2f})")
    return {n: float(np.mean(v)) for n, v in res.items()}


if __name__ == "__main__":
    only = sys.argv[1:] or None
    df = table(only)
    print(f"{df['city'].nunique()} cities, {len(df)} rows, {df['date'].min().date()} -> {df['date'].max().date()}; holdout starts {HOLDOUT_START.date()}")
    r1 = run_rain(df, "rain_next", "RAIN >= 2.5 mm tomorrow")
    r2 = run_rain(df, "heavy_next", "HEAVY RAIN >= 10 mm tomorrow")
    t1 = run_temp(df, "tmax_next", "nwp_tmax_mean", "TOMORROW'S HIGH")
    t2 = run_temp(df, "tmin_next", "nwp_tmin_mean", "TOMORROW'S LOW")
    json.dump({"rain": r1, "heavy": r2, "tmax_mae": t1, "tmin_mae": t2}, open(os.path.join(HERE, "cv_results_sl.json"), "w"), indent=2)
