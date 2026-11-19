# Check: price_ch_hourly.parquet (Energy-Charts day-ahead, bzn=CH)

- rows: 69144 hourly rows
- first / last timestamp_utc: 2018-12-31 23:00:00+00:00 / 2026-11-20 22:00:00+00:00
- missing hours (NaN price), whole file: 0 (0.0000%)
- missing hours 2019-01-01 → 2026-10-31 UTC: 0
- duplicate timestamps removed (overlap of yearly chunks): 0
- null prices in raw JSON: 0
- first 15-min value in source (UTC): 2026-11-03 23:00:00+00:00; hours after that are the mean of 4 quarter-hours
- incomplete hours in the 15-min era (<4 values): 0
- price range: min -463.68, max 871.61, mean 111.61 EUR/MWh
- hours with negative price: 1044

## Gaps (runs of missing hours)

none

## Mean price per year (EUR/MWh)

| year | mean | min | max |
|---|---|---|---|
| 2018 | 50.3 | 50.3 | 50.3 |
| 2019 | 40.9 | -39.5 | 108.1 |
| 2020 | 34.0 | -59.6 | 126.7 |
| 2021 | 114.9 | -79.4 | 532.2 |
| 2022 | 281.6 | -1.0 | 871.6 |
| 2023 | 107.5 | -142.9 | 268.8 |
| 2024 | 76.0 | -427.5 | 310.6 |
| 2025 | 101.7 | -262.2 | 318.0 |
| 2026 | 139.8 | -463.7 | 596.7 |
