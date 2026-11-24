# Weather app roadmap

## Done (branch `improve-model`)
* Rebuilt forecast: one pooled model for 16 Sri Lankan cities, calibrated rain / heavy rain, high and low with ranges, plain-language "why".
* Original glass-over-photo design kept and made responsive; new tabs: Next 24 hours, Tomorrow, 4 days, Island map, Proof; saved places, alerts, share-as-picture.
* Photos: 22 MB of JPEG replaced by responsive WebP with an inline blurred preview (a visit loads one scene, about 20 to 200 KB).
* v2 rain model (seven weather models, each weighed) with an honest, pre-committed test. See `ml/README.md`.

## Next (ranked)
1. Calibrated days 2 to 5 (use the previous_day2..5 forecasts).
2. Conformal / per-season temperature ranges (current "likely range" under-covers).
3. Quantify the live-vs-training input gap (forecast-API past days vs ERA5).
4. Pre-warm popular places on the server, so the first load after a Render cold start is not slow.
5. Choose from: Sinhala and Tamil, hourly commute rain windows, district heavy-rain risk with DMC links, air quality and UV, installable app with push alerts (needs a server).
