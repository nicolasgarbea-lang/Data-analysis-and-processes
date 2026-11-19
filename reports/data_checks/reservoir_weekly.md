# Data check: reservoir_weekly

- rows: 1403 weeks; first 2000-01-03 last 2026-11-16; duplicates dropped 0
- weekday of measure_date (0=Mon): {0: 1403}  (date = Monday 00:00 = Sunday 24h value)
- gaps != 7 days: 0
- fill % range: 8.3 – 96.2; max capacity changes over time: [8500.0, 8505.0, 8510.0, 8515.0, 8520.0, 8540.0, 8560.0, 8765.0, 8770.0, 8775.0, 8780.0, 8795.0, 8800.0, 8805.0, 8820.0, 8825.0, 8835.0, 8840.0, 8850.0, 8855.0, 8865.0, 8870.0, 8880.0, 8885.0, 8895.0, 8900.0]
- missing: {'reservoir_median_pct_same_week': 52, 'reservoir_vs_median_pct': 52} (median is NaN for year 2000: no earlier history)
- available_from_utc = measure_date (Monday) + 2 days at 18:00 Europe/Zurich (assumption; file was last modified Tue 2026-11-17 14:22 GMT for the 2026-11-16 value)
