"""
Build the modelling table: one row per (city, origin day t).  Everything in the features is known at the end of day t;
targets are what happens on day t+1.

  features : today's conditions, yesterday's change, recent wetness, season, location,
             and (for the MOS table) three models' genuine day-ahead forecasts for t+1.
  targets  : rain_next (precipitation on t+1 >= 2.5 mm), heavy_next (>= 10 mm),
             precip_next, tmax_next, tmin_next.
Truth is ERA5 reanalysis (a model-based estimate of observations, not rain-gauge readings): stated limitation.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "weatherProject", "forecast"))
import features as F  # noqa: E402  (shared with the live app)
from features import WET_MM, HEAVY_MM, OBS_FEATURES, NWP_FEATURES  # noqa: E402,F401
DATA = os.path.join(HERE, "data")
CITY_META = {}  # filled from fetch_data.CITIES


def _cities():
    from fetch_data import CITIES  # noqa: WPS433 (script-local import)
    return CITIES


def load_city(city: str, lat: float, lon: float) -> pd.DataFrame:
    a = pd.read_csv(os.path.join(DATA, f"{city}_archive.csv"), parse_dates=["time"]).rename(columns={"time": "date"})
    f = F.observation_frame(a, lat, lon, a["elevation"].iloc[0])
    f["city"] = city
    # targets: tomorrow
    f["precip_next"] = f["precip"].shift(-1)
    f["rain_next"] = (f["precip_next"] >= WET_MM).astype(float)
    f.loc[f["precip_next"].isna(), "rain_next"] = np.nan
    f["heavy_next"] = (f["precip_next"] >= HEAVY_MM).astype(float)
    f.loc[f["precip_next"].isna(), "heavy_next"] = np.nan
    f["tmax_next"], f["tmin_next"] = f["tmax"].shift(-1), f["tmin"].shift(-1)
    # genuine day-ahead forecasts for t+1 (issued on day t)
    p = pd.read_csv(os.path.join(DATA, f"{city}_prev.csv"), parse_dates=["date"])
    p["date"] = p["date"] - pd.Timedelta(days=1)  # forecast VALID on t+1, attached to origin day t
    f = f.merge(p, on="date", how="left")
    f = F.add_nwp_features(f)
    extra = os.path.join(DATA, f"{city}_prev_extra.csv")
    if os.path.exists(extra):
        e = pd.read_csv(extra, parse_dates=["date"])
        e["date"] = e["date"] - pd.Timedelta(days=1)
        f = F.add_nwpx_features(f.merge(e, on="date", how="left"))
    return f


def build(only: list[str] | None = None) -> pd.DataFrame:
    frames = []
    for city, (lat, lon) in _cities().items():
        if only and city not in only:
            continue
        if not (os.path.exists(os.path.join(DATA, f"{city}_archive.csv")) and os.path.exists(os.path.join(DATA, f"{city}_prev.csv"))):
            continue
        frames.append(load_city(city, lat, lon))
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, HERE)
    d = build()
    print(d.shape, d["city"].nunique(), "cities;", d["date"].min().date(), "->", d["date"].max().date())
    m = d.dropna(subset=NWP_FEATURES + ["rain_next"])
    print("rows with NWP forecasts:", len(m), "| wet-day rate:", round(m["rain_next"].mean(), 3))
