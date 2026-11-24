"""
Download training data for the Sri Lanka rain/temperature model from Open-Meteo (free, no API key).

  * archive  : daily observations-like truth (ERA5 reanalysis) 2015-01-01 -> yesterday
  * previous : GENUINE one-day-ahead forecasts issued the day before (ECMWF IFS, GFS, ICON), available since ~2024-03,
               aggregated to local-day values. This is the input a post-processing ("MOS") model needs.
Cached under ml/data/ (skipped if already downloaded).  Run:  myenv\\Scripts\\python.exe ml\\fetch_data.py

Attribution (required): Weather data by Open-Meteo.com (CC BY 4.0), which contains modified Copernicus ERA5 data
and NWP output from ECMWF, NOAA/NCEP and DWD.  https://open-meteo.com/en/license
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

# Popular Sri Lankan cities (lat, lon). The model is trained on all of them together.
CITIES = {
    "colombo": (6.9271, 79.8612), "kandy": (7.2906, 80.6337), "galle": (6.0535, 80.2210),
    "jaffna": (9.6615, 80.0255), "negombo": (7.2086, 79.8358), "anuradhapura": (8.3114, 80.4037),
    "trincomalee": (8.5874, 81.2152), "batticaloa": (7.7170, 81.7000), "matara": (5.9549, 80.5550),
    "nuwara_eliya": (6.9497, 80.7891), "kurunegala": (7.4863, 80.3647), "ratnapura": (6.6828, 80.3992),
    "badulla": (6.9934, 81.0550), "hambantota": (6.1241, 81.1185), "vavuniya": (8.7514, 80.4971),
    "puttalam": (8.0408, 79.8394),
}
ARCHIVE_VARS = ["temperature_2m_max", "temperature_2m_min", "temperature_2m_mean", "precipitation_sum", "wind_speed_10m_max",
                "wind_gusts_10m_max", "wind_direction_10m_dominant", "relative_humidity_2m_mean", "pressure_msl_mean",
                "dew_point_2m_mean", "cloud_cover_mean", "shortwave_radiation_sum"]
PREV_HOURLY = ["precipitation_previous_day1", "temperature_2m_previous_day1", "wind_gusts_10m_previous_day1",
               "relative_humidity_2m_previous_day1", "pressure_msl_previous_day1"]
PREV_MODELS = ["ecmwf_ifs025", "gfs_global", "icon_global"]
PREV_START = "2024-03-01"
END = (date.today() - timedelta(days=2)).isoformat()


def get(url, tries=8):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.load(r)
        except Exception as e:  # rate limit / transient
            msg = ""
            try:
                msg = e.read().decode()[:200]
            except Exception:
                pass
            wait = 45 * (i + 1)
            print(f"   retry {i + 1} after {wait}s ({str(e)[:60]} {msg})", flush=True)
            time.sleep(wait)
    raise RuntimeError("giving up on " + url[:120])


def archive(city, lat, lon):
    out = os.path.join(DATA, f"{city}_archive.csv")
    if os.path.exists(out):
        return
    q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "start_date": "2015-01-01", "end_date": END,
                                "daily": ",".join(ARCHIVE_VARS), "timezone": "Asia/Colombo"})
    d = get("https://archive-api.open-meteo.com/v1/archive?" + q)
    df = pd.DataFrame(d["daily"])
    df["elevation"] = d.get("elevation")
    df.to_csv(out, index=False)
    print(f"   archive {city}: {len(df)} days", flush=True)


def previous(city, lat, lon):
    out = os.path.join(DATA, f"{city}_prev.csv")
    if os.path.exists(out):
        return
    frames = []
    for m in PREV_MODELS:
        q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "start_date": PREV_START, "end_date": END,
                                    "hourly": ",".join(PREV_HOURLY), "models": m, "timezone": "Asia/Colombo"})
        d = get("https://previous-runs-api.open-meteo.com/v1/forecast?" + q)
        h = pd.DataFrame(d["hourly"])
        h["date"] = pd.to_datetime(h["time"]).dt.date
        h = h.drop(columns="time")
        h.columns = [c.replace("_previous_day1", "") for c in h.columns]
        g = h.groupby("date")
        daily = pd.DataFrame({
            f"{m}_precip": g["precipitation"].sum(min_count=18),
            f"{m}_tmax": g["temperature_2m"].max(), f"{m}_tmin": g["temperature_2m"].min(),
            f"{m}_gust": g["wind_gusts_10m"].max(), f"{m}_rh": g["relative_humidity_2m"].mean(),
            f"{m}_pressure": g["pressure_msl"].mean(),
        })
        frames.append(daily)
        time.sleep(8)
    df = pd.concat(frames, axis=1).reset_index().rename(columns={"index": "time"})
    df.to_csv(out, index=False)
    print(f"   previous-runs {city}: {len(df)} days", flush=True)


if __name__ == "__main__":
    only = sys.argv[1:] or list(CITIES)
    for city in only:
        lat, lon = CITIES[city]
        print(city, flush=True)
        archive(city, lat, lon)
        time.sleep(8)
        previous(city, lat, lon)
        time.sleep(8)
    with open(os.path.join(DATA, "ATTRIBUTION.txt"), "w") as f:
        f.write(__doc__)
    print("done", flush=True)
