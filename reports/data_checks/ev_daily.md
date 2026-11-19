# Data check: ev_daily

- rows: 2953
- first date: 2018-12-01  (local Europe/Zurich calendar day)
- last date: 2026-12-31
- duplicate dates removed: 0
- % missing overall: 11.10

| column | % missing |
|---|---|
| ev_count_city | 0.0 |
| ev_count_city_is_extrapolated | 0.0 |
| ev_count_city_known | 0.0 |
| stations_zh_count | 24.72 |
| stations_zh_count_known | 25.23 |
| charging_kw_zh | 24.72 |
| charging_kw_zh_known | 25.23 |
| charging_kw_zh_backcast | 0.0 |
| bfe_is_held_after_last_month | 0.0 |

## Notes

- EV stock points (30 Sept): 2017: 746, 2018: 887, 2019: 1467, 2020: 2023, 2021: 2979, 2022: 4373, 2023: 5991, 2024: 7571, 2025: 9743
- EV values after 2025-09-30 are extrapolated with the last yearly slope (ev_count_city_is_extrapolated = 1).
- BFE monthly data 2020-11 .. 2026-10 (71 months); monthly value placed on the last day of its month and interpolated linearly.
- stations_zh_count / charging_kw_zh are NaN before 2020-11-30 (series does not exist); the _known versions are NaN before 2020-12-15.
- charging_kw_zh_backcast fills the time before 2020-11 with a straight-line trend of the first 12 months (synthetic, clipped at 0).
- ev_count_city_known on 2026-10-01: 11921 vs interpolated truth 11921
