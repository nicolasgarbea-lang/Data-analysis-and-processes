# Check: demand_ewz.parquet / demand_ewz_hourly.parquet (ewz Bruttolastgang, Zurich)

- raw rows read: 276096; autumn DST label pairs resolved: 32 (none dropped)
- 15-min rows: 276288; first / last timestamp_utc (interval start): 2018-12-31 23:00:00+00:00 / 2026-11-17 22:45:00+00:00
- local time: 2019-01-01 00:00:00+01:00 → 2026-11-17 23:45:00+01:00 (interval start)
- duplicate UTC timestamps after conversion: 0
- missing 15-min intervals before filling: 192 (0.069%); after filling: 0
- filled intervals: 192 ({'netzebenen': 192})
- status counts (15-min): {'E': 272832, 'F': 3264, nan: 192}  (W = final, E = substitute, F = not yet checked; no W at all in the current files, so `share_non_final` is 1 everywhere — use `share_status_f`)
- hourly rows: 69072; hours with load_mw missing: 0; hours before 2026-11-01 UTC missing: 0
- load_mw range: min 182.8, max 463.1, mean 299.9 MW
- local days with ≠ 24 hours (should be only DST days, 23 / 25 h, plus partial first/last day): {'2019-03-31': 23, '2019-10-27': 25, '2020-03-29': 23, '2020-10-25': 25, '2021-03-28': 23, '2021-10-31': 25, '2022-03-27': 23, '2022-10-30': 25, '2023-03-26': 23, '2023-10-29': 25, '2024-03-31': 23, '2024-10-27': 25, '2025-03-30': 23, '2025-10-26': 25, '2026-03-29': 23, '2026-10-25': 25}

## Gaps in the raw data

| first interval start (UTC) | last interval start (UTC) | intervals | filled with |
|---|---|---|---|
| 2021-05-29 22:00:00+00:00 | 2021-05-30 21:45:00+00:00 | 96 | netzebenen |
| 2021-08-06 22:00:00+00:00 | 2021-08-07 21:45:00+00:00 | 96 | netzebenen |

## Status F by month (local time)

| month | intervals with F |
|---|---|
| 2020-06 | 1632 |
| 2026-11 | 1632 |

## Yearly mean load (MW, local calendar year)

| year | mean MW | min | max |
|---|---|---|---|
| 2019 | 312.9 | 193.5 | 463.1 |
| 2020 | 299.4 | 182.8 | 455.3 |
| 2021 | 301.1 | 190.0 | 458.1 |
| 2022 | 302.2 | 191.8 | 439.1 |
| 2023 | 295.1 | 184.8 | 436.6 |
| 2024 | 295.3 | 185.3 | 435.5 |
| 2025 | 295.9 | 186.0 | 435.7 |
| 2026 | 297.2 | 189.3 | 438.5 |
