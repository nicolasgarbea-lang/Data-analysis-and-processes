# Data check: weather_archive_hourly (Open-Meteo archive, ERA5 reanalysis)

- Rows: 69,479; timestamp_utc 2018-12-01 00:00:00+00:00 -> 2026-11-03 22:00:00+00:00
- Duplicates removed: 0
- Time shift: Open-Meteo stamp -1 h -> START of hour. Units: sunshine min, wind m/s.
- Reanalysis = not available at forecast time. Cross-check / gap filler only.

| column | missing | missing % |
|---|---|---|
| temp_c_era5 | 0 | 0.000% |
| radiation_wm2_era5 | 0 | 0.000% |
| sunshine_min_era5 | 0 | 0.000% |
| wind_ms_era5 | 0 | 0.000% |
| precip_mm_era5 | 0 | 0.000% |
| cloud_pct_era5 | 0 | 0.000% |
| humidity_pct_era5 | 0 | 0.000% |
