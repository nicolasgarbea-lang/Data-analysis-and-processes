# Data check: events_daily

- rows: 2953
- first date: 2018-12-01  (local Europe/Zurich calendar day)
- last date: 2026-12-31
- duplicate dates removed: 0
- % missing overall: 46.92

| column | % missing |
|---|---|
| event_size | 0.0 |
| n_events | 0.0 |
| event_name | 93.84 |
| event_types | 93.84 |

## Notes

- event rows in manual file: 183 on 182 days; events: 25
- days with event_size 3 / 2 / 1: 12 / 64 / 106
- rows outside the daily range (ignored): 0
- event_name / event_types are empty on days without an event (by design).
- Cancelled years (COVID 2020/2021) are simply absent: event_size = 0 on those days.
