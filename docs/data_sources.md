# Data sources – what exists and how it looks

**Focus:** Switzerland, with the **city of Zurich (ewz)** as our DSO. The price is Swiss (one price for all of Switzerland). Demand, weather, EVs, holidays and events are for Zurich.

*Checked on 19 Nov 2026 by downloading small samples from every source, then used in the build. Everything below is free unless noted. The open questions of the first check are answered in "What we verified during the build" at the end. The company in the project (Limmat Energie AG) is fictional; the data is the real ewz load of the city of Zurich.*

## Summary

| Input | Recommended source | Step | Period | Access |
|---|---|---|---|---|
| **Demand (target)** | ewz Bruttolastgang Stadt Zürich | 15 min | 2019 → 18 Nov 2026 | Free, CC0 |
| **Price (target)** | Energy-Charts API, `bzn=CH` | 1 h (15 min from 4 Nov 2026) | 2019 → tomorrow | Free, CC BY 4.0 |
| Weather (observed) | MeteoSwiss station Zürich-Fluntern (SMA) | 1 h | 2010 → yesterday | Free |
| Weather (forecast) | Open-Meteo "previous runs" API (ICON main, ECMWF, JMA) | 1 h | ICON real forecasts from 2024-01-19; JMA back to 2018 | Free, CC BY 4.0 |
| Weather (reanalysis, check only) | Open-Meteo archive API (ERA5) | 1 h | 2018-12 → now (~5 days lag) | Free, CC BY 4.0 |
| Weather Europe (price driver) | Open-Meteo previous-runs API, 9 points in DE/FR/IT/CH (ICON, JMA) | 1 h | ICON from 2024-01-19, JMA from 2018-12 | Free, CC BY 4.0 |
| Rooftop solar | Energy-Charts Swiss solar output | 1 h | 2019 → now | Free |
| EVs | Stadt Zürich car stock by fuel + BFE charging stations per canton | yearly / monthly | 2002–2025 / 2020-11 → 2026-10 | Free |
| Holidays | Python `holidays` (ZH) + Stadt Zürich school holidays file | daily | 2018 → 2030 | Free |
| Events | Hand-made table + football-data.co.uk results | daily | 2019 → 2026 | Free |
| Neighbour prices | Energy-Charts `bzn=DE-LU`, `FR`, `AT`, `IT-North` | 1 h (15 min from 1 Oct 2025) | 2019 → now | Free, CC BY 4.0 |
| Gas (TTF) | **Used: Yahoo `TTF=F` (unofficial fallback)**; the HSG LSEG/Bloomberg export was not available | daily | 2019 → Oct 2026 | unofficial, personal/educational use |
| CO₂ (EUA) | **Used: EEX primary-market auction results** (archive zip 2012–2025 + 2026 xlsx, found on the EEX site) | auction days | 2012 → 19 Nov 2026 | free, official |
| Reservoir level | BFE weekly fill of Swiss reservoirs | weekly | 2000 → 16 Nov 2026 | Free |
| EUR/CHF | ECB data API | daily | long history | Free |
| COVID stringency | OxCGRT `OxCGRT_compact_national_v1.csv` (GitHub), Switzerland | daily | 2020-01-01 → 2022-12-31 | CC BY 4.0 |
| German TSO forecasts (stored, not used) | Energy-Charts `public_power_forecast?country=de` | 1 h | 2019 → Nov 2026 | Free; publication time unverified |

The test month (**October 2026**) is fully covered by the two targets and by every main input.

---

## 1. Targets

### Demand – ewz "Bruttolastgang Stadt Zürich" (recommended)
- **URL:** `https://data.stadt-zuerich.ch/dataset/ewz_bruttolastgang_stadt_zuerich/download/{YYYY}_ewz_bruttolastgang.csv`, one file per year (2019–2026), ~1.3 MB each. It redirects, so use `curl -L`.
- **What:** total electricity delivered to end users in the city of Zürich, in **kWh per 15 minutes** (65,900 kWh in 15 minutes ≈ 264 MW).
- **Structure:**

  | zeitpunkt | bruttolastgang | status |
  |---|---|---|
  | 2026-10-25T00:00 | 61600.247427 | E |

- **Status:** W = final, E = substitute value, F = not yet checked. Values can still change for up to 6 months.
- **Watch out:**
  - Timestamps are in **local time**. Daylight-saving days have 92 or 100 rows, and the autumn change repeats 02:00–02:45.
  - The 2019 file starts at 00:15 while 2026 starts at 00:00, so check whether each timestamp marks the start or the end of its interval.
- **Alternatives:**
  - ewz "Stromabgabe Netzebenen" (one 14 MB CSV, `Timestamp,Value_NE5,Value_NE7`). It is in **UTC**, so there are no daylight-saving duplicates, and it splits medium and low voltage.
  - Basel-Stadt dataset 100233 on data.bs.ch, in UTC, 2012 → now.
  - Swissgrid "Energie Übersicht Schweiz" xlsx for the Swiss total, up to 31 Oct 2026.

### Price – Energy-Charts day-ahead price CH (recommended)
- **URL:** `https://api.energy-charts.info/price?bzn=CH&start=YYYY-MM-DD&end=YYYY-MM-DD`
- **Structure (JSON):**
  ```json
  {"unix_seconds": [1790805600, ...], "price": [180.35, ...], "unit": "EUR / MWh", "license_info": "CC BY 4.0 ...", "deprecated": false}
  ```
  Example: 1 Oct 2026, 00:00 Swiss time → 180.35 EUR/MWh.
- **Watch out:**
  - Timestamps are UTC and prices are in **EUR**.
  - Data is hourly up to 3 Nov 2026 and in **15-minute steps after that**. October 2026 is still hourly.
  - The API blocks you after ~15 quick calls. Download in monthly pieces with pauses.

---

## 2. Demand drivers

### Weather (observed) – MeteoSwiss Open Data
- **URLs (station SMA = Zürich-Fluntern):**
  - `https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/sma/ogd-smn_sma_h_historical_2010-2019.csv`
  - `.../sma/ogd-smn_sma_h_historical_2020-2029.csv`
  - `.../sma/ogd-smn_sma_h_recent.csv` (this year up to yesterday)
  - Basel: replace `sma` with `bas`.
  - Code list: `.../ogd-smn_meta_parameters.csv`
- **Structure:** semicolon-separated, 36 columns. The ones we need:

  | station_abbr | reference_timestamp | tre200h0 | sre000h0 | gre000h0 | fkl010h0 | rre150h0 | ure200h0 |
  |---|---|---|---|---|---|---|---|
  | SMA | 01.10.2026 10:00 | 20.8 | 14 | 353 | … | … | … |

  The columns are temperature (°C), sunshine (minutes per hour), solar radiation (W/m²), wind (m/s), rain (mm) and humidity (%).
- **Watch out:**
  - Timestamps are **UTC**.
  - The historical and recent files overlap, so remove duplicates after joining them.

### Weather (forecast) – Open-Meteo
At 11:00 we only know a **forecast** of tomorrow's weather.
- **Previous-runs API (the real forecast made the day before):** `https://previous-runs-api.open-meteo.com/v1/forecast?latitude=47.378&longitude=8.565&hourly=temperature_2m_previous_day1,shortwave_radiation_previous_day1&models=ecmwf_ifs025&timezone=GMT`
  - Real model forecasts exist only from about **2024**.
  - For 2019–2023 the default model returns values, but where they come from is unclear.
- **Archive API (model estimate of actual weather):** `https://archive-api.open-meteo.com/v1/archive?...`
- **Structure (JSON):** `{"hourly": {"time": [...], "temperature_2m": [...], ...}}`. Wind is in **km/h** here, not m/s.
- **Option for the team:** train on observed MeteoSwiss weather and say that this flatters the model, or use forecasts and accept the shorter history.

### Rooftop solar – Energy-Charts
- **Actual output:** `https://api.energy-charts.info/public_power?country=ch&start=..&end=..`
  - JSON: `unix_seconds` + `production_types: [{"name": "Solar", "data": [...]}, ...]`, in MW, hourly.
  - Example: 1 Oct 2026, 12:00 Swiss time → 3,397 MW.
  - The same call also returns Load, Hydro, Nuclear and Wind for Switzerland.
- **Day-ahead forecast:** `https://api.energy-charts.info/public_power_forecast?country=ch&production_type=solar&forecast_type=day-ahead&start=..&end=..`
  - Its peak was ~1.2 GW against 3.4 GW actual on the same day, so the two seem to cover different parts of Swiss solar. Check before using them together.

### EVs
- **Car stock in the city by fuel type:** `https://data.stadt-zuerich.ch/dataset/prd_ssz_fz_pw_bestand_jahr_quartier_antriebsart_rechtsform_od2001/download/VER200OD2001.csv`
  - Yearly, counted on 30 Sept, 2002–2025.
  - Columns: `StichtagDatJahr, QuarLang, KreisLang, Treibstoffart2Lang, AnzFahrzeuge, ...`
  - Electric cars in Zürich: 1,467 (2019) → 2,979 (2021) → 5,991 (2023) → 9,743 (2025). Interpolate between the yearly values to get a daily value.
- **Charging stations per canton, monthly (BFE):** `https://www.uvek-gis.admin.ch/BFE/ogd/57/ich_tanke_strom_Kennzahlen_monatlich.csv`
  - 2020-11 → 2026-10.
  - Columns include `stations_ZH_count`, `chargingPower_ZH_sum` (kW).
  - October 2026: 2,605 stations and 158,188 kW in Kanton Zürich.
- **Electric share of cars, Kanton Zürich:** `https://www.web.statistik.zh.ch/ogd/data/KANTON_ZUERICH_607.csv` (yearly, 6.6% in 2025).
- **Live charging-point status (BFE):** exists, but it is only a snapshot with no history, so we cannot use it for training.

### Holidays
- **Public holidays:** Python package `holidays`, `holidays.Switzerland(subdiv="ZH")`. It gives 9 days in 2026. Add Berchtoldstag (2 Jan), Sechseläuten and Knabenschiessen by hand.
- **School holidays and city days off:** `https://data.stadt-zuerich.ch/dataset/ssd_schulferien/download/schulferien.csv`, 2018 → 2030.

  | start_date | end_date | summary |
  |---|---|---|
  | 2026-10-05T00:00:00Z | 2026-10-17T00:00:00Z | Schulen Stadt Zürich: Herbstferien |

  The end date looks exclusive (the holiday ends the day before). Classify the summary with keywords (Herbst, Sport, Frühling, Sommer, Weihnacht).

### Events
- No open dataset of past events exists, so we **build a small table by hand** (~40 rows): `date, event, type, expected_size`.
  - Sechseläuten: 2019-04-08, 2021-04-19, 2022-04-25, 2023-04-17, 2024-04-15, 2025-04-28, 2026-04-20
  - Street Parade (confirmed with sources in `data/manual/events_zurich.csv`): 2019-08-10, 2022-08-13, 2023-08-12, 2024-08-10, 2025-08-09, 2026-08-08. 2020 and 2021 were cancelled.
  - Züri Fäscht: 5–7 July 2019 and 7–9 July 2023 (confirmed). It did not take place in 2026.
  - The final table has 183 event-day rows, each with a source URL; events whose date could not be confirmed are listed in `docs/events_unverified.md`.
- **Football:** `https://www.football-data.co.uk/new/SWZ.csv`, Swiss Super League results 2012 → now.
  - Columns: `Date, Time, Home, Away, ...`
  - Keep home games of FC Zürich and Grasshoppers.

---

## 3. Price drivers

| Driver | URL | Step | Structure / example |
|---|---|---|---|
| DE / FR price | `https://api.energy-charts.info/price?bzn=DE-LU` (or `FR`) | 15 min | Same JSON as the CH price |
| Gas TTF | HSG LSEG/Bloomberg. Fallback: `https://query1.finance.yahoo.com/v8/finance/chart/TTF=F?interval=1d&period1=..&period2=..` (unofficial) | daily | EUR/MWh closing price, 2019-01-02 → 2026-10-30 |
| CO₂ EUA | HSG LSEG/Bloomberg. Fallback: EEX auction archive zip (one xlsx per year) | daily | `Date, Time, Auction Name, ..., Auction Price €/tCO2` → `2025-12-15, 11:00, ..., 84.6` |
| Reservoir level | `https://www.bfe-ogd.ch/ogd17/ogd17_fuellungsgrad_speicherseen.csv` | weekly | Date, fill in GWh for Wallis, Graubünden, Tessin, rest of CH, total, and maxima → `2026-11-16, ..., 5546 (CH total), ..., 8895 (CH max)` |
| EUR/CHF | `https://data-api.ecb.europa.eu/service/data/EXR/D.CHF.EUR.SP00.A?startPeriod=..&format=csvdata` | daily | `2026-10-01, 0.9437` |

**Timing rule:** use only what is known **on day D at 10:00** (forecast time = gate closure 11:00 − 1 h). For daily drivers (gas, CO₂, FX) that means the value from day D−1 or earlier. The reservoir value is measured on Sunday 24:00 and counted as known from Thursday 23:59 (first used on Friday). Neighbour prices are known for day D only (their D+1 auction closes at 12:00).

---

## 4. How the data fits together (feature table)

One row per **4-hour block** (6 per day), everything converted to **Swiss local time** and summed or averaged per block:

| Column | From | How |
|---|---|---|
| `block_start` | – | 00, 04, 08, 12, 16, 20 h of day D+1 |
| `demand_mwh` (target) | ewz | sum of 16 × 15 min, kWh → MWh |
| `price_eur_mwh` (target) | Energy-Charts CH | mean of the hours in the block |
| `demand_lag_1d`, `demand_lag_7d`, `price_lag_1d`, `price_lag_7d` | ewz, Energy-Charts | same block 1 and 7 days earlier (the 1-day lag must be known by 11:00 of day D) |
| `temp`, `sunshine`, `radiation`, `wind` | MeteoSwiss / Open-Meteo | block mean |
| `solar_ch_mw` | Energy-Charts | block mean (lagged or forecast) |
| `ev_count_city`, `charging_kw_zh` | Stadt Zürich, BFE | interpolated to daily |
| `weekday`, `month`, `is_holiday`, `is_school_holiday` | `holidays`, school file | flags |
| `is_event`, `event_size`, `fcz_gc_home_game` | hand-made table, football-data | flags |
| `price_de`, `price_fr` | Energy-Charts | day D, same block |
| `gas_ttf`, `co2_eua`, `eur_chf` | LSEG / Yahoo / EEX / ECB | value from D−1 |
| `reservoir_pct` | BFE | latest week ÷ maximum |

---

## What we verified during the build (was "Not verified yet")

| Open question (19 Nov 2026) | Answer |
|---|---|
| Swiss day-ahead gate closure 11:00 or 12:00? | **11:00 CET/CEST** on D−1, results from ~11:10 (EPEX SPOT brochures 2020–2024, EEX glossary); no change found for 2019–2026. The EU-coupled auction (DE, FR, AT, IT) closes at 12:00. Details: `docs/auction_timing.md`. |
| ewz: do timestamps mark the start or the end of the interval (2019 starts at 00:15)? | **End of the 15-min interval**, in local time, in every year. Proof: the ewz Netzebenen file (UTC, documented as end labels) matches at shift 0 with correlation 0.999993 (0.9966 at ±15 min). The autumn DST duplicates are not in a consistent order (27 of 32 pairs would be wrong in file order) and are matched to Netzebenen. `reports/data_checks.md`. |
| MeteoSwiss: start or end of the hour? | **End** of the hour ("ReferenceTS 16:00 = 15:10 to 16:00"); shifted −1 h. Check: June radiation peaks symmetrically around solar noon (~11:26 UTC) after the shift. |
| Open-Meteo: which data for 2019–2023, and from when are there real forecasts? | ICON-seamless previous-runs data starts **2024-01-19** (ECMWF in Feb/Mar 2024). Earlier rows of the default model are not a real forecast archive and are not used. **JMA GSM** has real previous-runs forecasts back to 2018 (no radiation). Open-Meteo stamps are shifted −1 h; `_previous_dayN` was checked against the single-runs API. |
| Why do the Energy-Charts solar forecast and actual differ? | The scale is **not stable**: forecast/actual = 0.05–0.21 in 2019–2023, ≈ 1.0 in 2024, 0.6–0.7 in 2025–2026 (hourly correlation 0.89–0.98). It seems to cover a different, changing part of Swiss PV, and its publication time is not documented. It is stored as `unverified_ch_solar_fc` and **not used**; the models use the radiation forecast and lagged actual solar instead. |
| Exact dates of Street Parade and Züri Fäscht | Confirmed with sources (see Events above). |
| 2026 EEX CO₂ auction file | **Found** on the EEX website (`emission-spot-primary-market-auction-report-2026-data.xlsx`); CO₂ comes from one official source for the whole period. |
| Licence terms of the Yahoo prices | Personal/educational use only; marked as unofficial everywhere. |
| ENTSO-E Transparency (backup for load and price) | Not needed and not tested (needs an account and token); Energy-Charts and ewz covered everything. |
| Swissgrid timestamps | Not needed (Swissgrid data not used). |
| ewz publication lag | On 19 Nov 2026 at 09:05 the file held data up to the end of 17 Nov (~1.5 days). Our DSO is assumed to read its own meters up to the end of D−1 (sensitivity in `reports/model_notes_demand.md`). |

## Extra sources used in the build (not in the first check)

| Source | URL / endpoint | Used for |
|---|---|---|
| ewz Stromabgabe Netzebenen (UTC) | `https://data.stadt-zuerich.ch/dataset/ewz_stromabgabe_netzebenen_stadt_zuerich` | time-label proof, DST pairs, filling two missing 2021 days |
| Open-Meteo archive (ERA5) | `https://archive-api.open-meteo.com/v1/archive?...&models=era5` | cross-check of observed weather, never a model input |
| Open-Meteo previous runs, ICON and JMA, 9 European points | `https://previous-runs-api.open-meteo.com/v1/forecast` (`models=icon_seamless`, `jma_seamless`) | German wind/solar, French temperature, Alpine precipitation for the price model |
| Energy-Charts AT and IT-North prices | `https://api.energy-charts.info/price?bzn=AT` / `bzn=IT-North` | price features (day D) |
| OxCGRT COVID stringency index | `https://github.com/OxCGRT/covid-policy-dataset` (`OxCGRT_compact_national_v1.csv`) | demand feature for 2020–2022 |
| Energy-Charts German day-ahead forecasts | `https://api.energy-charts.info/public_power_forecast?country=de&...` | stored only (publication time unverified) |
