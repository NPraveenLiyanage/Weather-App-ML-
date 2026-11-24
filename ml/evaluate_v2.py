"""
v2 experiment: does an 8-model consensus beat the shipped 3-model model?   myenv\\Scripts\\python.exe ml\\evaluate_v2.py

PRE-COMMITMENT (written before running): the v1 holdout (2025-10 to 2026-11) was scored and published, so it cannot judge v2.
  * Selection uses blocked nested CV on data BEFORE 2026-08-29 only.
  * A fresh holdout, 2026-09-01 to the last day, is scored once (3-day purge before it).  It is short and covers one season.
  * v1 (3 models) is RE-TRAINED on exactly the same window so the comparison is fair.
  * Brier's standard error is ~0.008 for rain, so a small gain may sit inside noise. If so, that is what gets reported.
"""
from __future__ import annotations

import json
import os
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, mean_absolute_error, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dataset as D  # noqa: E402
import evaluate_sl as E  # noqa: E402
import features as F  # noqa: E402

DEV_END = pd.Timestamp("2026-08-28")
HOLD_START = pd.Timestamp("2026-09-01")
RNG = np.random.default_rng(1)

V1 = ["nwp_precip_mean_log", "nwp_wet_frac", "nwp_rh_mean", "nwp_pressure_delta"]
V2A = ["nwpx_precip_log_mean", "nwpx_wet_frac", "nwp_rh_mean", "nwp_pressure_delta"]
V2B = V2A + ["nwpx_precip_log_std"]
PER_MODEL = [f"{m}_plog" for m in F.MODELS_ALL] + ["nwp_rh_mean", "nwp_pressure_delta"]
OBS = D.OBS_FEATURES
TEMP_V1 = OBS + D.NWP_FEATURES + ["nwp_precip_mean_log"]
TEMP_V2 = OBS + D.NWP_FEATURES + ["nwp_precip_mean_log"] + F.NWPX_FEATURES + [f"{m}_tmax_d" for m in F.MODELS_ALL]


def table():
    d = D.build()
    d = d.dropna(subset=D.NWP_FEATURES + [c for c in F.NWPX_FEATURES if c not in ("nwpx_precip_log_std",)] + ["rain_next", "heavy_next", "tmax_next", "tmin_next"] + D.OBS_FEATURES).copy()
    d["nwpx_precip_log_std"] = d["nwpx_precip_log_std"].fillna(0)
    d["nwp_precip_mean_log"] = np.log1p(d["nwp_precip_mean"])
    d["month"] = d["date"].dt.month
    for m in F.MODELS_ALL:
        d[f"{m}_plog"] = np.log1p(d[f"{m}_precip"].clip(lower=0)).fillna(d["nwpx_precip_log_mean"])  # a missing model counts as "the consensus"
        d[f"{m}_tmax_d"] = (d[f"{m}_tmax"] - d["nwpx_tmax_mean"]).fillna(0.0)
    return d.reset_index(drop=True)


def fit_logit(df, cols, target, C):
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=5000)).fit(df[cols], df[target])


def cv_brier(dev, cols, target):
    best = (9, None)
    for C in (0.03, 0.1, 0.3, 1.0):
        ps, ys = [], []
        for a, b in E.block_splits(dev["date"], E.N_BLOCKS, E.GAP_DAYS):
            ps.append(fit_logit(dev.iloc[a], cols, target, C).predict_proba(dev.iloc[b][cols])[:, 1]); ys.append(dev.iloc[b][target].to_numpy())
        y, p = np.concatenate(ys), np.concatenate(ps)
        fold = [brier_score_loss(yy, pp) for yy, pp in zip(ys, ps)]
        if np.mean(fold) < best[0]:
            best = (float(np.mean(fold)), (C, float(np.std(fold, ddof=1) / np.sqrt(len(fold))), float(roc_auc_score(y, p))))
    return best


def week_boot(df, fn, n=400):
    wk = df["date"].dt.to_period("W").astype(str).to_numpy()
    groups = [np.where(wk == w)[0] for w in np.unique(wk)]
    vals = []
    for _ in range(n):
        idx = np.concatenate([groups[i] for i in RNG.integers(0, len(groups), len(groups))])
        vals.append(fn(idx))
    return float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))


def temp_model(df, cols, target, nwp):
    return HistGradientBoostingRegressor(random_state=0, max_iter=250, learning_rate=0.05, max_depth=4, l2_regularization=5.0, min_samples_leaf=40).fit(df[cols], df[target] - df[nwp])


def main():
    df = table()
    dev = df[df["date"] <= DEV_END].reset_index(drop=True)
    hold = df[df["date"] >= HOLD_START].reset_index(drop=True)
    print(f"{df['city'].nunique()} cities | DEV2 {len(dev)} rows to {dev['date'].max().date()} | HOLDOUT2 {len(hold)} rows {hold['date'].min().date()} -> {hold['date'].max().date()}")
    out = {"dev_rows": len(dev), "holdout_rows": len(hold)}
    for target, label in (("rain_next", "RAIN >= 2.5 mm"), ("heavy_next", "HEAVY >= 10 mm")):
        print(f"\n=== {label}: selection on DEV2 (blocked CV, Brier, lower is better) ===")
        res = {}
        for name, cols in (("v1: 3 models recalibrated", V1), ("v2a: 7 models recalibrated", V2A), ("v2b: 7 models + disagreement", V2B), ("v2c: each of the 7 weighted separately", PER_MODEL)):
            b, (C, se, auc) = cv_brier(dev, cols, target)
            res[name] = (b, se, C, cols)
            print(f"  {name:42s} Brier {b:.4f} +-{se:.4f}  AUC {auc:.3f}  (C={C})")
        base_b, base_se = res["v1: 3 models recalibrated"][0], res["v1: 3 models recalibrated"][1]
        best_name = min(res, key=lambda k: res[k][0])
        # simplest within 1 SE of the best: order by feature count
        within = [k for k in res if res[k][0] <= res[best_name][0] + res[best_name][1]]
        pick = min(within, key=lambda k: len(res[k][3]))
        print(f"  best: {best_name}; simplest within 1 SE: {pick}")

        print(f"  --- HOLDOUT2 (scored once), models re-trained on the SAME DEV2 window ---")
        y = hold[target].to_numpy()
        clim = E.Climatology(target).fit(dev).predict_proba(hold)
        p1 = fit_logit(dev, V1, target, res["v1: 3 models recalibrated"][2]).predict_proba(hold[V1])[:, 1]
        cols2 = res[pick][3]
        p2 = fit_logit(dev, cols2, target, res[pick][2]).predict_proba(hold[cols2])[:, 1]
        b1, b2, bc = brier_score_loss(y, p1), brier_score_loss(y, p2), brier_score_loss(y, clim)
        ci1 = week_boot(hold, lambda i: brier_score_loss(y[i], p1[i])); ci2 = week_boot(hold, lambda i: brier_score_loss(y[i], p2[i]))
        diff = week_boot(hold, lambda i: brier_score_loss(y[i], p2[i]) - brier_score_loss(y[i], p1[i]))
        print(f"  climatology {bc:.3f} | v1 (3 models) {b1:.3f} [{ci1[0]:.3f},{ci1[1]:.3f}] | selected v2 ({pick.split(':')[0]}) {b2:.3f} [{ci2[0]:.3f},{ci2[1]:.3f}]")
        print(f"  v2 minus v1 Brier = {b2 - b1:+.4f}  (95% CI {diff[0]:+.4f} to {diff[1]:+.4f}; negative = v2 better; CI spanning 0 = no reliable difference)")
        out[target] = {"v1": b1, "v2": b2, "v2_model": pick, "diff": b2 - b1, "diff_ci": diff, "climatology": bc, "dev": {k: v[0] for k, v in res.items()}}

    print("\n=== TEMPERATURE ===")
    for target, nwp1, nwp2, label in (("tmax_next", "nwp_tmax_mean", "nwpx_tmax_mean", "high"), ("tmin_next", "nwp_tmin_mean", "nwpx_tmin_mean", "low")):
        r = {"v1": [], "v2": [], "raw3": [], "raw8": []}
        for a, b in E.block_splits(dev["date"], E.N_BLOCKS, E.GAP_DAYS):
            A, Bv = dev.iloc[a], dev.iloc[b]
            r["raw3"].append(mean_absolute_error(Bv[target], Bv[nwp1])); r["raw8"].append(mean_absolute_error(Bv[target], Bv[nwp2]))
            r["v1"].append(mean_absolute_error(Bv[target], Bv[nwp1] + temp_model(A, TEMP_V1, target, nwp1).predict(Bv[TEMP_V1])))
            r["v2"].append(mean_absolute_error(Bv[target], Bv[nwp2] + temp_model(A, TEMP_V2, target, nwp2).predict(Bv[TEMP_V2])))
        print(f"  {label} DEV2 CV MAE: raw 3-model {np.mean(r['raw3']):.2f} | raw 8-model {np.mean(r['raw8']):.2f} | v1 corrected {np.mean(r['v1']):.2f} | v2 corrected {np.mean(r['v2']):.2f}")
        m1, m2 = temp_model(dev, TEMP_V1, target, nwp1), temp_model(dev, TEMP_V2, target, nwp2)
        y = hold[target].to_numpy(); q1 = hold[nwp1].to_numpy() + m1.predict(hold[TEMP_V1]); q2 = hold[nwp2].to_numpy() + m2.predict(hold[TEMP_V2])
        d = week_boot(hold, lambda i: mean_absolute_error(y[i], q2[i]) - mean_absolute_error(y[i], q1[i]))
        print(f"    HOLDOUT2 MAE: raw 3-model {mean_absolute_error(y, hold[nwp1]):.2f} | raw 8-model {mean_absolute_error(y, hold[nwp2]):.2f} | v1 {mean_absolute_error(y, q1):.2f} | v2 {mean_absolute_error(y, q2):.2f}  (v2 minus v1 {mean_absolute_error(y, q2) - mean_absolute_error(y, q1):+.3f}, CI {d[0]:+.3f} to {d[1]:+.3f})")
        out[label] = {"v1": float(mean_absolute_error(y, q1)), "v2": float(mean_absolute_error(y, q2)), "raw3": float(mean_absolute_error(y, hold[nwp1])), "raw8": float(mean_absolute_error(y, hold[nwp2])), "diff_ci": d}
    json.dump(out, open(os.path.join(HERE, "cv_results_v2.json"), "w"), indent=2, default=float)


if __name__ == "__main__":
    main()
