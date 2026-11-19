# Assumptions – targets and Swiss system data (agent D1)

One line per assumption, with the reason.

## ewz demand (Zurich)
- ewz Bruttolastgang timestamps mark the **end** of the 15-min interval → we subtract 15 min after converting to UTC. *Reason:* the sister file "Netzebenen" documents end labels ("bezieht sich auf die 15 Minuten vor dieser Zeitangabe") and Bruttolastgang = NE5 + NE7 at the same instant (corr 0.999993 at shift 0 vs 0.9966 at ±15 min); the year files also run 00:15 → 00:00 of the next year.
- Local labels are converted with the Europe/Zurich time zone (CET/CEST). *Reason:* the files have 92 rows on spring and 100 rows on autumn DST days, i.e. wall-clock time.
- Autumn DST duplicate labels (02:00–02:45) are assigned to summer/winter time by matching each pair to Netzebenen values, not by file order. *Reason:* the order in the files is inconsistent (27 of 32 pairs would be wrong if the file order was taken as chronological).
- If Netzebenen has no value for a duplicate pair, the file order is assumed chronological. *Reason:* documented fallback; not needed for 2019–2026.
- The two whole days missing in the 2021 file (local 2021-05-30 and 2021-08-07) are filled with NE5 + NE7 from Netzebenen and flagged `is_filled=True`, `fill_method=netzebenen`. *Reason:* it is the same quantity from the same utility (median difference 1.9 kWh on ~60,000 kWh); 192 of 276,288 intervals (0.07 %).
- Gaps of at most 1 h without a Netzebenen value would be linearly interpolated and flagged; longer gaps stay NaN. *Reason:* project rule; no such gap exists at the moment.
- Hourly `load_mw` = mean MW over the UTC hour (sum of four kWh values / 1000). *Reason:* mean MW is not distorted by 23/25-hour days or 3/5-hour blocks.
- Status: no value has status W (final). All data is E (substitute) except F (unchecked) for 2020-06 (17 days) and 2026-11 (1–17 Nov). We keep all values and expose `share_status_f`. *Reason:* E is ewz's corrected value; dropping it would drop everything.
- Publication lag of ewz demand: on 2026-11-19 at 09:05 the file contained data up to the end of 2026-11-17, so at 10:00 on day D only data **up to the end of D−2** may be safe. *Reason:* observed once; the build prompt assumes D−1 – the feature builder should check this (`demand_lag_2d_same_block` is still fine, a D−1 lag is not).
- 2019 mean demand (313 MW) is ~4 % higher than 2020–2026 (295–302 MW). *Reason:* taken as real (COVID-19 and efficiency trend); not corrected.

## CH day-ahead price
- Energy-Charts `price?bzn=CH` is the day-ahead (EPEX SPOT) price in EUR/MWh with UTC timestamps marking the start of the delivery period. *Reason:* API documentation and `unit` field; 1 Oct 2026 00:00 local = 180.35 EUR/MWh as in docs/data_sources.md.
- After the switch to 15-min products (first 15-min value 2026-11-03 23:00 UTC = 4 Nov 00:00 local) the hourly price is the simple mean of the four quarter-hours. *Reason:* project rule; equal to the volume-weighted mean for a flat hourly bid.
- Download in yearly chunks (`start=YYYY-01-01&end=YYYY-12-31`, interpreted as local days by the API) with ≥ 7 s pauses. *Reason:* yearly chunks work (tested) and need 8 calls instead of ~95; the API rate limit is shared with another agent.

## Swiss power (Energy-Charts public_power, CH)
- Swiss `load_mw` is not trusted from 2026-11-16 (values jump to 25–30 GW). *Reason:* known Energy-Charts glitch, confirmed in the data (daily means 26.9 GW on 18 Nov vs ~8.5 GW before).
- Load is also flagged when it is constant ≥ 6 h or outside 50–200 % of the centred 7-day median, and a whole local day is flagged when ≥ 6 of its hours are bad. *Reason:* finds 2023-02-17 (10 h frozen at 4,071 MW) and 2024-12-05 (whole day ~3–4 GW); the centred window is only used for the flag, never as a feature.
- Wind above 500 MW is flagged (`wind_bad`). *Reason:* Swiss wind capacity is < 200 MW; one value of 11,000 MW on 2021-03-31 22:00 UTC.
- `others_mw` is not a measurement (piecewise constant). *Reason:* 2–11 distinct values per year.
- "Renewable share" series (percent) are dropped. *Reason:* not MW and derivable from the other columns.
- Values are hourly in the source; if a 15-min period appears, it would be averaged to the hour. *Reason:* consistency with the price table.

## Swiss solar forecast
- The Energy-Charts day-ahead solar forecast exists for the whole period (2019 →), but its scale is not stable: forecast/actual = 0.05–0.21 for 2019–2023, ≈ 1.0 in 2024, 0.6–0.7 in 2025–2026, while the hourly correlation stays 0.89–0.98. *Reason:* the forecast seems to cover a different (and changing) part of Swiss PV than the actual series. **Recommendation:** use it only after rescaling (e.g. divide by a rolling past ratio) or only from 2024, or use lagged actual solar instead.
- Publication time of the forecast is not documented by Energy-Charts and was not verified. *Reason:* day-ahead solar forecasts on transparency platforms are typically published on the afternoon of the day before delivery, so the forecast for D+1 may only appear **after** our 10:00 forecast time on D. The feature builder should not use it for D+1 unless this is checked; using the forecast for day D (issued on D−1) is safe.
