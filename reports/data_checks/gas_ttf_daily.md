# Data check: gas_ttf_daily

- source: Yahoo Finance `TTF=F` (UNOFFICIAL fallback; HSG LSEG/Bloomberg export not available)
- rows: 2003 trading days (raw bars 2006, 3 with null close dropped, 0 duplicate dates dropped)
- first: 2018-12-03  last: 2026-11-18
- range: min 3.51, max 339.20 EUR/MWh (max on 2022-08-26)
- gaps > 4 calendar days (before date shown): 1 → 2024-04-02
- daily moves > 30%: 4 → 2019-09-30=16.4, 2022-02-24=134.3, 2022-03-02=165.5, 2026-03-02=44.5
- available_from_utc = trading day 18:00 Europe/Zurich (after ICE Endex settlement); use only rows with available_from_utc <= forecast time
