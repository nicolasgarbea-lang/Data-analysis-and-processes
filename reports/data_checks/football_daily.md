# Data check: football_daily

- rows: 2953
- first date: 2018-12-01  (local Europe/Zurich calendar day)
- last date: 2026-12-31
- duplicate dates removed: 0
- % missing overall: 45.65

| column | % missing |
|---|---|
| home_game | 0.0 |
| n_home_games | 0.0 |
| kickoff_hour_local | 91.3 |
| home_team | 91.3 |

## Notes

- file covers seasons 2012/2013 .. 2026/2027; last listed Zurich home game: 2026-11-07 (games after the download date are missing; the table is only complete up to then)
- home games in range: 257 (Zurich 146, Grasshoppers 111); missing kick-off times: 0
- days with 2 home games: 0
- Time column read as UK time and converted to Europe/Zurich (+1 h).
- Only Super League games: Swiss Cup and European home games are NOT included.
- kickoff_hour_local / home_team are empty on days without a home game (by design).
