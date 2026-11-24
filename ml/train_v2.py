"""
Fit and score the v2 rain models (7 weather models, each with its own learned weight).   myenv\\Scripts\\python.exe ml\\train_v2.py
Protocol exactly as pre-committed in evaluate_v2.py: C chosen by blocked CV on DEV2 (< 2026-08-29), fresh HOLDOUT2 scored once,
v1 re-trained on the same window for a fair comparison.  Writes weatherProject/forecast/model/rain_model_v2.json and metrics_v2.json.
The deployed weights are re-fit on ALL rows; the DEV2-fit copy is kept so the live 30-day scorecard only scores days it never saw.
"""
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evaluate_sl as E  # noqa: E402
import evaluate_v2 as V  # noqa: E402
import features as F  # noqa: E402

OUT = os.path.join(HERE, "..", "weatherProject", "forecast", "model")
COLS = F.RAIN_FEATURES_V2


def spec(pipe):
    sc, lr = pipe.named_steps["standardscaler"], pipe.named_steps["logisticregression"]
    return {"mean": sc.mean_.tolist(), "scale": sc.scale_.tolist(), "coef": lr.coef_[0].tolist(), "intercept": float(lr.intercept_[0])}


def main():
    df = V.table()
    df = F.add_rain_v2_inputs(df.copy()) if "ecmwf_ifs025_plog" not in df else df
    dev = df[df["date"] <= V.DEV_END].reset_index(drop=True)
    hold = df[df["date"] >= V.HOLD_START].reset_index(drop=True)
    metrics = {"data": {"dev_rows": len(dev), "holdout_rows": len(hold), "dev_to": str(dev["date"].max().date()), "holdout_from": str(hold["date"].min().date()),
                        "holdout_to": str(hold["date"].max().date()), "models": F.MODELS_ALL}}
    model = {"features": COLS, "full": {}, "dev": {}}
    for target, key in (("rain_next", "rain"), ("heavy_next", "heavy")):
        _, (C, _, _) = V.cv_brier(dev, COLS, target)
        # out-of-fold predictions on DEV2 for the calibration chart (each day judged by a model that never saw it)
        ps, ys = [], []
        for a, b in E.block_splits(dev["date"], E.N_BLOCKS, E.GAP_DAYS):
            ps.append(V.fit_logit(dev.iloc[a], COLS, target, C).predict_proba(dev.iloc[b][COLS])[:, 1]); ys.append(dev.iloc[b][target].to_numpy())
        p_oof, y_oof = np.concatenate(ps), np.concatenate(ys)
        bins = pd.cut(p_oof, [0, .1, .25, .4, .55, .7, .85, 1.0], include_lowest=True)
        rel = pd.DataFrame({"p": p_oof, "y": y_oof}).groupby(bins, observed=True).agg(n=("y", "size"), said=("p", "mean"), happened=("y", "mean"))
        # fresh holdout, v1 re-trained on the same window
        y = hold[target].to_numpy()
        m2 = V.fit_logit(dev, COLS, target, C)
        p2 = m2.predict_proba(hold[COLS])[:, 1]
        b1c = V.cv_brier(dev, V.V1, target)[1][0]
        p1 = V.fit_logit(dev, V.V1, target, b1c).predict_proba(hold[V.V1])[:, 1]
        clim = E.Climatology(target).fit(dev).predict_proba(hold)
        ci = V.week_boot(hold, lambda i: brier_score_loss(y[i], p2[i]))
        dci = V.week_boot(hold, lambda i: brier_score_loss(y[i], p2[i]) - brier_score_loss(y[i], p1[i]))
        metrics[key] = {"C": C, "holdout2_brier": brier_score_loss(y, p2), "holdout2_ci95": ci, "v1_same_window_brier": brier_score_loss(y, p1),
                        "climatology_brier": brier_score_loss(y, clim), "diff_v2_minus_v1": brier_score_loss(y, p2) - brier_score_loss(y, p1), "diff_ci95": dci,
                        "holdout2_auc": roc_auc_score(y, p2), "dev_oof_brier": brier_score_loss(y_oof, p_oof), "dev_oof_auc": roc_auc_score(y_oof, p_oof),
                        "reliability": [{"said": round(r.said, 3), "happened": round(r.happened, 3), "n": int(r.n)} for r in rel.itertuples()]}
        print(f"{key}: holdout2 Brier {metrics[key]['holdout2_brier']:.3f} {tuple(round(x, 3) for x in ci)} | v1 same window {metrics[key]['v1_same_window_brier']:.3f} | climatology {metrics[key]['climatology_brier']:.3f} | v2-v1 {metrics[key]['diff_v2_minus_v1']:+.4f} {tuple(round(x, 4) for x in dci)}")
        print("   reliability (said -> happened, n):", "; ".join(f"{r['said']:.2f}->{r['happened']:.2f} ({r['n']})" for r in metrics[key]["reliability"]))
        model["dev"][key] = spec(m2)
        model["full"][key] = spec(V.fit_logit(df, COLS, target, C))
    metrics["skill_rain_vs_climatology"] = 1 - metrics["rain"]["holdout2_brier"] / metrics["rain"]["climatology_brier"]
    json.dump(model, open(os.path.join(OUT, "rain_model_v2.json"), "w"), indent=2)
    json.dump(metrics, open(os.path.join(OUT, "metrics_v2.json"), "w"), indent=2, default=float)
    print("saved rain_model_v2.json and metrics_v2.json")


if __name__ == "__main__":
    main()
