"""
Final scoring + deployable model.   myenv\\Scripts\\python.exe ml\\train_final.py

1. Models chosen by the locked protocol in evaluate_sl.py (simplest within 1 SE of best on blocked nested CV):
     rain >= 2.5 mm, heavy rain >= 10 mm : logistic recalibration of the 3-model forecast consensus (4 features)
     tomorrow's high / low               : gradient-boosted correction of the forecast (residual model)
2. Fitted on DEV only, scored ONCE on the HOLDOUT (with block-bootstrap intervals), then a leave-cities-out test.
3. Refit on ALL rows for deployment -> model/rain_model.json, model/temp_models.joblib, model/metrics.json,
   and holdout predictions for the portfolio game -> model/holdout_predictions.csv
"""
from __future__ import annotations

import json
import os
import sys
import warnings

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, mean_absolute_error, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dataset as D  # noqa: E402
import evaluate_sl as E  # noqa: E402

OUT = os.path.join(HERE, "..", "weatherProject", "forecast", "model")
os.makedirs(OUT, exist_ok=True)
RAIN_FEATS = E.LOGIT_NWP
TEMP_FEATS = D.OBS_FEATURES + D.NWP_FEATURES + ["nwp_precip_mean_log"]
RNG = np.random.default_rng(0)


def fit_logit(df, target, C):
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=5000)).fit(df[RAIN_FEATS], df[target])


def tune_C(dev, target):
    best, bs = 1.0, 9
    for C in (0.1, 1.0):
        ps, ys = [], []
        for a, b in E.block_splits(dev["date"], E.N_BLOCKS, E.GAP_DAYS):
            ps.append(fit_logit(dev.iloc[a], target, C).predict_proba(dev.iloc[b][RAIN_FEATS])[:, 1]); ys.append(dev.iloc[b][target].to_numpy())
        s = brier_score_loss(np.concatenate(ys), np.concatenate(ps))
        if s < bs:
            best, bs = C, s
    return best


def fit_temp(df, target, nwp_col):
    return HistGradientBoostingRegressor(random_state=0, max_iter=250, learning_rate=0.05, max_depth=4, l2_regularization=5.0,
                                         min_samples_leaf=40).fit(df[TEMP_FEATS], df[target] - df[nwp_col])


def oof_residual_quantiles(dev, target, nwp_col):
    """Honest 80% interval half-widths from out-of-fold residuals (never in-sample)."""
    res = []
    for a, b in E.block_splits(dev["date"], E.N_BLOCKS, E.GAP_DAYS):
        m = fit_temp(dev.iloc[a], target, nwp_col)
        res.append(dev.iloc[b][target].to_numpy() - (dev.iloc[b][nwp_col].to_numpy() + m.predict(dev.iloc[b][TEMP_FEATS])))
    r = np.concatenate(res)
    return float(np.quantile(r, 0.10)), float(np.quantile(r, 0.90))


def rain_scores(y, p, base):
    return {"brier": brier_score_loss(y, p), "skill_vs_climatology": 1 - brier_score_loss(y, p) / brier_score_loss(y, np.full_like(p, base)),
            "auc": roc_auc_score(y, p), "pr_auc": average_precision_score(y, p), "logloss": log_loss(y, np.clip(p, 1e-4, 1 - 1e-4))}


def week_bootstrap(df, fn, n=300):
    """Resample whole weeks (days within a week are correlated) to get honest intervals."""
    wk = df["date"].dt.to_period("W").astype(str)
    groups = {w: np.where(wk.to_numpy() == w)[0] for w in wk.unique()}
    keys = list(groups)
    vals = []
    for _ in range(n):
        idx = np.concatenate([groups[k] for k in RNG.choice(keys, len(keys))])
        vals.append(fn(idx))
    return float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))


def main():
    df = E.table()
    dev = df[df["date"] < E.HOLDOUT_START].reset_index(drop=True)
    hold = df[df["date"] >= E.HOLDOUT_START].reset_index(drop=True)
    print(f"{df['city'].nunique()} cities | DEV {len(dev)} rows to {dev['date'].max().date()} | HOLDOUT {len(hold)} rows {hold['date'].min().date()} -> {hold['date'].max().date()}")
    metrics = {"data": {"cities": sorted(df["city"].unique().tolist()), "dev_rows": len(dev), "holdout_rows": len(hold),
                        "holdout_from": str(hold["date"].min().date()), "holdout_to": str(hold["date"].max().date())}}

    # ---------------- rain (>=2.5, >=10): fit on DEV, score holdout once
    pred_out = hold[["city", "date", "precip_next", "rain_next", "heavy_next", "nwp_precip_mean", "nwp_wet_frac", "nwp_rh_mean", "nwp_pressure_delta",
                     "ecmwf_ifs025_precip", "gfs_global_precip", "icon_global_precip", "tmax", "precip", "pressure", "rh"]].copy()
    for target, key in (("rain_next", "rain"), ("heavy_next", "heavy")):
        C = tune_C(dev, target)
        m = fit_logit(dev, target, C)
        p = m.predict_proba(hold[RAIN_FEATS])[:, 1]
        y = hold[target].to_numpy()
        base = dev[target].mean()
        clim = E.Climatology(target).fit(dev).predict_proba(hold)
        pers = E.FeatLogit(["wet_days_7", "precip"], target).fit(dev).predict_proba(hold)
        sc = rain_scores(y, p, base)
        ci = week_bootstrap(hold, lambda i: brier_score_loss(y[i], p[i]))
        cb = brier_score_loss(y, clim)
        cp = brier_score_loss(y, pers)
        metrics[key] = {"holdout": sc, "brier_ci95": ci, "climatology_brier": cb, "persistence_brier": cp, "dev_base_rate": base, "holdout_base_rate": float(y.mean()), "C": C}
        pred_out[f"p_{key}"] = p
        # reliability table
        bins = pd.cut(p, [0, .1, .25, .4, .55, .7, .85, 1.0], include_lowest=True)
        rel = pd.DataFrame({"p": p, "y": y}).groupby(bins).agg(n=("y", "size"), said=("p", "mean"), happened=("y", "mean")).dropna()
        metrics[key]["reliability"] = [{"said": round(r.said, 3), "happened": round(r.happened, 3), "n": int(r.n)} for r in rel.itertuples()]
        print(f"\n{key.upper()} (>= {'2.5' if key == 'rain' else '10'} mm) HOLDOUT: Brier {sc['brier']:.3f} [{ci[0]:.3f}, {ci[1]:.3f}] vs climatology {cb:.3f}, persistence {cp:.3f} | skill {sc['skill_vs_climatology']:.2f} | AUC {sc['auc']:.3f} | PR-AUC {sc['pr_auc']:.3f}")
        print("  reliability (said -> happened, n):", "; ".join(f"{r['said']:.2f}->{r['happened']:.2f} ({r['n']})" for r in metrics[key]["reliability"]))

    # ---------------- temperatures
    temp_models, intervals = {}, {}
    for target, nwp_col, key in (("tmax_next", "nwp_tmax_mean", "tmax"), ("tmin_next", "nwp_tmin_mean", "tmin")):
        q10, q90 = oof_residual_quantiles(dev, target, nwp_col)
        m = fit_temp(dev, target, nwp_col)
        pred = hold[nwp_col].to_numpy() + m.predict(hold[TEMP_FEATS])
        y = hold[target].to_numpy()
        mae = mean_absolute_error(y, pred)
        ci = week_bootstrap(hold, lambda i: mean_absolute_error(y[i], pred[i]))
        raw = mean_absolute_error(y, hold[nwp_col])
        pers = mean_absolute_error(y, hold["tmax" if key == "tmax" else "tmin"])
        cov = float(np.mean((y >= pred + q10) & (y <= pred + q90)))
        metrics[key] = {"mae": mae, "mae_ci95": ci, "raw_forecast_mae": raw, "persistence_mae": pers, "interval80": [q10, q90], "interval80_holdout_coverage": cov}
        pred_out[f"{key}_pred"], pred_out[f"{key}_raw"], pred_out[f"{key}_true"] = pred, hold[nwp_col].to_numpy(), y
        print(f"\n{key.upper()} HOLDOUT MAE {mae:.2f} C [{ci[0]:.2f}, {ci[1]:.2f}] | raw forecast {raw:.2f} | persistence {pers:.2f} | 80% interval {q10:+.2f}..{q90:+.2f} covers {cov:.0%} of holdout days")

    # ---------------- unseen cities: train on 12 cities, test 4 held-out cities on the holdout period
    cities = sorted(df["city"].unique())
    groups = [cities[i::4] for i in range(4)]
    rows = []
    for g in groups:
        tr, te = dev[~dev["city"].isin(g)], hold[hold["city"].isin(g)]
        m = fit_logit(tr, "rain_next", metrics["rain"]["C"])
        p_unseen = m.predict_proba(te[RAIN_FEATS])[:, 1]
        p_seen = fit_logit(dev, "rain_next", metrics["rain"]["C"]).predict_proba(te[RAIN_FEATS])[:, 1]
        tm = fit_temp(tr, "tmax_next", "nwp_tmax_mean")
        t_unseen = te["nwp_tmax_mean"].to_numpy() + tm.predict(te[TEMP_FEATS])
        rows.append({"cities": g, "brier_unseen": brier_score_loss(te["rain_next"], p_unseen), "brier_seen": brier_score_loss(te["rain_next"], p_seen),
                     "tmax_mae_unseen": mean_absolute_error(te["tmax_next"], t_unseen), "tmax_mae_raw": mean_absolute_error(te["tmax_next"], te["nwp_tmax_mean"])})
    metrics["unseen_cities"] = rows
    print("\nUNSEEN-CITY TEST (model trained WITHOUT these cities):")
    for r in rows:
        print(f"  {','.join(r['cities'])[:60]:60s} rain Brier {r['brier_unseen']:.3f} (with them in training {r['brier_seen']:.3f}) | high MAE {r['tmax_mae_unseen']:.2f} (raw {r['tmax_mae_raw']:.2f})")

    # ---------------- keep the DEV-fitted models too: the live scorecard uses them so it only scores days they have never seen
    dev_spec = {"sklearn": sklearn.__version__, "targets": {}}
    for target, key in (("rain_next", "rain"), ("heavy_next", "heavy")):
        pipe = fit_logit(dev, target, metrics[key]["C"])
        sc, lr = pipe.named_steps["standardscaler"], pipe.named_steps["logisticregression"]
        dev_spec["targets"][key] = {"mean": sc.mean_.tolist(), "scale": sc.scale_.tolist(), "coef": lr.coef_[0].tolist(), "intercept": float(lr.intercept_[0])}
    json.dump(dev_spec, open(os.path.join(OUT, "rain_model_dev.json"), "w"), indent=2)
    joblib.dump({"tmax": fit_temp(dev, "tmax_next", "nwp_tmax_mean"), "tmin": fit_temp(dev, "tmin_next", "nwp_tmin_mean"), "sklearn": sklearn.__version__}, os.path.join(OUT, "temp_models_dev.joblib"))

    # ---------------- refit on ALL rows for deployment
    full = df
    deploy = {"sklearn": sklearn.__version__, "rain_features": RAIN_FEATS, "temp_features": TEMP_FEATS, "targets": {}}
    for target, key in (("rain_next", "rain"), ("heavy_next", "heavy")):
        pipe = fit_logit(full, target, metrics[key if key == "rain" else "heavy"]["C"])
        sc, lr = pipe.named_steps["standardscaler"], pipe.named_steps["logisticregression"]
        deploy["targets"][key] = {"mean": sc.mean_.tolist(), "scale": sc.scale_.tolist(), "coef": lr.coef_[0].tolist(), "intercept": float(lr.intercept_[0])}
    joblib.dump({"tmax": fit_temp(full, "tmax_next", "nwp_tmax_mean"), "tmin": fit_temp(full, "tmin_next", "nwp_tmin_mean"), "sklearn": sklearn.__version__}, os.path.join(OUT, "temp_models.joblib"))
    # Deployed ranges are sized from out-of-fold residuals over ALL data (the dev-only ranges under-covered the holdout: see metrics).
    deploy["interval80"] = {"tmax": list(oof_residual_quantiles(full, "tmax_next", "nwp_tmax_mean")), "tmin": list(oof_residual_quantiles(full, "tmin_next", "nwp_tmin_mean"))}
    metrics["deployed_interval80"] = deploy["interval80"]
    json.dump(deploy, open(os.path.join(OUT, "rain_model.json"), "w"), indent=2)
    json.dump(metrics, open(os.path.join(OUT, "metrics.json"), "w"), indent=2, default=float)
    pred_out.to_csv(os.path.join(OUT, "holdout_predictions.csv"), index=False)
    print("\nsaved model + metrics + holdout predictions to", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
