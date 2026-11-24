"""
Export real HOLDOUT days (never used for training or model selection) for the portfolio's "Beat my model" game.
    myenv\\Scripts\\python.exe ml\\export_game.py <output.json>
Each round shows the evidence a forecaster would see; the page reveals what happened and what the model said.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, "..", "weatherProject", "forecast", "model")
NAMES = {"nuwara_eliya": "Nuwara Eliya"}
SEED, PER_BUCKET = 7, 12


def main(out):
    d = pd.read_csv(os.path.join(MODEL, "holdout_predictions.csv"), parse_dates=["date"])
    m = json.load(open(os.path.join(MODEL, "metrics.json"), encoding="utf8"))
    d = d.dropna(subset=["p_rain", "ecmwf_ifs025_precip", "gfs_global_precip", "icon_global_precip", "nwp_rh_mean", "nwp_pressure_delta"])
    rng = np.random.default_rng(SEED)
    rain, dry = d[d["rain_next"] == 1], d[d["rain_next"] == 0]
    hard = d[(d["p_rain"] > 0.25) & (d["p_rain"] < 0.75)]  # genuinely uncertain days, so the game is not trivial
    pool = pd.concat([
        rain.sample(PER_BUCKET, random_state=SEED), dry.sample(PER_BUCKET, random_state=SEED),
        hard[hard["rain_next"] == 1].sample(PER_BUCKET // 2, random_state=SEED), hard[hard["rain_next"] == 0].sample(PER_BUCKET // 2, random_state=SEED),
    ]).drop_duplicates(["city", "date"])
    rows = []
    for r in pool.itertuples():
        rows.append({
            "city": NAMES.get(r.city, r.city.replace("_", " ").title()),
            "date": r.date.strftime("%Y-%m-%d"),
            "models_mm": {"European": round(r.ecmwf_ifs025_precip, 1), "American": round(r.gfs_global_precip, 1), "German": round(r.icon_global_precip, 1)},
            "humidity": round(float(r.nwp_rh_mean)), "pressure_change": round(float(r.nwp_pressure_delta), 1),
            "today_mm": round(float(r.precip), 1),
            "model_p": round(float(r.p_rain), 3), "rained": bool(r.rain_next == 1), "mm": round(float(r.precip_next), 1),
        })
    rng.shuffle(rows)
    doc = {"rounds": rows,
           "meta": {"holdout": f'{m["data"]["holdout_from"]} to {m["data"]["holdout_to"]}', "model_brier": round(m["rain"]["holdout"]["brier"], 3),
                    "climatology_brier": round(m["rain"]["climatology_brier"], 3), "auc": round(m["rain"]["holdout"]["auc"], 3),
                    "pool_model_brier": round(float(np.mean([(x["model_p"] - x["rained"]) ** 2 for x in rows])), 3),
                    "attribution": "Weather data by Open-Meteo.com (CC BY 4.0)"}}
    json.dump(doc, open(out, "w"), indent=1)
    print(len(rows), "rounds ->", out, "| pool model Brier", doc["meta"]["pool_model_brier"], "| rained share", round(float(np.mean([x["rained"] for x in rows])), 2))


if __name__ == "__main__":
    main(sys.argv[1])
