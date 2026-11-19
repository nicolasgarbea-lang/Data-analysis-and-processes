# Data check: de_forecasts_hourly

- rows: 69095 hourly; first 2019-01-01 00:00:00+00:00 last 2026-11-18 22:00:00+00:00
- raw 15-min values averaged to hourly; duplicates between chunks dropped (keep last)
- solar_da_forecast_de_mw: missing 0.00% (2019-01-01→2026-11-01), first valid 2019-01-01 00:00:00+00:00, min 0, max 57896
- wind_onshore_da_forecast_de_mw: missing 0.00% (2019-01-01→2026-11-01), first valid 2019-01-01 00:00:00+00:00, min 161, max 48122
- wind_offshore_da_forecast_de_mw: missing 0.00% (2019-01-01→2026-11-01), first valid 2019-01-01 00:00:00+00:00, min 13, max 7387
- load_da_forecast_de_mw: missing 0.00% (2019-01-01→2026-11-01), first valid 2019-01-01 00:00:00+00:00, min 30545, max 77586
- PUBLICATION TIME UNVERIFIED: API gives no issue time. Legal deadlines: load D-1 10:00 CET (Art. 6 Reg. 543/2013, borderline for our 10:00 forecast), wind/solar D-1 18:00 CET (Art. 14, after our forecast time). Flag column publication_time_unverified=True.
