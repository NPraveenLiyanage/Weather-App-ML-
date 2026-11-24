"""
Phase 2 data for v2: genuine forecasts issued 2, 3, 4 and 5 days ahead (Open-Meteo Previous Runs), so days 2 to 5 can be CALIBRATED
instead of shown as a raw average.  Precipitation for 7 weather models; temperature for the 3 best-tested ones.
Cached per city; re-run to resume.    myenv\\Scripts\\python.exe ml\\fetch_leads.py
Weather data by Open-Meteo.com (CC BY 4.0).
"""
import json, os, sys, time, urllib.parse, urllib.request
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_data import CITIES, DATA, END, PREV_START

MODELS = ["ecmwf_ifs025", "gfs_global", "icon_global", "jma_gsm", "gem_global", "meteofrance_arpege_world", "cma_grapes_global"]
TEMP_MODELS = {"ecmwf_ifs025", "gfs_global", "icon_global"}
LEADS = [2, 3, 4, 5]


def get(url):
    for i in range(12):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.load(r)
        except Exception as e:
            body = ""
            try: body = e.read().decode()[:100]
            except Exception: pass
            wait = min(900, 60 * (i + 1))
            print(f"   wait {wait}s ({str(e)[:40]} {body})", flush=True)
            time.sleep(wait)
    raise RuntimeError("giving up")


for city, (lat, lon) in CITIES.items():
    out = os.path.join(DATA, f"{city}_leads.csv")
    if os.path.exists(out):
        continue
    frames = []
    for m in MODELS:
        vars_ = [f"precipitation_previous_day{L}" for L in LEADS]
        if m in TEMP_MODELS:
            vars_ += [f"temperature_2m_previous_day{L}" for L in LEADS]
        q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "start_date": PREV_START, "end_date": END, "models": m, "hourly": ",".join(vars_), "timezone": "Asia/Colombo"})
        d = get("https://previous-runs-api.open-meteo.com/v1/forecast?" + q)
        h = pd.DataFrame(d["hourly"]); h["date"] = pd.to_datetime(h["time"]).dt.date
        g = h.groupby("date")
        cols = {}
        for L in LEADS:
            cols[f"{m}_L{L}_precip"] = g[f"precipitation_previous_day{L}"].sum(min_count=18)
            if m in TEMP_MODELS:
                cols[f"{m}_L{L}_tmax"] = g[f"temperature_2m_previous_day{L}"].max()
                cols[f"{m}_L{L}_tmin"] = g[f"temperature_2m_previous_day{L}"].min()
        frames.append(pd.DataFrame(cols))
        time.sleep(12)
    pd.concat(frames, axis=1).reset_index().to_csv(out, index=False)
    print(city, "done", flush=True)
print("done", flush=True)
