# Data check: weather_observed_hourly (MeteoSwiss SMA Zürich-Fluntern)

- Rows: 69,839 (hourly, complete UTC grid)
- First / last timestamp_utc: 2018-12-01 00:00:00+00:00 / 2026-11-18 22:00:00+00:00
- Duplicates removed after joining historical + recent files: 0
- Time shift: MeteoSwiss hourly stamp = END of interval -> shifted -1 h to START of hour.
- Gaps <= 3 h linearly interpolated (flag column `<col>_interpolated`), longer gaps left NaN.

| column | missing before fill | missing before fill % | filled (<=3 h) | still missing | still missing % | long gaps (>3 h) |
|---|---|---|---|---|---|---|
| temp_c | 33 | 0.047% | 0 | 33 | 0.047% | 1 |
| sunshine_min | 0 | 0.000% | 0 | 0 | 0.000% | 0 |
| radiation_wm2 | 0 | 0.000% | 0 | 0 | 0.000% | 0 |
| wind_ms | 7 | 0.010% | 0 | 7 | 0.010% | 1 |
| precip_mm | 34 | 0.049% | 0 | 34 | 0.049% | 1 |
| humidity_pct | 33 | 0.047% | 0 | 33 | 0.047% | 1 |

## Gaps longer than 3 h (left as NaN)

- `temp_c`: 2021-05-15 13:00:00+00:00 -> 2021-05-16 21:00:00+00:00 (33 h)
- `wind_ms`: 2026-08-17 06:00:00+00:00 -> 2026-08-17 12:00:00+00:00 (7 h)
- `precip_mm`: 2021-05-15 13:00:00+00:00 -> 2021-05-16 22:00:00+00:00 (34 h)
- `humidity_pct`: 2021-05-15 13:00:00+00:00 -> 2021-05-16 21:00:00+00:00 (33 h)

## Gaps of 1-3 h (interpolated)

- `temp_c`: 0 gaps, 0 hours
- `sunshine_min`: 0 gaps, 0 hours
- `radiation_wm2`: 0 gaps, 0 hours
- `wind_ms`: 0 gaps, 0 hours
- `precip_mm`: 0 gaps, 0 hours
- `humidity_pct`: 0 gaps, 0 hours
