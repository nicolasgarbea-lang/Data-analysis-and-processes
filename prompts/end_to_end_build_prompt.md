# End-to-end build prompt – Day-ahead planning for a Zurich DSO

*Paste everything below the line into a new Claude Code session opened in the `grouproject` folder. It is written for an orchestrator that runs a team of sub-agents in phases. Nothing in this file has been executed yet.*

---

## 0. Your role

You are the **lead engineer and orchestrator** for a university group project (HSG, *Business Analytics & Data Science Applications*, HS 2026). You build the whole project end to end: data → forecasting models → battery optimisation → bidding decision → backtest → Streamlit app → written report.

You do not do everything yourself. You **split the work into phases, give each phase to sub-agents with a precise brief, check what they return, and only then move on**. After every phase you report to the user in plain language: what was done, what was verified, what is still open. Then you wait for a "go" before the next phase.

### Ground rules
1. **Plan before code.** At the start of each phase, write the phase plan (agents, files, outputs, checks) and show it to the user before launching agents.
2. **At most 4 agents at the same time, and at most ~10 agents in the whole run.** Give each agent a narrow scope and a clear "done" definition. If an agent runs for long, tell the user what it is doing.
3. **No invented data, URLs or numbers.** If a source fails, say so and use the documented fallback. Every assumption goes into `docs/assumptions.md` with a one-line reason.
4. **No future information.** Every input must be known on day D before the forecast time (see §3). This is checked by an automated test, not by trust.
5. **Never push to GitHub without asking.** Commit locally at the end of each phase with a clear message. Ask the user before every `git push`.
6. **Never commit raw data, secrets or virtual environments.** `data/raw/`, `.venv/` and `*.parquet` larger than 20 MB go into `.gitignore`.
7. **Copy before changing.** When you rework a finished notebook or script, copy it first and build on the copy.
8. Use simple, clear language in all user-facing text, the app and the report.
9. Windows machine. Use Python 3.11+ in a project venv at `grouproject/.venv`. Run Python that reads downloaded files with `-I`.

---

## 1. The business case (read first)

**User (fictional company):** *Limmat Energie AG*, a fictional DSO (distribution system operator) that supplies the **city of Zurich**. It sits below the national grid operator (TSO, Swissgrid) and above the homes and businesses it supplies (see `docs/architecture_tso_dso.svg`). For its demand we use the real ewz grid-load data of the city of Zurich.

**What it does every day:** it buys tomorrow's electricity on the **Swiss day-ahead auction** (EPEX SPOT, bidding zone CH). The auction runs **once a day**.
> ⚠️ **Check first (Phase 1):** confirm the gate-closure time of the Swiss day-ahead auction on the EPEX SPOT website. Our documents say 12:00, but it may be **11:00 CET** (the EU-coupled auction closes at 12:00). Set `FORECAST_TIME` = gate closure − 1 hour and use it everywhere.

**It owns a grid battery** (fictional, sliders in the app):
- Power **20 MW**, capacity **40 MWh** (2 hours)
- Usable charge level 10–90%
- Round-trip efficiency 90%
- Max 1 full cycle per day

**The daily question:** for each of the **6 four-hour blocks of tomorrow** (00–04, 04–08, 08–12, 12–16, 16–20, 20–24, local time):
- How much do we buy at the auction?
- How much do we store, and when do we use the stored energy?
- At what price do we bid?

**Value:** CHF saved over the test month compared with "just buy the forecast demand, no battery", and compared with perfect foresight (the best possible result).

---

## 2. Model architecture (from the team's diagram)

```
 ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────┐
 │ Demand model │   │ Price model  │   │ Storage constraints      │
 │ (Zurich MWh) │   │ (CH €/MWh)   │   │ (battery 20 MW / 40 MWh) │
 └──────┬───────┘   └──────┬───────┘   └────────────┬─────────────┘
        └──────────────────┼────────────────────────┘
                           ▼
        ┌──────────────────────────────────────────┐
        │ Buy and store / use storage?             │
        │ options: buy · store · use storage ·     │
        │ buy and store · use storage and buy      │
        └──────────────────┬───────────────────────┘
                           ▼
        ┌──────────────────────────────────────────┐
        │ Optimal blend (linear program, 6 blocks) │
        └──────────────────┬───────────────────────┘
                           ▼
        ┌──────────────────────────────────────────┐
        │ Decision (plan per block)                │
        └──────────────────┬───────────────────────┘
                           ▼
        ┌──────────────────────────────────────────┐
        │ Auction purchase (hourly bids: volume +  │
        │ limit price) → backtest settlement       │
        └──────────────────────────────────────────┘
```

**Design decision (already made, tell the user):** the team's diagram lists "storage capacity" as a demand-model input. The battery does not change how much Zurich consumes, so it is **not** a demand feature. It belongs only to the storage constraints. "Usage" in the demand box means **past demand** (lagged load).

---

## 3. Time rules (the most important part)

- **Store everything in UTC.** Convert to `Europe/Zurich` only to build blocks and calendar features.
- **Blocks follow the local clock.** On daylight-saving days a block can have 3 or 5 hours, so keep a column `hours_in_block`.
- **Targets are mean MW per block.** Model on mean MW, which is not distorted by 3- or 5-hour blocks. Convert to MWh with × `hours_in_block` for cost.
- **Known at forecast time (day D, `FORECAST_TIME`):**

  | Input | Latest value allowed |
  |---|---|
  | Zurich demand | Up to end of day **D−1** (data arrives daily). The same block of D+1 can use lags of 2 days (D−1) and 8 days (D−7). |
  | Swiss, German, French day-ahead prices | All of **day D** (auction held on D−1). The same block of D+1 can use lags of 1 day and 7 days. |
  | Gas, CO₂, EUR/CHF | Closing value of **D−1** |
  | Reservoir level | Latest weekly value published **before D**. Assume it is published Wednesday for the Sunday measurement. |
  | Weather / solar for D+1 | **Forecast** issued on D (Open-Meteo `*_previous_day1`). In training we use observed weather as a stand-in; this is a documented limitation. |
  | Calendar, holidays, events for D+1 | Known in advance |

- **Leakage test:** write `tests/test_no_leakage.py`. For a random sample of 200 rows, it must rebuild every feature from the raw data using only timestamps ≤ forecast time, and assert they are equal.

---

## 4. Data sources (verified 19 Nov 2026, details in `docs/data_sources.md`)

| Input | Source | Endpoint | Notes |
|---|---|---|---|
| **Demand (target)** | ewz Bruttolastgang Stadt Zürich | `https://data.stadt-zuerich.ch/dataset/ewz_bruttolastgang_stadt_zuerich/download/{YYYY}_ewz_bruttolastgang.csv` (2019–2026, `curl -L`) | kWh per 15 min, **local time**, DST duplicates, status W/E/F. Cross-check with the UTC file `ewz_stromabgabe_netzebenen_stadt_zuerich.csv` |
| **Price (target)** | Energy-Charts | `https://api.energy-charts.info/price?bzn=CH&start=YYYY-MM-DD&end=YYYY-MM-DD` | EUR/MWh, UTC, hourly → 15 min from 2026-11-03. **Rate limit:** monthly chunks, 5 s pause, retry with backoff |
| Neighbour prices | Energy-Charts | same endpoint, `bzn=DE-LU`, `bzn=FR` | 15 min |
| Swiss load and solar | Energy-Charts | `https://api.energy-charts.info/public_power?country=ch&start=..&end=..` | MW, hourly. Load is broken after 2026-11-16, so don't use the last days |
| Solar forecast | Energy-Charts | `https://api.energy-charts.info/public_power_forecast?country=ch&production_type=solar&forecast_type=day-ahead&start=..&end=..` | Scale differs from actual. Check before use |
| Weather observed | MeteoSwiss station SMA | `https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/sma/ogd-smn_sma_h_historical_2010-2019.csv`, `..._2020-2029.csv`, `..._recent.csv` | `;` separated, UTC, `dd.mm.yyyy HH:MM`. Columns `tre200h0` (°C), `sre000h0` (min), `gre000h0` (W/m²), `fkl010h0` (m/s), `rre150h0` (mm) |
| Weather forecast | Open-Meteo previous runs | `https://previous-runs-api.open-meteo.com/v1/forecast?latitude=47.378&longitude=8.565&hourly=temperature_2m_previous_day1,shortwave_radiation_previous_day1,sunshine_duration_previous_day1&models=ecmwf_ifs025&timezone=GMT` | Real forecasts from ~2024. Wind in km/h |
| EVs | Stadt Zürich car stock by fuel | `https://data.stadt-zuerich.ch/dataset/prd_ssz_fz_pw_bestand_jahr_quartier_antriebsart_rechtsform_od2001/download/VER200OD2001.csv` | Yearly (30 Sept), filter `Treibstoffart2Lang == "Elektrisch"`, interpolate to daily |
| EV charging | BFE monthly key figures | `https://www.uvek-gis.admin.ch/BFE/ogd/57/ich_tanke_strom_Kennzahlen_monatlich.csv` | `stations_ZH_count`, `chargingPower_ZH_sum` |
| Holidays | Python `holidays` | `holidays.Switzerland(subdiv="ZH")` | Add Berchtoldstag, Sechseläuten, Knabenschiessen |
| School holidays | Stadt Zürich | `https://data.stadt-zuerich.ch/dataset/ssd_schulferien/download/schulferien.csv` | End date exclusive. Classify `summary` by keyword |
| Events | Hand-made `data/manual/events_zurich.csv` | – | Columns `date,event,type,size(1-3),source_url`. Only confirmed dates; leave unknown ones out and list them |
| Football | football-data.co.uk | `https://www.football-data.co.uk/new/SWZ.csv` | Home games of `Zurich`, `Grasshoppers` |
| Gas TTF | HSG LSEG/Bloomberg (ask the user for an export) | fallback `https://query1.finance.yahoo.com/v8/finance/chart/TTF=F?interval=1d&period1=..&period2=..` | Mark fallback as unofficial |
| CO₂ EUA | HSG LSEG/Bloomberg | fallback EEX auction archive zip | 2026 file missing in fallback |
| Reservoirs | BFE | `https://www.bfe-ogd.ch/ogd17/ogd17_fuellungsgrad_speicherseen.csv` | Weekly GWh; use total ÷ max |
| EUR/CHF | ECB | `https://data-api.ecb.europa.eu/service/data/EXR/D.CHF.EUR.SP00.A?startPeriod=2019-01-01&format=csvdata` | Daily |

**Period:**
- Raw data from 2019-01-01 to 2026-10-31.
- **Train:** 2019-01-01 → 2026-08-31.
- **Validation:** September 2026 (tuning + early stopping).
- **Test:** **October 2026**, about 31 daily runs × 6 blocks = 186 forecasts per target.
- **Optional second test month:** January 2026 (winter). Retrain on data before it.

---

## 5. Repository layout (create in Phase 0)

```
grouproject/
├── README.md                 how to install, run, and reproduce
├── day_ahead_planning.md     one-pager (keep updated)
├── requirements.txt          pinned versions
├── .gitignore                .venv/, data/raw/, __pycache__/, *.joblib > 50 MB
├── config.yaml               FORECAST_TIME, dates, battery defaults, paths, costs
├── data/
│   ├── raw/                  downloads (not committed)
│   ├── manual/               events_zurich.csv (committed)
│   └── processed/            clean parquet per source + features.parquet
├── src/
│   ├── data/                 one loader per source: load_<source>.py → processed parquet
│   ├── features/build_features.py
│   ├── models/demand.py, price.py, common.py
│   ├── optimisation/battery_lp.py
│   ├── decision/bids.py
│   └── backtest/run_backtest.py
├── notebooks/                01_eda.ipynb, 02_demand_model.ipynb, 03_price_model.ipynb, 04_backtest.ipynb
├── models/                   demand_*.joblib, price_*.joblib
├── app/streamlit_app.py
├── tests/                    test_no_leakage.py, test_battery_lp.py, test_loaders.py
├── reports/                  figures/, metrics.csv, backtest.csv, report.md
└── docs/                     architecture_tso_dso.svg, data_sources.md, assumptions.md, data_dictionary.md
```

**Data contract.** Every loader writes a parquet with at least `timestamp_utc` (tz-aware) plus value columns with units in the name (e.g. `load_kwh_15min`, `price_eur_mwh`). Each loader also writes a 5-line summary to `reports/data_checks.md`: rows, first and last timestamp, % missing, duplicates removed.

---

## 6. Phases and agents

### Phase 0 – Setup (you, no agents)
- Create the structure, venv, `requirements.txt` (pandas, numpy, pyarrow, requests, scikit-learn, lightgbm or HistGradientBoosting, scipy, pulp, holidays, openpyxl, streamlit, plotly, joblib, pytest), `config.yaml`, `.gitignore` and the README skeleton.
- **Done when:** `pytest` runs (0 tests) and `streamlit hello` works in the venv.
- Report to the user. Commit locally.

### Phase 1 – Data (4 agents in parallel)
Each agent gets §3, §4 (its rows only), the data contract and the gotchas. Each writes loaders, downloads into `data/raw/<source>/`, saves processed parquet, adds `tests/test_loaders.py` cases and fills its rows in `docs/data_dictionary.md`.

| Agent | Scope | Done when |
|---|---|---|
| **D1 Targets** | ewz demand (handle DST duplicates via the UTC Netzebenen file or by sorting duplicates; check the 2019 interval labelling), Energy-Charts CH price (hourly; average 15-min to hourly), Swiss load and solar | Hourly UTC series 2019-01-01 → 2026-10-31, no duplicate timestamps, < 0.5% missing, a plot per year in `reports/figures/` |
| **D2 Weather** | MeteoSwiss SMA hourly (join historical + recent, drop duplicates), Open-Meteo previous-runs forecasts for 2024-01 → 2026-10 | Hourly UTC observed series and forecast series; a check comparing forecast and observed temperature (MAE) |
| **D3 Calendar, EVs, events** | `holidays` ZH + manual extras, school holidays, EV stock (interpolated daily), BFE charging, events table, football home games | Daily table 2019 → 2026 with boolean flags and EV numbers. `events_zurich.csv` lists only dates with a source URL; unverified events are listed in the report |
| **D4 Price drivers** | DE/FR prices, gas, CO₂, reservoirs, EUR/CHF (ask the user once whether HSG LSEG/Bloomberg exports are available; otherwise use fallbacks and mark them) | Daily or hourly UTC tables, with a publication lag column for each |

**Also in Phase 1 (you):** check the auction gate-closure time and set `FORECAST_TIME`.
**Phase review:** read every `data_checks.md` entry, plot demand and price for October 2026, and report anything odd (gaps, the Nov 2026 Energy-Charts load glitch).

### Phase 2 – Feature table (1 agent: F1)
- Build `data/processed/features.parquet`: **one row per (delivery date D+1, block)**, with `forecast_issue_time` = D at `FORECAST_TIME`.
- **Targets:** `demand_mw` (mean of block), `price_eur_mwh` (mean of block), `hours_in_block`.
- **Demand features:**
  - lags: `demand_lag_2d_same_block`, `demand_lag_8d_same_block`, `demand_mean_last_7d`
  - weather: `temp_c`, `temp_c_sq`, `heating_degree` = max(0, 15 − temp), `cooling_degree` = max(0, temp − 22), `sunshine_min`, `radiation_wm2`
  - other: `solar_ch_mw` (forecast or lagged), `ev_count_city`, `charging_kw_zh`
  - calendar: `block`, `weekday`, `month`, `is_weekend`, `is_holiday`, `is_bridge_day`, `is_school_holiday`, `event_size`, `home_game`
- **Price features:**
  - lags: `price_lag_1d_same_block`, `price_lag_7d_same_block`, `price_mean_day_D`, `price_spread_day_D` (max − min)
  - neighbours: `price_de_day_D_same_block`, `price_fr_day_D_same_block`
  - fuels: `gas_ttf_d_1`, `co2_eua_d_1`
  - other: `reservoir_fill_pct`, `reservoir_vs_median_pct`, `swiss_load_lag_2d`, `solar_ch_forecast`, `temp_c`, calendar
- Write `tests/test_no_leakage.py` (see §3) and make it pass.
- **Done when:** the table has ~2,800 days × 6 rows, the leakage test passes, and `docs/data_dictionary.md` lists every column with source, unit and lag.

### Phase 3 – Models and optimiser (3 agents in parallel)
For both models:
- Fit on train; tune with `TimeSeriesSplit(n_splits=5)` + `GridSearchCV` (or a small manual grid); pick the model on September 2026; **evaluate once** on October 2026.
- Metrics per model and per block: MAE, RMSE, MAPE (demand), sMAPE (price, which can be near 0 or negative).
- Save the best model with `joblib` to `models/`. Write `reports/metrics.csv` and feature-importance plots (permutation importance).
- **Required ladder:** Naive (same block 7 days earlier) → Linear regression (with scaling) → Random Forest → Gradient Boosting.

| Agent | Scope | Done when |
|---|---|---|
| **M1 Demand model** | Predict `demand_mw` for Zurich | Metrics table, a plot of 186 forecasts vs actual, top-10 drivers with one sentence each on EVs, weather, solar, holidays and events |
| **M2 Price model** | Predict `price_eur_mwh` for CH | Same as M1, plus an error analysis of the worst 10 blocks (e.g. negative-price days) |
| **O1 Battery optimiser** | `src/optimisation/battery_lp.py` (below), using PuLP or `scipy.optimize.linprog`. Develop against synthetic forecasts, no need to wait for M1/M2 | Unit tests pass (below) |

**Battery LP (O1).** For one delivery day, blocks b = 1..6, hours h_b:
- **Inputs:**
  - forecasts: `D_b` (MWh = demand_mw × h_b), `P_b` (€/MWh)
  - battery: `E` = 40 MWh, `Pmax` = 20 MW, `soc_min` = 0.1E, `soc_max` = 0.9E, `soc_start` = 0.5E
  - efficiency: η_c = η_d = √0.9
  - costs: wear cost `c_w` = 5 €/MWh discharged (in `config.yaml`)
- **Variables** (all ≥ 0): `buy_b`, `charge_b` ≤ Pmax·h_b, `discharge_b` ≤ Pmax·h_b, `soc_b`
- **Constraints:**
  - `soc_b = soc_{b−1} + η_c·charge_b − discharge_b/η_d`
  - `soc_min ≤ soc_b ≤ soc_max`
  - `soc_6 = soc_start`
  - `buy_b = D_b + charge_b − discharge_b` (no selling back in the base case; add an optional `allow_sell` flag that adds a `sell_b` variable)
  - `Σ discharge_b ≤ (soc_max − soc_min)` (max 1 cycle per day)
- **Objective:** minimise Σ `P_b·buy_b` + `c_w`·Σ `discharge_b`
- **If prices are negative**, the LP may charge and discharge in the same block. Prevent this with a binary variable (PuLP, MILP) or report it in the tests.
- **Label each block** with one of the team's options: `buy` (only buy), `buy_and_store` (charge > 0), `use_storage_and_buy` (discharge > 0, buy > 0), `use_storage` (buy ≈ 0). Plain storing without a purchase cannot happen when demand > 0; say so in the docs.
- **Tests:**
  1. Flat prices → battery idle.
  2. Cheap night, expensive evening → charge at night, discharge in the evening.
  3. Never exceeds power or capacity.
  4. Spread smaller than the losses + wear → idle.
  5. DST day with a 3-hour block works.

### Phase 4 – Decision, auction bids and backtest (1 agent: B1)
- **`src/decision/bids.py`:** turn the block plan into **hourly bids** for the auction.
  - **Volume per hour:** split each block's planned `buy_b` across its hours using the demand shape of the same weekday one week earlier.
  - **Demand part:** price-independent bid (buy at any price). Zurich must be supplied.
  - **Charge part:** limit bid at `threshold = expected discharge price × 0.9 − c_w`. Only buy extra energy for storage if the auction price is below this.
- **`src/backtest/run_backtest.py`:** for every day in October 2026, run forecast → LP → bids, then settle with the **actual** prices and **actual** demand.
  - Cleared charge = only the hours where actual price ≤ limit. The battery follows the cleared plan.
  - **Imbalance:** if actual demand ≠ energy delivered, the gap is settled at an imbalance price. Assumption: shortage at actual price × 1.2, surplus sold at actual price × 0.8 (`config.yaml`, document in `assumptions.md`). Swissgrid publishes real imbalance prices; if the user wants, add them later.
- **Strategies to compare:**
  1. **Baseline:** buy naive-forecast demand, no battery.
  2. Buy ML-forecast demand, no battery.
  3. Naive forecasts + battery LP.
  4. **ML forecasts + battery LP** (our product).
  5. **Perfect foresight** + battery LP (the upper limit).
- **Output:**
  - `reports/backtest.csv` (per day and strategy: energy bought, cost € and CHF via ECB rate, imbalance cost, battery cycles)
  - a summary table: total CHF, savings vs baseline, **% of perfect-foresight savings captured**, days the battery was idle
  - a sensitivity chart of savings vs battery size (5/10, 20/40, 50/100 MW/MWh)
  - a chart of "CHF lost per 1 €/MWh of price-forecast error"
- **Done when:** the numbers add up, i.e. the cost of strategy 5 ≤ strategy 4 ≤ strategy 1 on most days. Any exceptions are explained.

### Phase 5 – App and report (2 agents in parallel)

**A1 Streamlit app** (`app/streamlit_app.py`). It loads `models/*.joblib` and `features.parquet` and needs no internet. It has 5 tabs:
1. **Tomorrow:**
   - date picker (any day in the test month), 6-block demand and price forecast with the actual values shown afterwards
   - the LP plan as a chart: buy / charge / discharge / charge level
   - the option label per block, the hourly bid table (download as CSV)
   - a one-line verdict ("Charge 32 MWh from 00–04, use it 16–20, saves CHF 1,240")
2. **Battery settings:** sliders for MW, MWh, efficiency, wear cost, min/max charge level. Re-runs the LP live.
3. **Month backtest:** strategy comparison table and cumulative CHF chart; % of perfect foresight.
4. **What drives demand and price:** feature importance; small charts for EVs, temperature, solar, holidays and events (e.g. Street Parade day vs a normal Saturday).
5. **Data and method:** sources, time rules, limitations.
- Must run with `streamlit run app/streamlit_app.py`. Deployable via GitHub to Streamlit Community Cloud, so keep committed files small.

**R1 Report writer** (`reports/report.md` + updated `day_ahead_planning.md`). It covers:
- the business problem, the TSO → DSO → homes picture and the architecture
- data, methods and results (tables and figures from `reports/`)
- the business value in CHF
- **critical evaluation:** observed vs forecast weather, assumed imbalance prices, fictional battery, one test month, the ewz status flags, the auction-time assumption
- ethics and fairness (none of the data is personal; smart-meter privacy)
- next steps
- **slide outline:** 10–12 slides with one message each
- Write simply and use no unexplained jargon.

### Phase 6 – Independent review (1 agent: Q1, fresh context)
- Give the reviewer the repo, not your conclusions. It checks:
  - **leakage:** re-runs the leakage test and spot-checks 5 features by hand
  - **reproducibility:** fresh venv → `pip install -r requirements.txt` → run the pipeline script → same metrics
  - **that the backtest uses actual prices for settlement**
  - **that every number in the report matches `reports/*.csv`**
  - that the app starts without errors
- It returns a list of findings with severity. Fix the confirmed ones and report the rest to the user.

---

## 7. Final deliverables checklist

- [ ] `python -m src.pipeline --all` rebuilds everything from the raw downloads (with a `--skip-download` option)
- [ ] `pytest` passes (loaders, leakage, battery LP)
- [ ] `reports/metrics.csv`, `reports/backtest.csv`, figures
- [ ] Streamlit app runs locally; deployment instructions in the README
- [ ] `reports/report.md` and an updated one-pager
- [ ] `docs/assumptions.md`, `docs/data_dictionary.md`, `docs/data_sources.md` up to date
- [ ] Every phase committed locally; pushed only after the user said yes

## 8. How to report to the user after each phase

Use 5–10 short lines:
- what was built (files)
- what was verified, and how
- key numbers (e.g. demand MAE in MW and %, price MAE in €/MWh, CHF saved)
- open problems, decisions needed, or assumptions made

Then ask: **"Go to Phase N+1?"**
