"""
Phase 1 of the v2 model: five MORE weather models' genuine day-ahead forecasts (precipitation + temperature only),
so the post-processor can weigh 8 models instead of 3.  Cached per city; re-run to resume.  Be gentle: hourly data is heavy.
    myenv\Scripts\python.exe ml\fetch_extra.py
Weather data by Open-Meteo.com (CC BY 4.0).
"""
import os, sys, time, urllib.parse, urllib.request, json
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_data import CITIES, DATA, END, PREV_START

EXTRA = ["jma_gsm", "gem_global", "meteofrance_arpege_world", "cma_grapes_global", "bom_access_global"]


def get(url):
    for i in range(12):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.load(r)
        except Exception as e:
            body = ""
            try: body = e.read().decode()[:120]
            except Exception: pass
            wait = min(900, 60 * (i + 1))
            print(f"   wait {wait}s ({str(e)[:40]} {body})", flush=True)
            time.sleep(wait)
    raise RuntimeError("giving up")


for city, (lat, lon) in CITIES.items():
    out = os.path.join(DATA, f"{city}_prev_extra.csv")
    if os.path.exists(out):
        continue
    frames = []
    for m in EXTRA:
        q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "start_date": PREV_START, "end_date": END, "models": m,
                                    "hourly": "precipitation_previous_day1,temperature_2m_previous_day1", "timezone": "Asia/Colombo"})
        d = get("https://previous-runs-api.open-meteo.com/v1/forecast?" + q)
        h = pd.DataFrame(d["hourly"]); h["date"] = pd.to_datetime(h["time"]).dt.date
        g = h.groupby("date")
        frames.append(pd.DataFrame({f"{m}_precip": g["precipitation_previous_day1"].sum(min_count=18),
                                    f"{m}_tmax": g["temperature_2m_previous_day1"].max(), f"{m}_tmin": g["temperature_2m_previous_day1"].min()}))
        time.sleep(15)
    pd.concat(frames, axis=1).reset_index().to_csv(out, index=False)
    print(city, "done", flush=True)
print("done", flush=True)
