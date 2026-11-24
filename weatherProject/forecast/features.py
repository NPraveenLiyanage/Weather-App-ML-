"""
Feature construction shared by TRAINING (ml/dataset.py) and SERVING (forecast/predictor.py).
One implementation, so the live app can never drift from what the model was trained on.

Input frame columns (Open-Meteo daily names): date, temperature_2m_max/min/mean, precipitation_sum, relative_humidity_2m_mean,
pressure_msl_mean, dew_point_2m_mean, cloud_cover_mean, wind_gusts_10m_max, wind_direction_10m_dominant, shortwave_radiation_sum.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WET_MM = 2.5      # "rain day": light rain or more (ERA5 over-counts drizzle, so 1 mm would be fake rain)
HEAVY_MM = 10.0   # "heavy rain day"
MODELS = ["ecmwf_ifs025", "gfs_global", "icon_global"]
# BoM ACCESS stopped publishing in July 2025, so it is excluded. A missing model is tolerated (consensus over those present, at least MIN_MODELS).
EXTRA_MODELS = ["jma_gsm", "gem_global", "meteofrance_arpege_world", "cma_grapes_global"]
MODELS_ALL = MODELS + EXTRA_MODELS
MIN_MODELS = 5

OBS_FEATURES = ["lat", "lon", "elev", "tmax", "tmin", "tmean", "precip", "rh", "pressure", "dew", "cloud", "gust", "rad", "wind_sin", "wind_cos",
                "range", "dew_spread", "d_pressure", "d_rh", "d_tmax", "precip_l1", "precip_3d", "precip_7d", "precip_30d", "wet_days_7", "doy_sin", "doy_cos"]
NWP_FEATURES = ["nwp_precip_mean", "nwp_precip_max", "nwp_precip_min", "nwp_wet_frac", "nwp_tmax_mean", "nwp_tmin_mean", "nwp_rh_mean", "nwp_gust_mean",
                "nwp_pressure_delta", "nwp_tmax_delta"]
RAIN_FEATURES = ["nwp_precip_mean_log", "nwp_wet_frac", "nwp_rh_mean", "nwp_pressure_delta"]
TEMP_FEATURES = OBS_FEATURES + NWP_FEATURES + ["nwp_precip_mean_log"]


def observation_frame(a: pd.DataFrame, lat: float, lon: float, elev: float) -> pd.DataFrame:
    """Per-day 'what we know at the end of the day' features. Needs >= 30 trailing days for the long windows."""
    a = a.sort_values("date").reset_index(drop=True)
    f = pd.DataFrame(index=a.index)
    f["date"] = pd.to_datetime(a["date"])
    f["lat"], f["lon"], f["elev"] = lat, lon, elev
    f["tmax"], f["tmin"], f["tmean"] = a["temperature_2m_max"], a["temperature_2m_min"], a["temperature_2m_mean"]
    f["precip"] = a["precipitation_sum"]
    f["rh"], f["pressure"], f["dew"], f["cloud"] = a["relative_humidity_2m_mean"], a["pressure_msl_mean"], a["dew_point_2m_mean"], a["cloud_cover_mean"]
    f["gust"], f["rad"] = a["wind_gusts_10m_max"], a["shortwave_radiation_sum"]
    ang = np.radians(a["wind_direction_10m_dominant"])
    f["wind_sin"], f["wind_cos"] = np.sin(ang), np.cos(ang)
    f["range"] = f["tmax"] - f["tmin"]
    f["dew_spread"] = f["tmean"] - f["dew"]
    f["d_pressure"] = f["pressure"].diff()
    f["d_rh"] = f["rh"].diff()
    f["d_tmax"] = f["tmax"].diff()
    f["precip_l1"] = f["precip"].shift(1)
    f["precip_3d"] = f["precip"].rolling(3).sum()
    f["precip_7d"] = f["precip"].rolling(7).sum()
    f["precip_30d"] = f["precip"].rolling(30).sum()
    f["wet_today"] = (f["precip"] >= WET_MM).astype(float)
    f["wet_days_7"] = f["wet_today"].rolling(7).sum()
    doy = f["date"].dt.dayofyear
    f["doy_sin"], f["doy_cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
    return f


def add_nwp_features(f: pd.DataFrame) -> pd.DataFrame:
    """Needs columns {model}_precip/_tmax/_tmin/_gust/_rh/_pressure holding each model's forecast for the NEXT day."""
    pr = f[[f"{m}_precip" for m in MODELS]]
    f["nwp_precip_mean"], f["nwp_precip_max"], f["nwp_precip_min"] = pr.mean(axis=1), pr.max(axis=1), pr.min(axis=1)
    f["nwp_wet_frac"] = (pr >= WET_MM).sum(axis=1).where(pr.notna().all(axis=1)) / 3.0
    f["nwp_tmax_mean"] = f[[f"{m}_tmax" for m in MODELS]].mean(axis=1)
    f["nwp_tmin_mean"] = f[[f"{m}_tmin" for m in MODELS]].mean(axis=1)
    f["nwp_rh_mean"] = f[[f"{m}_rh" for m in MODELS]].mean(axis=1)
    f["nwp_gust_mean"] = f[[f"{m}_gust" for m in MODELS]].mean(axis=1)
    f["nwp_pressure_delta"] = f[[f"{m}_pressure" for m in MODELS]].mean(axis=1) - f["pressure"]
    f["nwp_tmax_delta"] = f["nwp_tmax_mean"] - f["tmax"]
    f["nwp_precip_mean_log"] = np.log1p(f["nwp_precip_mean"])
    f["nwp_precip_max_log"] = np.log1p(f["nwp_precip_max"])
    return f


NWPX_FEATURES = ["nwpx_precip_log_mean", "nwpx_precip_log_std", "nwpx_wet_frac", "nwpx_tmax_mean", "nwpx_tmin_mean", "nwpx_tmax_std", "nwpx_tmin_std", "nwpx_n"]


def add_nwpx_features(f: pd.DataFrame) -> pd.DataFrame:
    """Seven-model consensus; needs {model}_precip/_tmax/_tmin columns for MODELS_ALL (NaN where a model has no data)."""
    pr = f[[f"{m}_precip" for m in MODELS_ALL]]
    n = pr.notna().sum(axis=1)
    ok = n >= MIN_MODELS
    lp = np.log1p(pr.clip(lower=0))
    f["nwpx_n"] = n
    f["nwpx_precip_log_mean"] = lp.mean(axis=1).where(ok)
    f["nwpx_precip_log_std"] = lp.std(axis=1).where(ok)
    f["nwpx_wet_frac"] = ((pr >= WET_MM).sum(axis=1) / n.replace(0, np.nan)).where(ok)
    tx = f[[f"{m}_tmax" for m in MODELS_ALL]]
    tn = f[[f"{m}_tmin" for m in MODELS_ALL]]
    f["nwpx_tmax_mean"], f["nwpx_tmax_std"] = tx.mean(axis=1).where(ok), tx.std(axis=1).where(ok)
    f["nwpx_tmin_mean"], f["nwpx_tmin_std"] = tn.mean(axis=1).where(ok), tn.std(axis=1).where(ok)
    return f


# --- v2 rain model: every weather model gets its own learned weight (a missing model counts as "the consensus")
PLOG = [f"{m}_plog" for m in MODELS_ALL]
RAIN_FEATURES_V2 = PLOG + ["nwp_rh_mean", "nwp_pressure_delta"]


def add_rain_v2_inputs(f: pd.DataFrame) -> pd.DataFrame:
    for m in MODELS_ALL:
        if f"{m}_precip" not in f:
            f[f"{m}_precip"] = np.nan
        for k in ("tmax", "tmin"):
            if f"{m}_{k}" not in f:
                f[f"{m}_{k}"] = np.nan
    f = add_nwpx_features(f)
    for m in MODELS_ALL:
        f[f"{m}_plog"] = np.log1p(f[f"{m}_precip"].clip(lower=0)).fillna(f["nwpx_precip_log_mean"])
    return f
