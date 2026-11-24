"""
Live forecast for any location in Sri Lanka.

  Open-Meteo (3 weather models: ECMWF IFS, NOAA GFS, DWD ICON)  ->  shared features  ->  our calibrated models

* P(rain >= 2.5 mm) and P(heavy rain >= 10 mm) tomorrow: logistic recalibration of the 3-model consensus.
* Tomorrow's high / low: the consensus forecast plus a learned correction, with an 80% range.
* A 30-day scorecard re-runs the same model on past days using genuine day-ahead forecasts and compares with what happened.
Weather data by Open-Meteo.com (CC BY 4.0).  See ml/ for training, evaluation and the honest limits.
"""
from __future__ import annotations

import json
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd
import requests

from . import features as F

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, "model")
TZ = "Asia/Colombo"
SL_BOX = (5.7, 10.0, 79.4, 82.1)  # lat_min, lat_max, lon_min, lon_max: the region the model was trained and tested on
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
PREV_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OBS_VARS = ["temperature_2m_max", "temperature_2m_min", "temperature_2m_mean", "precipitation_sum", "relative_humidity_2m_mean", "pressure_msl_mean",
            "dew_point_2m_mean", "cloud_cover_mean", "wind_gusts_10m_max", "wind_direction_10m_dominant", "shortwave_radiation_sum"]
NWP_DAILY = ["precipitation_sum", "temperature_2m_max", "temperature_2m_min", "wind_gusts_10m_max", "relative_humidity_2m_mean", "pressure_msl_mean"]

CITIES = {
    "colombo": ("Colombo", 6.9271, 79.8612), "kandy": ("Kandy", 7.2906, 80.6337), "galle": ("Galle", 6.0535, 80.2210),
    "jaffna": ("Jaffna", 9.6615, 80.0255), "negombo": ("Negombo", 7.2086, 79.8358), "anuradhapura": ("Anuradhapura", 8.3114, 80.4037),
    "trincomalee": ("Trincomalee", 8.5874, 81.2152), "batticaloa": ("Batticaloa", 7.7170, 81.7000), "matara": ("Matara", 5.9549, 80.5550),
    "nuwara_eliya": ("Nuwara Eliya", 6.9497, 80.7891), "kurunegala": ("Kurunegala", 7.4863, 80.3647), "ratnapura": ("Ratnapura", 6.6828, 80.3992),
    "badulla": ("Badulla", 6.9934, 81.0550), "hambantota": ("Hambantota", 6.1241, 81.1185), "vavuniya": ("Vavuniya", 8.7514, 80.4971),
    "puttalam": ("Puttalam", 8.0408, 79.8394),
}

_lock = threading.Lock()
_models: dict = {}
_cache: dict = {}


class ForecastError(Exception):
    pass


# ----------------------------------------------------------------------------- models
def load_models():
    with _lock:
        if not _models:
            with open(os.path.join(MODEL_DIR, "rain_model.json"), encoding="utf8") as fh:
                _models["rain"] = json.load(fh)
            _models["temp"] = joblib.load(os.path.join(MODEL_DIR, "temp_models.joblib"))
            with open(os.path.join(MODEL_DIR, "rain_model_v2.json"), encoding="utf8") as fh:
                _models["rain2"] = json.load(fh)
            with open(os.path.join(MODEL_DIR, "metrics_v2.json"), encoding="utf8") as fh:
                _models["metrics2"] = json.load(fh)
            with open(os.path.join(MODEL_DIR, "rain_model_dev.json"), encoding="utf8") as fh:
                _models["rain_dev"] = json.load(fh)
            _models["temp_dev"] = joblib.load(os.path.join(MODEL_DIR, "temp_models_dev.joblib"))
            with open(os.path.join(MODEL_DIR, "metrics.json"), encoding="utf8") as fh:
                _models["metrics"] = json.load(fh)
    return _models


def _logit(x: np.ndarray, spec: dict) -> tuple[float, np.ndarray]:
    """Logistic regression with standardisation (exported from scikit-learn). Returns probability and per-feature contributions."""
    z = (x - np.array(spec["mean"])) / np.array(spec["scale"])
    contrib = z * np.array(spec["coef"])
    s = float(contrib.sum() + spec["intercept"])
    return 1.0 / (1.0 + math.exp(-s)), contrib


# ----------------------------------------------------------------------------- fetching
def _get(url: str, params: dict, ttl: int = 1800):
    key = (url, tuple(sorted(params.items())))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            if len(_cache) > 400:
                _cache.clear()
            _cache[key] = (time.time(), data)
            return data
        except requests.RequestException as e:
            last = e
            time.sleep(1)
    raise ForecastError(f"Weather data is temporarily unavailable ({last})")


def _get_optional(url: str, params: dict):
    """The four extra models only sharpen the rain forecast: if that call fails the forecast still works without them."""
    try:
        return _get(url, params)
    except ForecastError:
        return None


def in_region(lat: float, lon: float) -> bool:
    return SL_BOX[0] <= lat <= SL_BOX[1] and SL_BOX[2] <= lon <= SL_BOX[3]


def _prev_daily(h: pd.DataFrame, m: str) -> pd.DataFrame:
    h = h.copy()
    h["date"] = pd.to_datetime(h["time"]).dt.date
    g = h.groupby("date")
    return pd.DataFrame({f"{m}_precip": g["precipitation"].sum(min_count=18), f"{m}_tmax": g["temperature_2m"].max(), f"{m}_tmin": g["temperature_2m"].min(),
                         f"{m}_gust": g["wind_gusts_10m"].max(), f"{m}_rh": g["relative_humidity_2m"].mean(), f"{m}_pressure": g["pressure_msl"].mean()})


# ----------------------------------------------------------------------------- the forecast
def _why(contrib: dict, row: pd.Series, n_models: int, n_wet: int) -> list:
    """Plain-language reasons. The per-model inputs are correlated, so they are explained together (a per-input sign can mislead)."""
    fc = sum(v for k, v in contrib.items() if k.endswith("_plog"))
    mm = float(row["nwp_precip_mean"])
    rh, dp = float(row["nwp_rh_mean"]), float(row["nwp_pressure_delta"])
    items = [
        (abs(fc), ("The weather models expect about %.1f mm of rain, and %d of %d say it will rain" % (mm, n_wet, n_models)) if n_wet
         else ("The weather models expect only %.1f mm, and none of the %d say it will rain" % (mm, n_models)), fc),
        (abs(contrib["nwp_rh_mean"]), "The air will be %s (%.0f%% humidity)" % ("humid" if rh >= 78 else "fairly dry" if rh < 65 else "moderately humid", rh), contrib["nwp_rh_mean"]),
        (abs(contrib["nwp_pressure_delta"]), "Pressure is falling, which usually means unsettled weather" if dp < -0.8 else "Pressure is rising, which usually means settling weather" if dp > 0.8 else "Pressure is steady", contrib["nwp_pressure_delta"]),
    ]
    items.sort(key=lambda t: -t[0])
    return [{"text": t, "pushes": "up" if v > 0.05 else ("down" if v < -0.05 else "neutral")} for _, t, v in items]


def _certainty(p: float) -> str:
    m = max(p, 1 - p)
    return "very sure" if m >= 0.85 else "fairly sure" if m >= 0.7 else "leaning" if m >= 0.58 else "toss-up"


# ----------------------------------------------------------------------------- weather codes -> words + background scene
def describe(code: int, is_day: int = 1) -> dict:
    """WMO weather code -> plain words and the background photo to use (see static/img/sky/manifest.json)."""
    table = {
        0: ("clear sky", "clear"), 1: ("mostly clear", "clear"), 2: ("partly cloudy", "cloudy"), 3: ("overcast clouds", "overcast"),
        45: ("fog", "fog"), 48: ("freezing fog", "fog"), 51: ("light drizzle", "drizzle"), 53: ("drizzle", "drizzle"), 55: ("heavy drizzle", "drizzle"),
        56: ("freezing drizzle", "drizzle"), 57: ("freezing drizzle", "drizzle"), 61: ("light rain", "drizzle"), 63: ("moderate rain", "moderate"),
        65: ("heavy intensity rain", "rain"), 66: ("freezing rain", "rain"), 67: ("freezing rain", "rain"), 71: ("light snow", "overcast"),
        73: ("snow", "overcast"), 75: ("heavy snow", "overcast"), 77: ("snow grains", "overcast"), 80: ("light rain showers", "shower"),
        81: ("rain showers", "showers"), 82: ("violent rain showers", "rain"), 85: ("snow showers", "overcast"), 86: ("snow showers", "overcast"),
        95: ("thunderstorm", "thunder"), 96: ("thunderstorm with hail", "thunder"), 99: ("thunderstorm with heavy hail", "thunder"),
    }
    text, scene = table.get(int(code), ("unsettled weather", "overcast"))
    return {"text": text, "scene": scene, "night": not bool(is_day)}


def season_note(month: int) -> dict:
    """Plain-language monsoon context for Sri Lanka (general climatology, not a forecast)."""
    if month in (12, 1, 2):
        return {"name": "Northeast monsoon", "text": "Rain mostly falls in the north and east; the southwest is usually drier."}
    if month in (3, 4):
        return {"name": "First inter-monsoon", "text": "Hot, humid days with afternoon thunderstorms spreading across the island."}
    if month in (5, 6, 7, 8, 9):
        return {"name": "Southwest monsoon", "text": "Rain mostly falls in the southwest and hills; the north and east are usually drier."}
    return {"name": "Second inter-monsoon", "text": "Afternoon and evening thunderstorms, often heavy, are common across the island."}


# ----------------------------------------------------------------------------- shared prediction core
def _as_list(d):
    return d if isinstance(d, list) else [d]


def _fetch_forecast_inputs(lats: list, lons: list):
    ll = {"latitude": ",".join(f"{x:.3f}" for x in lats), "longitude": ",".join(f"{x:.3f}" for x in lons)}
    with ThreadPoolExecutor(3) as ex:  # the calls are independent: run them side by side
        fo = ex.submit(_get, FORECAST_URL, {**ll, "daily": ",".join(OBS_VARS), "past_days": 32, "forecast_days": 2, "timezone": TZ})
        fn = ex.submit(_get, FORECAST_URL, {**ll, "daily": ",".join(NWP_DAILY), "models": ",".join(F.MODELS), "forecast_days": 6, "timezone": TZ})
        fx = ex.submit(_get_optional, FORECAST_URL, {**ll, "daily": "precipitation_sum", "models": ",".join(F.EXTRA_MODELS), "forecast_days": 6, "timezone": TZ})
        extra = fx.result()
        return _as_list(fo.result()), _as_list(fn.result()), (_as_list(extra) if extra else [None] * len(lats))


def _predict(obs: dict, nwp: dict, lat: float, lon: float, name, extra=None, spec_key="full"):
    """Calibrated forecast for tomorrow from the two Open-Meteo payloads for ONE location."""
    M = load_models()
    elev = float(obs.get("elevation", 0.0))
    daily = pd.DataFrame(obs["daily"]).rename(columns={"time": "date"})
    daily["date"] = pd.to_datetime(daily["date"])
    today = pd.Timestamp(datetime.now(ZoneInfo(TZ)).date())
    if today not in set(daily["date"]):
        raise ForecastError("Weather data is out of date; please try again shortly.")
    daily = daily[daily["date"] <= today].reset_index(drop=True)
    f = F.observation_frame(daily, lat, lon, elev)
    row = f[f["date"] == today].iloc[[0]].copy()

    nd = pd.DataFrame(nwp["daily"]).rename(columns={"time": "date"})
    nd["date"] = pd.to_datetime(nd["date"])
    tomorrow = today + pd.Timedelta(days=1)
    t = nd[nd["date"] == tomorrow]
    if t.empty:
        raise ForecastError("Forecast for tomorrow is not available yet.")
    names = {"precipitation_sum": "precip", "temperature_2m_max": "tmax", "temperature_2m_min": "tmin", "wind_gusts_10m_max": "gust",
             "relative_humidity_2m_mean": "rh", "pressure_msl_mean": "pressure"}
    for m in F.MODELS:
        for api, short in names.items():
            col = f"{api}_{m}"
            row[f"{m}_{short}"] = float(t[col].iloc[0]) if col in t and pd.notna(t[col].iloc[0]) else np.nan
    if row[[f"{m}_precip" for m in F.MODELS]].isna().any(axis=None):
        raise ForecastError("One of the weather models has no data for this location right now.")
    row = F.add_nwp_features(row)
    if extra is not None:
        ed = pd.DataFrame(extra["daily"]).rename(columns={"time": "date"})
        ed["date"] = pd.to_datetime(ed["date"])
        et = ed[ed["date"] == tomorrow]
        for m in F.EXTRA_MODELS:
            col = f"precipitation_sum_{m}"
            row[f"{m}_precip"] = float(et[col].iloc[0]) if (not et.empty and col in et and pd.notna(et[col].iloc[0])) else np.nan
    row = F.add_rain_v2_inputs(row)
    s = row.iloc[0]

    out = {"location": {"name": name or f"{lat:.2f}, {lon:.2f}", "lat": lat, "lon": lon, "elevation": round(elev)},
           "generated_at": datetime.utcnow().isoformat() + "Z", "today": str(today.date()), "date": str(tomorrow.date()), "calibrated": True}
    xr = s[F.RAIN_FEATURES_V2].to_numpy(dtype=float)
    p_rain, contrib = _logit(xr, M["rain2"][spec_key]["rain"])
    p_heavy, _ = _logit(xr, M["rain2"][spec_key]["heavy"])
    p_heavy = min(p_heavy, p_rain)  # heavy rain cannot be likelier than any rain
    present = [m for m in F.MODELS_ALL if pd.notna(row[f"{m}_precip"].iloc[0])]
    n_wet = int(sum(float(s[f"{m}_precip"]) >= F.WET_MM for m in present))
    mm_all = [float(s[f"{m}_precip"]) for m in present]
    cdict = dict(zip(F.RAIN_FEATURES_V2, contrib))
    out["rain"] = {"probability": round(p_rain, 3), "certainty": _certainty(p_rain), "heavy_probability": round(p_heavy, 3),
                   "expected_mm": round(float(np.mean(mm_all)), 1), "models_agree": n_wet, "models_total": len(present),
                   "model_mm": {m: round(float(s[f"{m}_precip"]), 1) for m in present}, "why": _why(cdict, s, len(present), n_wet)}
    xt = row[F.TEMP_FEATURES]
    for key, col, fit in (("high", "nwp_tmax_mean", "tmax"), ("low", "nwp_tmin_mean", "tmin")):
        pred = float(s[col] + M["temp"][fit].predict(xt)[0])
        lo, hi = M["rain"]["interval80"][fit]
        out[key] = {"value": round(pred, 1), "low": round(pred + lo, 1), "high": round(pred + hi, 1), "raw_forecast": round(float(s[col]), 1)}
    return out, nd, today


def forecast(lat: float, lon: float, name=None) -> dict:
    if not in_region(lat, lon):
        raise ForecastError("This forecast is trained and tested for Sri Lanka only. Please choose a location inside Sri Lanka.")
    lat, lon = round(float(lat), 3), round(float(lon), 3)
    live_params = {"latitude": lat, "longitude": lon, "timezone": TZ, "forecast_days": 2, "wind_speed_unit": "kmh",
                   "current": "temperature_2m,apparent_temperature,relative_humidity_2m,cloud_cover,wind_speed_10m,wind_gusts_10m,pressure_msl,visibility,weather_code,is_day,precipitation",
                   "hourly": "temperature_2m,precipitation_probability,precipitation,weather_code,relative_humidity_2m,is_day",
                   "daily": "sunrise,sunset,temperature_2m_max,temperature_2m_min"}
    with ThreadPoolExecutor(1) as ex:
        live_future = ex.submit(_get, FORECAST_URL, live_params, 600)
        obs, nwp, extra = _fetch_forecast_inputs([lat], [lon])
        live = live_future.result()
    out, nd, today = _predict(obs[0], nwp[0], lat, lon, name, extra[0])

    # days 2-5: honest raw consensus (our calibration is trained for day 1 only)
    outlook = []
    for d in range(2, 6):
        r = nd[nd["date"] == today + pd.Timedelta(days=d)]
        if r.empty:
            continue
        r = r.iloc[0]
        mm = [float(r[f"precipitation_sum_{m}"]) for m in F.MODELS if pd.notna(r.get(f"precipitation_sum_{m}"))]
        hi_t = [float(r[f"temperature_2m_max_{m}"]) for m in F.MODELS if pd.notna(r.get(f"temperature_2m_max_{m}"))]
        lo_t = [float(r[f"temperature_2m_min_{m}"]) for m in F.MODELS if pd.notna(r.get(f"temperature_2m_min_{m}"))]
        if not mm:
            continue
        outlook.append({"date": str((today + pd.Timedelta(days=d)).date()), "expected_mm": round(float(np.mean(mm)), 1),
                        "models_agree": int(sum(v >= F.WET_MM for v in mm)), "models": len(mm),
                        "high": round(float(np.mean(hi_t)), 1) if hi_t else None, "low": round(float(np.mean(lo_t)), 1) if lo_t else None})
    out["outlook"] = outlook

    # right now + the next 24 hours (raw Open-Meteo, shown as such)
    cur = live["current"]
    desc = describe(cur["weather_code"], cur.get("is_day", 1))
    out["now"] = {"temp": round(cur["temperature_2m"]), "feels": round(cur["apparent_temperature"]), "humidity": round(cur["relative_humidity_2m"]),
                  "clouds": round(cur["cloud_cover"]), "wind_kmh": round(cur["wind_speed_10m"], 1), "gust_kmh": round(cur["wind_gusts_10m"], 1),
                  "pressure": round(cur["pressure_msl"]), "visibility_km": round((cur.get("visibility") or 0) / 1000, 1), "mm": cur.get("precipitation", 0),
                  "time": cur["time"][-5:], "description": desc["text"], "scene": desc["scene"], "night": desc["night"],
                  "high_today": round(live["daily"]["temperature_2m_max"][0]), "low_today": round(live["daily"]["temperature_2m_min"][0])}
    out["sun"] = {"sunrise": live["daily"]["sunrise"][0][-5:], "sunset": live["daily"]["sunset"][0][-5:]}
    h = live["hourly"]
    now_iso = cur["time"][:13]
    start = max(0, next((i for i, t in enumerate(h["time"]) if t[:13] >= now_iso), 0))
    out["hourly"] = [{"time": h["time"][i][-5:], "temp": round(h["temperature_2m"][i], 1), "pop": h["precipitation_probability"][i], "mm": h["precipitation"][i],
                      "text": describe(h["weather_code"][i], h["is_day"][i])["text"], "humidity": h["relative_humidity_2m"][i]}
                     for i in range(start, min(start + 24, len(h["time"])))]
    out["season"] = season_note(today.month)
    out["track_record"] = track_record_summary()
    return out


def island() -> dict:
    """Tomorrow's calibrated rain chance for every trained city at once (batched: 2 weather calls in total)."""
    key = ("island", datetime.now(ZoneInfo(TZ)).strftime("%Y-%m-%d-%H") + str(datetime.now().minute // 30))
    hit = _cache.get(key)
    if hit:
        return hit[1]
    keys = list(CITIES)
    lats, lons = [CITIES[k][1] for k in keys], [CITIES[k][2] for k in keys]
    obs, nwp, extra = _fetch_forecast_inputs(lats, lons)
    cities = []
    for k, o, n, e in zip(keys, obs, nwp, extra):
        try:
            r, _, _ = _predict(o, n, CITIES[k][1], CITIES[k][2], CITIES[k][0], e)
        except ForecastError:
            continue
        cities.append({"key": k, "name": CITIES[k][0], "lat": CITIES[k][1], "lon": CITIES[k][2], "p": r["rain"]["probability"],
                       "heavy": r["rain"]["heavy_probability"], "mm": r["rain"]["expected_mm"], "high": r["high"]["value"]})
    out = {"cities": cities}
    _cache[key] = (time.time(), out)
    return out


def track_record_summary() -> dict:
    M = load_models()
    m, m2 = M["metrics"], M["metrics2"]
    r = m2["rain"]
    return {"rain_brier": round(r["holdout2_brier"], 3), "rain_brier_v1": round(r["v1_same_window_brier"], 3), "rain_brier_climatology": round(r["climatology_brier"], 3),
            "rain_gain_ci": [round(x, 4) for x in r["diff_ci95"]], "skill": round(m2["skill_rain_vs_climatology"], 2),
            "rain_holdout": f'{m2["data"]["holdout_from"]} to {m2["data"]["holdout_to"]}', "rain_holdout_days": m2["data"]["holdout_rows"], "rain_models": len(m2["data"]["models"]),
            "high_mae": round(m["tmax"]["mae"], 2), "high_mae_raw": round(m["tmax"]["raw_forecast_mae"], 2), "low_mae": round(m["tmin"]["mae"], 2), "low_mae_raw": round(m["tmin"]["raw_forecast_mae"], 2),
            "temp_holdout": f'{m["data"]["holdout_from"]} to {m["data"]["holdout_to"]}', "temp_holdout_days": m["data"]["holdout_rows"], "cities": len(m["data"]["cities"]),
            "reliability": r["reliability"]}


# ----------------------------------------------------------------------------- scorecard: re-run on the past 30 days
def scorecard(lat: float, lon: float, days: int = 30) -> dict:
    if not in_region(lat, lon):
        raise ForecastError("Outside Sri Lanka.")
    M = load_models()
    lat, lon = round(float(lat), 3), round(float(lon), 3)
    end = datetime.now(ZoneInfo(TZ)).date() - timedelta(days=3)  # reanalysis truth lags a couple of days
    start = end - timedelta(days=days + 33)
    arch = _get(ARCHIVE_URL, {"latitude": lat, "longitude": lon, "start_date": start.isoformat(), "end_date": end.isoformat(),
                              "daily": ",".join(OBS_VARS), "timezone": TZ}, ttl=6 * 3600)
    elev = float(arch.get("elevation", 0.0))
    a = pd.DataFrame(arch["daily"]).rename(columns={"time": "date"})
    f = F.observation_frame(a, lat, lon, elev)
    f["precip_next"], f["tmax_next"], f["tmin_next"] = f["precip"].shift(-1), f["tmax"].shift(-1), f["tmin"].shift(-1)

    parts = []
    for m in F.MODELS:
        d = _get(PREV_URL, {"latitude": lat, "longitude": lon, "start_date": (start + timedelta(days=30)).isoformat(), "end_date": end.isoformat(), "models": m,
                            "hourly": "precipitation_previous_day1,temperature_2m_previous_day1,wind_gusts_10m_previous_day1,relative_humidity_2m_previous_day1,pressure_msl_previous_day1",
                            "timezone": TZ}, ttl=6 * 3600)
        h = pd.DataFrame(d["hourly"])
        h.columns = [c.replace("_previous_day1", "") for c in h.columns]
        parts.append(_prev_daily(h, m))
    p = pd.concat(parts, axis=1).reset_index().rename(columns={"index": "date"})
    p["date"] = pd.to_datetime(p["date"]) - pd.Timedelta(days=1)
    f = f.merge(p, on="date", how="left")
    f = F.add_nwp_features(f)
    for m in F.EXTRA_MODELS:
        try:
            d = _get(PREV_URL, {"latitude": lat, "longitude": lon, "start_date": (start + timedelta(days=30)).isoformat(), "end_date": end.isoformat(), "models": m,
                                "hourly": "precipitation_previous_day1", "timezone": TZ}, ttl=6 * 3600)
            h = pd.DataFrame(d["hourly"])
            h["date"] = pd.to_datetime(h["time"]).dt.normalize()
            ex = h.groupby("date")["precipitation_previous_day1"].sum(min_count=18).rename(f"{m}_precip").reset_index()
            ex["date"] = ex["date"] - pd.Timedelta(days=1)
            f = f.merge(ex, on="date", how="left")
        except ForecastError:
            pass  # that model is simply treated as "the consensus", exactly as in training
    f = F.add_rain_v2_inputs(f)
    f = f.dropna(subset=F.RAIN_FEATURES + ["precip_next", "tmax_next"]).tail(days)
    rows = []
    for _, r in f.iterrows():
        pr, _ = _logit(r[F.RAIN_FEATURES_V2].to_numpy(dtype=float), M["rain2"]["dev"]["rain"])
        hi = float(r["nwp_tmax_mean"] + M["temp_dev"]["tmax"].predict(r[F.TEMP_FEATURES].to_frame().T.astype(float))[0])
        rows.append({"date": str((r["date"] + pd.Timedelta(days=1)).date()), "p_rain": round(pr, 3), "rained": bool(r["precip_next"] >= F.WET_MM),
                     "mm": round(float(r["precip_next"]), 1), "high_pred": round(hi, 1), "high_actual": round(float(r["tmax_next"]), 1)})
    if not rows:
        raise ForecastError("Not enough recent data for a scorecard yet.")
    y = np.array([r["rained"] for r in rows], dtype=float)
    p_arr = np.array([r["p_rain"] for r in rows])
    right = int(((p_arr >= 0.5) == (y == 1)).sum())
    return {"days": len(rows), "right_calls": right, "brier": round(float(np.mean((p_arr - y) ** 2)), 3),
            "brier_always_climatology": round(float(np.mean((y.mean() - y) ** 2)), 3),
            "high_mae": round(float(np.mean([abs(r["high_pred"] - r["high_actual"]) for r in rows])), 2), "rows": rows,
            "note": "These days are after the model's training period: this card uses a version trained only on earlier data, so it has never seen them. \"What happened\" is a reanalysis estimate, not a rain-gauge reading."}
