# Sri Lanka rain & temperature forecast: method, evidence and limits

The page at `/` forecasts **tomorrow** for any place in Sri Lanka:
chance of rain (>= 2.5 mm), chance of heavy rain (>= 10 mm), and a likely range for the daytime high and overnight low.
Every number on the page is backed by the test below. Re-run everything with the app's pinned environment (scikit-learn 1.7.0).

```
myenv\Scripts\python.exe ml\fetch_data.py        # ~16 cities, ERA5 truth + genuine day-ahead forecasts (Open-Meteo, CC BY 4.0)
myenv\Scripts\python.exe ml\evaluate_sl.py       # locked model-selection protocol
myenv\Scripts\python.exe ml\train_final.py       # one-time holdout score, unseen-city test, writes forecast/model/
myenv\Scripts\python.exe ml\export_game.py out.json   # holdout days for the portfolio's "Beat my model" game
myenv\Scripts\python.exe ml\evaluate.py          # the ORIGINAL 366-row dataset, evaluated honestly (see "What was wrong")
```

## How real weather apps work (and why this is not one model per city)
Weather services run physics simulations of the atmosphere (ECMWF, NOAA GFS, DWD ICON). Apps interpolate those to your location and,
at best, add **one shared statistical correction** across many stations. Training a model per city from a few years of history cannot compete.
So this project does the same, at small scale: **one model for all of Sri Lanka**, fed by three real forecast models (genuine one-day-ahead
forecasts, via Open-Meteo's Previous Runs API), which learns how much to trust them and corrects their habits.

## Protocol (fixed before models were compared)
* 16 cities pooled; a city is only lat/lon/elevation. Rows = (city, day); features are known at the end of day t, targets are day t+1.
* **Final holdout**: 2025-10-01 to 2026-11-21 (6,608 city-days), scored once, after selection. Development data: 2024-03 to 2025-09.
* Selection: time-blocked CV with a 3-day purge, hyper-parameters tuned **inside** each training fold, simplest model within one standard error wins.
* Baselines every model must beat: climatology (city x month), persistence, and the raw forecast recalibrated.
* Primary metric Brier score (probability quality); accuracy alone would flatter any rain model.
* Truth is ERA5 reanalysis, a model-based estimate rather than rain-gauge readings. ERA5 over-counts drizzle (77% of Colombo days >= 1 mm; real Colombo is near 40%), which is why "rain" means >= 2.5 mm.

## Results on the untouched holdout
| | Ours | Climatology | Persistence | Raw forecast |
|---|---|---|---|---|
| Rain >= 2.5 mm, Brier (lower is better) | **0.125** (95% CI 0.112 to 0.136) | 0.223 | 0.184 | n/a (recalibrated is what we ship) |
| Heavy rain >= 10 mm, Brier | **0.095** (0.079 to 0.111) | 0.150 | 0.127 | n/a |
| Rain ROC-AUC / PR-AUC | 0.904 / 0.904 | | | |
| Tomorrow's high, mean abs error | **0.75 C** (0.71 to 0.78) | | 0.94 C | 0.91 C |
| Tomorrow's low, mean abs error | **0.56 C** (0.53 to 0.58) | | 0.60 C | 0.71 C |

* Calibration: when the model said 63% it rained on 62% of those days; 78% said, 74% happened; 94% said, 93% happened.
* **Works for places it never saw.** Training without a group of four cities and testing on them gave the same rain Brier as training with them (0.118 vs 0.118, 0.131 vs 0.131, 0.117 vs 0.115, 0.133 vs 0.134), and the temperature error still beat the raw forecast. One model covers the country.
* **Where ML adds little:** for rain, the calibrated three-model forecast already carries nearly all the skill; richer ML models tied it within noise (development CV, all 16 cities: Brier 0.120 for gradient boosting, 0.121 logistic, 0.122 recalibrated forecast; standard error about 0.008). ML earns its place on temperature (development CV, 16 cities: high error 0.66 vs 0.91 C raw, low error 0.46 vs 0.59 C).
* **A miss we report:** the 80% temperature ranges covered only 75% (high) and 71% (low) of holdout days, so the page says "likely range", not "80%".

## v2: seven weather models, each weighed (and what did NOT help)
Written down **before** running, because the first holdout had already been scored and published (`ml/evaluate_v2.py`): selection only on data before 2026-08-29,
a fresh holdout from 2026-09-01 (1,312 place-days, one season, short), v1 re-trained on the same window, and "if the gain is inside the noise, that is what gets reported".
* **Averaging more models did not help**: 7-model recalibrated consensus Brier 0.1262 vs 0.1238 for the 3-model version (dev CV).
* **Letting the model weigh each of the 7 separately did**, modestly: dev CV 0.1174 vs 0.1238; fresh holdout **0.108 vs 0.114** (difference -0.0060, 95% CI -0.0094 to -0.0021); heavy rain **0.118 vs 0.127** (-0.0084, CI -0.0161 to -0.0015). Climatology: 0.229 / 0.212. Out-of-fold calibration over 14,528 days stays on the diagonal (said 63%, happened 63%; said 95%, happened 94%).
* **Temperature: no gain**, so it stays on the 3-model version. The raw 7-model average is worse than the 3-model one (0.97 vs 0.91 C in dev CV), and the corrected 7-model model scored 0.80 vs 0.68 C in dev CV.
* Bureau of Meteorology (Australia) ACCESS was dropped: its archive ends July 2025. A missing model is tolerated at run time (counted as "the consensus").
* Still open: calibrated days 2-5, conformal temperature ranges (the "80%" ranges covered 71-75%), and quantifying the train/serve gap. The gain is small and from one short window; treat it as likely-real, not certain.

## What was wrong with the original model (and the numbers I first quoted)
The original app trained a Random Forest on 366 consecutive days from one station, 18% of them rainy.
* Always answering "no rain" is already **81.8%** accurate; the forest's 84.9% single-split accuracy was barely above that.
* My first quick check reported AUC 0.945. That was **one lucky 73-row split**. Rows are consecutive days (lag-1 autocorrelation of temperature 0.85), so shuffled folds leak. Blocked cross-validation gives about **0.78 to 0.84** (`ml/evaluate.py`).
* The live page **never used wind direction**: one `LabelEncoder` was re-fit on the target, so the compass lookup always failed and every prediction used `-1`. Fixed in `views.py` for the classic page (`/classic/`).
* It re-trained the forest on every page request and returned a hard yes/no instead of a probability.

## Limits (also stated on the page)
* Tomorrow only; days 2 to 5 are the raw average of the three models and are labelled as such.
* Trained and tested for Sri Lanka (16 cities, coast to hills); the page refuses coordinates outside it.
* Training years with genuine day-ahead forecasts begin in 2024, so seasonal coverage is about 2.5 years. More years will help.
* The page's rain numbers come from the newest 3 months (v2); its temperature numbers from the 14-month test (v1 temperature model, unchanged). It says so.
* Live inputs come from the forecast service's own analysis of today, while training used ERA5: a small train/serve difference we have not quantified.
* Not for safety-critical decisions. Follow official warnings.

Weather data by Open-Meteo.com (CC BY 4.0), including modified Copernicus ERA5 data and forecasts from ECMWF, NOAA/NCEP and DWD.
