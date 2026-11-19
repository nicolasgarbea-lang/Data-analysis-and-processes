# Assumptions – calendar, EVs, events, football (agent D3)

One line per assumption, with the reason.

## Calendar
- `date` is the local Europe/Zurich calendar day for every daily table – blocks and holidays follow the local clock.
- Public holidays = `holidays.Switzerland(subdiv="ZH")` (9 per year) + Berchtoldstag 2 Jan – the package omits Berchtoldstag, but the city (and its school calendar) treats it as a day off.
- Easter Sunday, Pentecost Sunday and the Federal Fast Sunday are not flagged as holidays – they are Sundays anyway (`is_weekend`).
- Sechseläuten Monday and Knabenschiessen Monday are half-holidays (afternoon off), not full holidays – shops and offices in the city close in the afternoon only.
- Half-holiday dates come from the official Stadt Zürich school calendar (it lists the school-free day each year) – an official source that covers every year 2019–2026.
- Sechseläuten 2020 has no half-holiday – cancelled (COVID) and not in the school calendar; 2021 keeps the flag because the school calendar lists 19 Apr 2021 as school-free, although the public festival was cancelled (Böögg burned in Uri, [source](https://www.sechselaeuten.ch/assets/downloads/2021/Medienmitteilungen/MM_ZZZ_Boegg%20SL_2021.pdf)).
- Knabenschiessen 2020/2021 keep the half-holiday flag (school-free per school calendar) but are left out of the events table – 2020 was cancelled and 2021 was only a small shoot-off without the fair ([Blick](https://www.blick.ch/life/freizeit/ohne-chilbi-knabenschiessen-2021-nur-mit-ehemaligen-gewinnern-id16591545.html)).
- Bridge day = working day with a full holiday on one side and a weekend or holiday on the other (e.g. Friday after Ascension) – the usual definition; half-holidays are not used for it.
- School-calendar end dates are exclusive – verified: single-day entries such as "Nationalfeiertag 2018-08-01 → 2018-08-02" and "Knabenschiessen 2026-09-14 → 2026-09-15" cover one day, and summer holidays "KW 29–33" end on the Saturday before the first school day.
- School-holiday rows = summaries starting with "Schulen Stadt Zürich" that contain "ferien" or "schulfrei", excluding "Schulschluss" (half day), "Schuljahresbeginn" and "1. Schultag" – those are not days off.
- Type by keyword (first hit): Weihnacht → christmas, Sportferien → sport, Frühling → spring, Sommer → summer, Herbst → autumn, else school_free_day – the 2022/2025 entries "Gründonnerstag … Frühlingsferien" become spring.
- `covid_stringency` = OxCGRT national stringency index for Switzerland (official academic tracker, open on GitHub) – covers 2020-01-01..2022-12-31 without gaps.
- `covid_stringency_filled` = 0 before 2020 and after 2022 – no measures before 2020; OxCGRT stopped tracking at the end of 2022, when the index was already 5.6 (only minor measures left).
- COVID policy is treated as known on the day – measures were announced before they started; the index itself is a historical reconstruction (documented limitation).

## EVs and charging
- Electric cars = `Treibstoffart2Lang == "Elektrisch"` (battery electric) only; hybrids are excluded – as the brief says, and hybrids charge little from the grid.
- 30 Sept count of year Y is public from **1 Aug of year Y+1** – the dataset page shows the 2025 data (time range 2002–2025) was last updated on 13 Jul 2026; we round up to 1 Aug as a safety margin (one observation only, so it is an assumption).
- `ev_count_city_known` = last published value + last published yearly growth (straight line), not a flat carry-forward – the stock grows steadily (+20–50 % per year), so a flat value would be 10–14 months stale and biased low; the extrapolation uses only published numbers, so it is leakage-safe.
- `ev_count_city` after 2025-09-30 is extrapolated with the 2024→2025 slope – no newer count exists yet; flagged in `ev_count_city_is_extrapolated`.
- BFE monthly values describe the state at the end of the month – the file has no day; end of month is the natural reading of a monthly stock.
- BFE month M is public from the **15th of month M+1** – the October 2026 value was online when we downloaded on 19 Nov 2026 ("early next month"); the 15th is a cautious choice.
- `_known` BFE columns carry the last published month forward – monthly changes are a few percent, simpler than extrapolating.
- BFE July 2021 is missing in the source – the daily "true" columns interpolate across it; `_known` columns keep the June value one month longer.
- BFE series start 2020-11: values before are NaN – the series does not exist; `charging_kw_zh_backcast` is a rough straight-line back-extrapolation (first 12 months, clipped at 0) for anyone who needs a full-length column; it is synthetic.
- After the last BFE month (2026-10) the true columns are held flat – only Nov–Dec 2026, outside the test month.
- `stations_ZH_count` and `chargingPower_ZH_sum` are for the canton of Zurich, not the city – the BFE file has no city level.

## Events
- Only events with a confirmed date and a source URL are in `data/manual/events_zurich.csv`; everything else is in `docs/events_unverified.md` – rule "no invented data".
- One CSV row per event day (multi-day events are expanded) – the daily table can then take the max size per day.
- Size: 3 = several hundred thousand visitors (Street Parade ~800k–920k, Züri Fäscht ~2M), 2 = tens of thousands (Sechseläuten, Knabenschiessen, Pride demo, Silvesterzauber ~130–150k at midnight, stadium concerts/games ~20–50k, UCI Worlds, Caliente), 1 = smaller or spread out (marathon, Silvesterlauf, Weltklasse city day, film festival) – rough judgement from visitor numbers in the sources.
- Silvesterzauber is size 2, not 3 – the crowd gathers only for a few hours around midnight.
- Weltklasse: day 1 (city event) size 1, day 2 (stadium meeting at Letzigrund) size 2 – the dates listed by Wikipedia are two days.
- Knabenschiessen covers Saturday–Monday – the fair runs over the second weekend of September through Monday; the Monday is confirmed by the school calendar.
- Cancelled years (COVID 2020/2021) are absent from the table – no event, `event_size` = 0.
- Future 2026 events (Nov–Dec, e.g. Silvesterlauf 13 Dec, Silvesterzauber 31 Dec) are listed from announcements – they are known in advance; outside the test period.
- Zurich Film Festival 2025: Unifrance gives 25 Sep–10 Oct, the festival's own site 25 Sep–5 Oct; we use 25 Sep–5 Oct – the official dates win.
- Events are treated as known in advance – they are announced months ahead.

## Football
- `Time` in SWZ.csv is UK time – Saturday games show 17:00/19:30 and Sunday 13:15/15:30 while Super League kick-offs are 18:00/20:30 and 14:15/16:30 Swiss time; we convert Europe/London → Europe/Zurich (+1 h all year).
- Only Super League games – the file has no cup, European or friendly games (documented limitation).
- Grasshoppers have no games in 2019/20 and 2020/21 – they played in the second division (Challenge League), which this file does not cover; `home_game` = 0 for GC in that period.
- Super League games after the download date (19 Nov 2026) are missing – the file lists results, not future fixtures; irrelevant for the October 2026 test month.
- Both clubs play at Stadion Letzigrund – so one `home_game` flag covers both; no day has two home games.
