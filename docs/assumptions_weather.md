# Assumptions – weather (agent D2)

## Time conventions
- MeteoSwiss hourly stamp = END of the 10-min-aggregation interval ("ReferenceTS 16:00 = 15:10 to 16:00", opendatadocs.meteoswiss.ch/general/download) → we shift −1 h so `timestamp_utc` = start of hour. Checked: after the shift, mean June radiation peaks in the 11–12 UTC bin and is symmetric around 11:30 UTC (solar noon at 8.56° E ≈ 11:26 UTC).
- MeteoSwiss notes hourly values before 2018 used a SYNOP schedule; our data start 2018-12-01, so this does not matter.
- Open-Meteo: radiation, sunshine and precipitation are "preceding hour" mean/sum; temperature, wind, cloud, humidity are instantaneous (open-meteo.com/en/docs). We shift every Open-Meteo stamp −1 h (one rule for all variables). Radiation alignment checked: MAE vs station is 34.8 W/m² with this shift vs 56 W/m² with ±1 h.
- Instantaneous Open-Meteo values therefore are the value at the end of the hour, while MeteoSwiss gives the hour mean (0.5 h offset). Kept for simplicity; the bias correction absorbs the diurnal part.

## Forecast availability (what `_previous_dayN` means)
- Open-Meteo docs: "_previous_day1 is the value that was predicted 24 hours before valid time, _previous_day2 48 hours before". We verified with the Single-Runs API (valid day 2026-10-02) that `_previous_dayN` at valid time V equals the latest run initialised at or before V − N·24 h (ECMWF: 00/06/12 Z runs at the matching hours; ICON-seamless: 00/03/06 Z runs, i.e. 3-hourly).
- Run cadence assumed: ICON-seamless 3 h, ECMWF IFS 6 h, JMA GSM 6 h.
- Publication delay assumed (time from run start until data are downloadable): ICON 4 h (DWD ICON-global/EU 00Z are out ~03:30–04:00 UTC, ICON-D2 faster), ECMWF 8 h (00Z open data around 07–08 UTC, as stated in the brief), JMA 6 h. Conservative choices.
- Forecast time F = day D 10:00 Europe/Zurich (`config.yaml auction.forecast_time_local`), D = local delivery day − 1.

## Leakage-safe rule (`*_fc_safe`), re-derived in `tests/test_loaders_weather.py`
For each row T (start of hour, UTC): `valid_om = T + 1 h`; `init_N = floor(valid_om − N·24 h, cadence)`; use day1 if `init_1 + delay ≤ F`, else day2 (the code asserts `init_2 + delay ≤ F` for all rows).
- Result: day1 is used only for delivery-day local hours 00–06 (hour 06 only in summer time, CEST), day2 for all later hours. This is stricter than "day1 before 10:00 local" in the brief, because a forecast for D+1 08:00 made "24 h before" comes from the D 06Z run, which is not published by D 10:00.
- In practice radiation/sunshine `_fc_safe` are effectively day2 forecasts (day1 only covers night hours).
- Assumption: the archived previous-runs values equal what was available in real time (Open-Meteo stores runs as they arrive; we cannot verify retroactively).

## Model choice
- `icon_seamless` is the main forecast: earliest full variable set (from 2024-01-19) and lowest error (safe temp MAE 1.10 °C, ECMWF 1.82 °C, JMA 2.00 °C).
- `jma_seamless` (JMA GSM, ~0.5°) is kept because it is the only real forecast archive back to 2018 (temp/wind/precip/cloud/humidity, no radiation/sunshine). Coarse grid → cold bias ~−1.4 °C, mostly removed by the bias correction (MAE 1.52 °C).
- `best_match`/`gfs_seamless` give GFS 2 m temperature only from 2021-03-24 (radiation from 2024-01-19) – not stored, JMA covers longer. `meteoswiss_icon_ch1` has no previous-runs archive.

## Bias correction
- `*_corr` = forecast + mean(observed − forecast) per calendar month × local hour, fitted only on hours before 2026-09-01 (validation start), so validation/test months are out of sample. Chosen because it beat a single linear fit and a per-month linear fit out of sample (Sep+Oct 2026: ICON 0.939 → 0.929 °C, JMA 2.00 → 1.56 °C).
- For ICON the gain is small (≈1%); for JMA it is large.

## Gaps
- Observed: one 33-h gap in temp/humidity/precip (2021-05-15 13:00 → 2021-05-16 21/22:00 UTC) and a 7-h wind gap (2026-08-17 06–12 UTC) – left NaN. No gaps ≤ 3 h existed, so nothing was interpolated (code and flags are in place). ERA5 can fill these if needed.
- ICON day2 radiation and cloud cover are missing in the archive around 2026-04-10/11: `radiation_wm2_fc_safe` and `cloud_pct_fc_safe` are NaN for 23 hours (2026-04-10 05:00 → 2026-04-11 10:00 UTC); all other `_fc_safe` columns are complete from 2024-01-20 on; feature builder may fall back to `_ecmwf` or day1.
- The "recent" MeteoSwiss file is cached; re-run with `--force` to refresh it.
