# Data check: co2_eua_daily

- source: EEX primary-market auction reports (archive zip 2012-2025 + 2026 xlsx), official
- auction rows read: 3043; successful used: 3039; duplicate auction rows dropped: 1
- rows (auction days): 1724; in 2019-01-01→2026-10-31: 1704
- first: 2018-12-03  last: 2026-11-19
- range: min 14.60, max 97.51 EUR/t
- gaps > 7 days without auction (date after gap, gap days): 2019-01-07(21), 2020-01-07(22), 2021-01-29(46), 2022-01-10(21), 2023-01-09(21), 2024-01-15(28), 2025-01-07(22), 2026-01-07(23)
- daily value = volume-weighted mean of all successful auctions that day
- no auctions on most Fridays/weekends, in parts of August and around New Year → as-of join with last value
- available_from_utc = auction day 12:00 Europe/Zurich (results published ~11:15)
