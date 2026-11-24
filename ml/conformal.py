"""
Temperature ranges that actually cover what they claim.     myenv\\Scripts\\python.exe ml\\conformal.py

Problem found earlier: the "80%" ranges (sized from out-of-fold residuals) covered only 75% (high) and 71% (low) of the holdout days, because the
weather drifted away from the training months. Candidates are calibrated on the DEVELOPMENT period only (before 2025-10-01), then judged on the
later period once. Coverage is reported as measured, not as targeted.
    A  static:      empirical 10%/90% quantiles of residuals (what shipped)
    B  symmetric:   split-conformal half-width = 80th percentile of |residual|
    C  seasonal:    B, separately for each monsoon season (DJF, MAM, JJAS, ON)
    D  adaptive:    B on residuals divided by the weather models' disagreement (wider when the models disagree)
"""
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dataset as D  # noqa: E402
import evaluate_sl as E  # noqa: E402
import features as F  # noqa: E402

CUT = pd.Timestamp("2025-10-01")
TEMP_FEATS = F.TEMP_FEATURES


def season(m):
    return "DJF" if m in (12, 1, 2) else "MAM" if m in (3, 4) else "JJAS" if m in (5, 6, 7, 8, 9) else "ON"


def oof_residuals(df, target, nwp):
    """Out-of-fold residuals (each row predicted by a model that never saw its time block), over the whole table."""
    res = pd.Series(np.nan, index=df.index)
    for a, b in E.block_splits(df["date"], E.N_BLOCKS, E.GAP_DAYS):
        m = HistGradientBoostingRegressor(random_state=0, max_iter=250, learning_rate=0.05, max_depth=4, l2_regularization=5.0, min_samples_leaf=40).fit(df.iloc[a][TEMP_FEATS], df.iloc[a][target] - df.iloc[a][nwp])
        pred = df.iloc[b][nwp] + m.predict(df.iloc[b][TEMP_FEATS])
        res.iloc[b] = df.iloc[b][target] - pred
    return res


def main():
    df = E.table()
    df["spread"] = df[[f"{m}_tmax" for m in F.MODELS]].std(axis=1).fillna(0.0)
    df["season"] = df["month"].map(season)
    out = {}
    for target, nwp, label in (("tmax_next", "nwp_tmax_mean", "high"), ("tmin_next", "nwp_tmin_mean", "low")):
        d = df.copy()
        d["spread"] = d[[f"{m}_{'tmax' if label == 'high' else 'tmin'}" for m in F.MODELS]].std(axis=1).fillna(0.0)
        d["res"] = oof_residuals(d, target, nwp)
        cal, test = d[d["date"] < CUT], d[d["date"] >= CUT]
        r_cal, r_test = cal["res"].to_numpy(), test["res"].to_numpy()
        rows = {}
        lo, hi = np.quantile(r_cal, [0.10, 0.90])
        rows["A static quantiles"] = ((r_test >= lo) & (r_test <= hi), hi - lo)
        h = np.quantile(np.abs(r_cal), 0.80)
        rows["B symmetric conformal"] = (np.abs(r_test) <= h, 2 * h)
        hs = {s: np.quantile(np.abs(cal.loc[cal["season"] == s, "res"]), 0.80) for s in cal["season"].unique()}
        w = test["season"].map(hs).to_numpy()
        rows["C seasonal conformal"] = (np.abs(r_test) <= w, 2 * w.mean())
        k = np.quantile(np.abs(r_cal) / (cal["spread"].to_numpy() + 0.25), 0.80)
        w = k * (test["spread"].to_numpy() + 0.25)
        rows["D disagreement-scaled"] = (np.abs(r_test) <= w, 2 * w.mean())
        print(f"\n=== {label}: calibrated on {len(cal)} days before {CUT.date()}, judged on {len(test)} later days (target 80%) ===")
        out[label] = {}
        for name, (hit, width) in rows.items():
            cov = float(np.mean(hit))
            out[label][name] = {"coverage": cov, "mean_width_c": float(width)}
            print(f"  {name:26s} covered {cov:6.1%}   mean width {width:4.2f} C")
        out[label]["seasonal_half_widths"] = {s: float(v) for s, v in hs.items()}
        out[label]["spread_scale_k"] = float(k)
        # what to ship: all data (dev + later) so the deployed ranges include the drift, per-season
        allres = d["res"].dropna()
        out[label]["deploy_seasonal_half_widths"] = {s: float(np.quantile(np.abs(d.loc[d["season"] == s, "res"].dropna()), 0.80)) for s in d["season"].unique()}
    json.dump(out, open(os.path.join(HERE, "cv_results_conformal.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
