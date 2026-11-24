"""How wide must a seasonal range be to really cover 80% of LATER days when calibrated on EARLIER days?  (drift-aware level)
    myenv\\Scripts\\python.exe ml\\conformal_level.py
Writes ml/cv_results_conformal_deploy.json: seasonal half-widths from ALL out-of-fold residuals at the level that achieved ~80% out-of-time.
"""
import json, os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import conformal as C  # noqa: E402
import evaluate_sl as E  # noqa: E402

CUT = C.CUT
df = E.table()
df["season"] = df["month"].map(C.season)
deploy = {}
for target, nwp, label in (("tmax_next", "nwp_tmax_mean", "high"), ("tmin_next", "nwp_tmin_mean", "low")):
    d = df.copy()
    d["res"] = C.oof_residuals(d, target, nwp)
    cal, test = d[d["date"] < CUT], d[d["date"] >= CUT]
    best = None
    print(f"\n{label}: level of the calibration quantile -> coverage on later days / mean width")
    for q in (0.80, 0.85, 0.88, 0.90, 0.92):
        hs = {s: np.quantile(np.abs(cal.loc[cal["season"] == s, "res"]), q) for s in cal["season"].unique()}
        w = test["season"].map(hs).to_numpy()
        cov = float(np.mean(np.abs(test["res"].to_numpy()) <= w))
        print(f"  q={q:.2f}: covers {cov:.1%}, mean width {2 * w.mean():.2f} C")
        if best is None and cov >= 0.79:
            best = q
    q = best or 0.92
    deploy[label] = {"level": q, "half_widths": {s: float(np.quantile(np.abs(d.loc[d["season"] == s, "res"].dropna()), q)) for s in d["season"].unique()}}
    print(f"  -> ship level {q} (first level reaching ~80% on later days), seasonal half-widths from ALL residuals: {deploy[label]['half_widths']}")
json.dump(deploy, open(os.path.join(HERE, "cv_results_conformal_deploy.json"), "w"), indent=2)
