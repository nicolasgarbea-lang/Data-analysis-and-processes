# Data check: calendar_features_daily

- rows: 2953
- first date: 2018-12-01  (local Europe/Zurich calendar day)
- last date: 2026-12-31
- duplicate dates removed: 0
- % missing overall: 22.99

| column | % missing |
|---|---|
| weekday | 0.0 |
| month | 0.0 |
| day_of_year | 0.0 |
| is_weekend | 0.0 |
| is_holiday | 0.0 |
| holiday_name | 97.22 |
| is_half_holiday | 0.0 |
| half_holiday_name | 99.49 |
| is_bridge_day | 0.0 |
| is_school_holiday | 0.0 |
| school_holiday_type | 75.04 |
| days_to_next_holiday | 0.0 |
| days_since_last_holiday | 0.0 |
| is_christmas_period | 0.0 |
| is_dst_change_day | 0.0 |
| hours_in_day | 0.0 |
| covid_stringency | 62.89 |
| covid_stringency_filled | 0.0 |
| ev_count_city | 0.0 |
| ev_count_city_is_extrapolated | 0.0 |
| ev_count_city_known | 0.0 |
| stations_zh_count | 24.72 |
| stations_zh_count_known | 25.23 |
| charging_kw_zh | 24.72 |
| charging_kw_zh_known | 25.23 |
| charging_kw_zh_backcast | 0.0 |
| bfe_is_held_after_last_month | 0.0 |
| event_size | 0.0 |
| n_events | 0.0 |
| event_name | 93.84 |
| event_types | 93.84 |
| home_game | 0.0 |
| n_home_games | 0.0 |
| kickoff_hour_local | 91.3 |
| home_team | 91.3 |

## Notes

- merged from calendar_daily, ev_daily, events_daily, football_daily on `date` (local Zurich day); 35 value columns
- see the check files of the parts for details; text columns are empty on normal days by design
