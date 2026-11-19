# Data sources – what exists and how it looks

**Focus:** Switzerland, with the **city of Zurich (ewz)** as our DSO. The price is Swiss (one price for all of Switzerland). Demand, weather, EVs, holidays and events are for Zurich.

*Checked on 19 Nov 2026 by downloading small samples from every source. Everything below is free unless noted. "Not verified" items are listed at the end.*

## Summary

| Input | Recommended source | Step | Period | Access |
|---|---|---|---|---|
| **Demand (target)** | ewz Bruttolastgang Stadt Zürich | 15 min | 2019 → 18 Nov 2026 | Free, CC0 |
| **Price (target)** | Energy-Charts API, `bzn=CH` | 1 h (15 min from 4 Nov 2026) | 2019 → tomorrow | Free, CC BY 4.0 |
| Weather (observed) | MeteoSwiss station Zürich-Fluntern (SMA) | 1 h | 2010 → yesterday | Free |
| Weather (forecast) | Open-Meteo "previous runs" API | 1 h | real forecasts from ~2024 | Free, CC BY 4.0 |
| Rooftop solar | Energy-Charts Swiss solar output | 1 h | 2019 → now | Free |
| EVs | Stadt Zürich car stock by fuel + BFE charging stations per canton | yearly / monthly | 2002–2025 / 2020-11 → 2026-10 | Free |
| Holidays | Python `holidays` (ZH) + Stadt Zürich school holidays file | daily | 2018 → 2030 | Free |
| Events | Hand-made table + football-data.co.uk results | daily | 2019 → 2026 | Free |
| Neighbour prices | Energy-Charts `bzn=DE-LU`, `FR` | 15 min | 2019 → now | Free |
| Gas (TTF) | LSEG/Bloomberg at HSG (fallback: Yahoo `TTF=F`) | daily | 2019 → Oct 2026 | HSG / unofficial |
| CO₂ (EUA) | LSEG/Bloomberg at HSG (fallback: EEX auction results) | daily | 2012 → 2025 (2026 file not found) | HSG / free |
| Reservoir level | BFE weekly fill of Swiss reservoirs | weekly | 2000 → 16 Nov 2026 | Free |
| EUR/CHF | ECB data API | daily | long history | Free |

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
  - Street Parade: 2024-08-10, 2026-08-08 are confirmed. 2020 and 2021 were cancelled. Other years still need checking.
  - Züri Fäscht: 2019 and 2023 (early July). The dates need checking.
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

**Timing rule:** use only what is known **on day D before 11:00**. For daily drivers (gas, CO₂, FX) that means the value from day D−1. The reservoir value is measured on Sunday and published a few days later.

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

## Not verified yet
- ENTSO-E Transparency (the backup for load and price) needs a free account and an API token. Not tested.
- Whether timestamps mark the start or the end of each interval for MeteoSwiss, ewz 2019 and Swissgrid.
- What source Open-Meteo's default model uses for 2019–2023.
- Why the Energy-Charts solar forecast and actual output differ in size.
- Exact dates of Street Parade (2019, 2022, 2023, 2025) and Züri Fäscht.
- The 2026 EEX CO₂ auction file. Licence terms of the Yahoo prices.
