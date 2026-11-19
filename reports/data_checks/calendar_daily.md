# Data check: calendar_daily

- rows: 2953
- first date: 2018-12-01  (local Europe/Zurich calendar day)
- last date: 2026-12-31
- duplicate dates removed: 0
- % missing overall: 18.59

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

## Notes

- public holidays per year (incl. Berchtoldstag): {2018: 2, 2019: 10, 2020: 10, 2021: 10, 2022: 10, 2023: 10, 2024: 10, 2025: 10, 2026: 10}
- bridge days: 18; half-holidays: 15
- school-holiday days: 737; types: {'summer': 264, 'christmas': 107, 'spring': 104, 'sport': 96, 'autumn': 96, 'school_free_day': 70}
- DST days: 16 (hours_in_day values [np.int64(23), np.int64(24), np.int64(25)])
- holiday_name / half_holiday_name / school_holiday_type are empty on normal days (by design).
- covid_stringency is NaN outside 2020-01-01..2022-12-31 (OxCGRT coverage); use covid_stringency_filled (0 outside) in models.
