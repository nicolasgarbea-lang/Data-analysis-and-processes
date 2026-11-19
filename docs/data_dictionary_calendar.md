# Data dictionary – calendar, EVs, events, football (agent D3)

All tables are **daily**, keyed by `date` = **local Europe/Zurich calendar day** (plain date, no time zone),
one row per day from **2018-12-01 to 2026-12-31**, no gaps. `calendar_features_daily.parquet` holds all columns below
in one table.

"Lag" = when the value is known. "In advance" = known long before the day (calendar, fixtures, announced events).
Columns marked **not for features** use information published later; use the `_known` column instead.

## calendar_daily.parquet (`src/data/load_calendar.py`)

| column | unit / values | source | time convention | publication lag |
|---|---|---|---|---|
| weekday | 0 = Mon … 6 = Sun | computed | local day | in advance |
| month | 1–12 | computed | local day | in advance |
| day_of_year | 1–366 | computed | local day | in advance |
| is_weekend | 0/1 (Sat, Sun) | computed | local day | in advance |
| is_holiday | 0/1 | `holidays.Switzerland(subdiv="ZH")` + Berchtoldstag 2 Jan | local day | in advance |
| holiday_name | text, empty on normal days | as above | local day | in advance |
| is_half_holiday | 0/1 (afternoon off in the city) | Sechseläuten Monday, Knabenschiessen Monday; dates from the Stadt Zürich school calendar | local day | in advance |
| half_holiday_name | text, empty on normal days | as above | local day | in advance |
| is_bridge_day | 0/1 | computed: working day with a holiday on one side and a weekend/holiday on the other | local day | in advance |
| is_school_holiday | 0/1 | Stadt Zürich `schulferien.csv` (end date exclusive) | local day | in advance |
| school_holiday_type | christmas / sport / spring / summer / autumn / school_free_day; empty otherwise | keyword on `summary` | local day | in advance |
| days_to_next_holiday | days (0 on a holiday) | computed from is_holiday | local day | in advance |
| days_since_last_holiday | days (0 on a holiday) | computed from is_holiday | local day | in advance |
| is_christmas_period | 0/1 (24 Dec – 2 Jan) | computed | local day | in advance |
| is_dst_change_day | 0/1 | tz database Europe/Zurich | local day | in advance |
| hours_in_day | 23 / 24 / 25 hours | tz database | local day | in advance |
| covid_stringency | index 0–100, NaN outside 2020-01-01..2022-12-31 | OxCGRT `OxCGRT_compact_national_v1.csv`, CHE, `StringencyIndex_Average` | daily (national) | historical index; for 2020–2022 policy was announced before it applied (treat as known on the day) |
| covid_stringency_filled | index 0–100 | as above, 0 before 2020 and after 2022 | daily | as above |

## ev_daily.parquet (`src/data/load_ev.py`)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| ev_count_city | electric cars (count), interpolated | Stadt Zürich VER200OD2001.csv, `Treibstoffart2Lang == "Elektrisch"`, summed over quarters & legal forms; points on 30 Sept, straight line between them; after 2025-09-30 extended with the last yearly slope | local day | **not for features** (uses values published up to ~10 months later) |
| ev_count_city_is_extrapolated | 0/1 | flag: date after the last 30 Sept point (2025-09-30) | local day | – |
| ev_count_city_known | electric cars (count) | same source; last published 30 Sept value + last published yearly growth (straight line) | local day | 30 Sept of year Y assumed public on **1 Aug of Y+1** |
| stations_zh_count | charging stations, canton Zurich | BFE `ich_tanke_strom_Kennzahlen_monatlich.csv`, `stations_ZH_count`; month value on last day of month, linear in between; NaN before 2020-11-30, held flat after 2026-10-31 | local day | **not for features** |
| stations_zh_count_known | charging stations | same, last published month carried forward | local day | month M public on the **15th of M+1** |
| charging_kw_zh | kW installed charging power, canton Zurich | BFE, `chargingPower_ZH_sum`; same handling as stations | local day | **not for features** |
| charging_kw_zh_known | kW | same, last published month carried forward | local day | month M public on the 15th of M+1 |
| charging_kw_zh_backcast | kW | observed (interpolated) where available; before 2020-11 a straight-line trend of the first 12 months, clipped at 0 (**synthetic**) | local day | **not for features** before 2020-12 (built with later data) |
| bfe_is_held_after_last_month | 0/1 | flag: date after the last BFE month (2026-10) | local day | – |

## events_daily.parquet (`src/data/load_events.py`, input `data/manual/events_zurich.csv`)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| event_size | 0 = none, 1 = small/medium, 2 = large (tens of thousands), 3 = huge (hundreds of thousands) – max over the day | hand-made table, one source URL per row | local day | in advance (events are announced months ahead) |
| n_events | count of distinct events that day | same | local day | in advance |
| event_name | names joined by " \| ", empty otherwise | same | local day | in advance |
| event_types | parade / festival / tradition / sport / concert / culture, joined by " \| " | same | local day | in advance |

`events_zurich.csv`: `date` (local day, one row per event day), `event`, `type`, `size` (1–3), `source_url`.

## football_daily.parquet (`src/data/load_football.py`)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| home_game | 0/1 | football-data.co.uk `SWZ.csv`, `Home` in {Zurich, Grasshoppers} | local day of kick-off | in advance (fixtures published weeks ahead) |
| n_home_games | count | same | local day | in advance |
| kickoff_hour_local | hour in Swiss local time, decimal (20.5 = 20:30), earliest game | `Time` column, which is **UK time** → converted to Europe/Zurich | local | in advance |
| home_team | Zurich / Grasshoppers | same | – | in advance |

## calendar_features_daily.parquet (`src/data/merge_calendar.py`)
Left join of the four tables above on `date`; same columns, one row per day.
