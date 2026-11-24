"""
Train/serve gap.     myenv\\Scripts\\python.exe ml\\serve_gap.py
The model was trained on ERA5 reanalysis for "today". Live, the app feeds it the forecast service's own recent analysis ("past_days").
For the last 45 complete days at 16 places we build the same features BOTH ways and compare (a) the inputs and (b) the model's answers.
"""
import json, os, sys, time, urllib.parse, urllib.request
import numpy as np
import pandas as pd
import joblib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dataset as D  # noqa: E402
import features as F  # noqa: E402
from fetch_data import CITIES  # noqa: E402

MODEL = os.path.join(HERE, "..", "weatherProject", "forecast", "model")
OBS = ["temperature_2m_max", "temperature_2m_min", "temperature_2m_mean", "precipitation_sum", "relative_humidity_2m_mean", "pressure_msl_mean",
       "dew_point_2m_mean", "cloud_cover_mean", "wind_gusts_10m_max", "wind_direction_10m_dominant", "shortwave_radiation_sum"]


def get(url):
    for i in range(6):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.load(r)
        except Exception as e:
            time.sleep(20 * (i + 1))
    raise RuntimeError("fetch failed")


def logit(x, spec):
    z = (x - np.array(spec["mean"])) / np.array(spec["scale"])
    return 1 / (1 + np.exp(-(z * np.array(spec["coef"])).sum(axis=1) - spec["intercept"]))


def main():
    rain2 = json.load(open(os.path.join(MODEL, "rain_model_v2.json")))["dev"]["rain"]
    spec = json.load(open(os.path.join(MODEL, "rain_model_v2.json")))
    tmax_model = joblib.load(os.path.join(MODEL, "temp_models.joblib"))["tmax"]
    ranges_cols = F.TEMP_FEATURES
    keys = list(CITIES)
    ll = {"latitude": ",".join(str(CITIES[k][0]) for k in keys), "longitude": ",".join(str(CITIES[k][1]) for k in keys)}
    live = get("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({**ll, "daily": ",".join(OBS), "past_days": 75, "forecast_days": 1, "timezone": "Asia/Colombo"}))
    live = live if isinstance(live, list) else [live]
    rows_gap, in_diffs, out_rain, out_tmax = [], {}, [], []
    full = D.build()
    full["month"] = full["date"].dt.month
    for k, lv in zip(keys, live):
        a_live = pd.DataFrame(lv["daily"]).rename(columns={"time": "date"})
        elev = lv.get("elevation", 0)
        f_live = F.observation_frame(a_live, CITIES[k][0], CITIES[k][1], elev)
        ref = full[full["city"] == k].set_index("date")
        f_live = f_live.set_index("date")
        common = [d for d in f_live.index if d in ref.index and pd.notna(ref.loc[d, "nwp_precip_mean"]) and pd.notna(f_live.loc[d, "precip_30d"])]
        common = sorted(common)[-45:]
        if not common:
            continue
        L, R = f_live.loc[common], ref.loc[common]
        for c in ("tmax", "tmin", "rh", "pressure", "cloud", "gust", "precip", "dew", "rad"):
            in_diffs.setdefault(c, []).append(np.abs(L[c].to_numpy() - R[c].to_numpy()))
        # the model's answers with live-style vs training-style "today" features (forecast inputs identical)
        base = R.copy()
        alt = R.copy()
        for c in F.OBS_FEATURES:
            if c in L:
                alt[c] = L[c].to_numpy()
        for frame in (base, alt):
            frame["nwp_pressure_delta"] = frame["nwp_pressure_delta"] if frame is base else (R["nwp_pressure_delta"] + R["pressure"] - L["pressure"]).to_numpy()
        base = F.add_rain_v2_inputs(base.reset_index()); alt = F.add_rain_v2_inputs(alt.reset_index())
        for fr in (base, alt):
            fr["nwp_precip_mean_log"] = np.log1p(fr["nwp_precip_mean"])
        pb = logit(base[F.RAIN_FEATURES_V2].to_numpy(float), spec["dev"]["rain"]); pa = logit(alt[F.RAIN_FEATURES_V2].to_numpy(float), spec["dev"]["rain"])
        out_rain.append(np.c_[pb, pa])
        tb = base["nwp_tmax_mean"].to_numpy() + tmax_model.predict(base[ranges_cols]); ta = alt["nwp_tmax_mean"].to_numpy() + tmax_model.predict(alt[ranges_cols])
        out_tmax.append(np.c_[tb, ta])
    rain = np.vstack(out_rain); tmax = np.vstack(out_tmax)
    res = {"days_compared": int(len(rain)),
           "input_mean_abs_diff": {c: float(np.mean(np.concatenate(v))) for c, v in in_diffs.items()},
           "rain_prob_mean_abs_diff": float(np.mean(np.abs(rain[:, 0] - rain[:, 1]))),
           "rain_call_flips_pct": float(np.mean((rain[:, 0] >= 0.5) != (rain[:, 1] >= 0.5)) * 100),
           "tmax_mean_abs_diff_c": float(np.mean(np.abs(tmax[:, 0] - tmax[:, 1])))}
    print(json.dumps(res, indent=2))
    json.dump(res, open(os.path.join(HERE, "serve_gap.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
