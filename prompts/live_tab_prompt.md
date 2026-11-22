# Build prompt – "Plan tomorrow (live)" tab

*Written 21 Nov 2026 for the branch `live-forecast-tab`. Paste everything below the line into a Claude Code session
opened in the repository root. The orchestrator splits the work into three parts (A, B, C) that touch different files.*

---

## 0. Goal

The web app today **replays** September and October 2026 from stored predictions. Add a tab that does the real
job: **on day D, plan delivery day D+1 from data that is known today**, then show the plan, the hourly bids and the
inputs it used. The user can correct or stress a few inputs ("what if it is 3 °C colder?", "tomorrow is a holiday")
and re-plan.

The tab must use **the same code paths as the backtest**:
- `src.features.build_features.build_features(tables, dates)` for the inputs
- the saved models `models/demand_best.joblib` and `models/price_best.joblib`
- `src.backtest.run_backtest.plan_day(..., settle=False)` for the battery plan and the bids

What the user sees must therefore match what was tested.

### Ground rules
- Work on the branch `live-forecast-tab`. Never commit to `main`. Push the branch only at the end.
- No invented data. If a source fails, keep the last stored value, mark it **stale** or **estimated**, and say so
  in the app.
- No future information: everything respects the cut-offs already encoded in `build_features` (forecast time
  10:00 Europe/Zurich on day D).
- Live downloads and caches go to `data/live/` (gitignored). Never overwrite `data/processed/`.
- Windows and macOS: build every path with `pathlib`; never hard-code `.venv/bin/python`.
- Plain English in the UI. Keep the existing pages unchanged.

---

## 1. Part A – Live data refresh (`src/live/refresh.py`)

**Function:** `refresh_tables(today: date | None = None, force: bool = False) -> tuple[dict[str, DataFrame], list[dict]]`
- Start from the stored tables (`build_features.load_tables()`), which run until early or mid November 2026.
- Fetch the recent window from each source: the last ~21 days up to the latest available, and for forecasts up to
  D+2. Append to the stored tables with **the same columns, units and time conventions**. Where rows overlap, the
  fresh rows win. Drop duplicates on the key (`timestamp_utc`, `date` or `measure_date`).
- Reuse the project's loader code for parsing and unit conversion. Patch module constants (raw folder, start and
  end dates) instead of copying logic. Respect the rate limits: Energy-Charts ≥ 7 s between calls, Open-Meteo with
  backoff.
- Cache:
  - raw responses in `data/live/raw/<today>/`
  - merged tables in `data/live/processed/<today>/<name>.parquet`
  - a second call on the same day reuses the cache unless `force=True`

**Sources (key → how to refresh):**

| key | refresh |
|---|---|
| `demand` | ewz yearly CSV of the current year (`load_ewz_demand`); 15 min → hourly as the loader does |
| `price` | Energy-Charts `bzn=CH` (`load_price_ch`); now 15-minute values, averaged to hourly by the loader |
| `neighbours` | Energy-Charts DE-LU, FR, AT, IT-North (`load_neighbour_prices`) |
| `power`, `ch_solar_fc` | Energy-Charts public_power and solar forecast CH (`load_swiss_power`); keep the `*_bad` flags logic |
| `de_forecasts` | Energy-Charts DE forecasts (`load_de_forecasts`) |
| `weather_obs` | MeteoSwiss SMA `*_h_recent.csv` (`load_meteoswiss`) |
| `weather_fc` | Open-Meteo previous-runs API, same models, variables and leads (`load_openmeteo_forecast`). **Merge the raw lead columns with the stored frame first, then recompute** `add_safe_columns` and `add_bias_correction` on the full frame (the bias fit needs the old rows) |
| `weather_europe` | Open-Meteo previous-runs for the European points (`load_openmeteo_europe`), same merge-then-recompute rule |
| `gas`, `co2`, `eurchf`, `reservoir` | Re-download the small files with their loaders (`load_gas`, `load_co2`, `load_fx`, `load_reservoirs`) |
| `calendar` | No download. The stored calendar runs to 2026-12-31. Warn if tomorrow is outside it |

**Status list:** one dict per source:
- `source`, `label` (plain English)
- `last_timestamp_utc` (latest non-null value)
- `rows_added`
- `ok` (bool)
- `message` (e.g. "ewz publishes ~1.5 days late: data up to 19 Nov 24:00")

A failing source must not stop the refresh: keep the stored table and set `ok = false`.

**CLI:** `python -m src.live.refresh [--force]` prints the status table.

**Tests** (`tests/test_live_refresh.py`, offline: monkeypatch the fetchers with small fixtures):
- merge keeps the schema
- fresh rows win on overlap
- a failing source keeps the stored table and returns `ok=False`

---

## 2. Part B – Live plan + API (`src/live/plan.py`, `api/server.py`)

**Function:** `live_plan(tables, delivery_date, battery: dict, soc_start_mwh: float | None, overrides: dict) -> dict`

1. **Fill known gaps** (copy the tables, never mutate the cache):
   - **Zurich demand:** the ewz file is ~1.5 days late, so hours missing up to the end of D−1 are filled with the
     same hour 7 days earlier. They are flagged `estimated`, and the number of estimated hours is reported.
   - **Daily drivers:** gas, CO₂, EUR/CHF and reservoir use the latest value (the `AsOf` lookup already does).
2. **Build the features** with `build_features(tables, [delivery_date])`, then apply the overrides:
   - `temp_shift_c` adds to every delivery-day temperature forecast column and recomputes the derived temperature
     columns with `build_features._temp_derived`
   - `is_holiday` (bool) sets the holiday flags
   - `gas_eur_mwh` replaces the gas feature(s)
   - `demand_scale_pct` scales the final demand forecast (manual correction for a known event)
3. **Predict:**
   - demand: `ForecastModel.predict` and `predict_quantiles`
   - price: the same, and the price band uses the model's `band_factor` like the backtest
   - naive forecasts: the `*_lag_7d_same_block` columns
4. **Plan without settlement** by calling `run_backtest.plan_day(d, "ml_battery", battery=…, soc_start_mwh=…,
   settle=False, allow_sell=…)` inside a context that temporarily replaces `run_backtest.load_data` and
   `run_backtest._forecast_index` with live versions built from the live tables, the feature rows and the
   predictions:
   - `blocks` for D+1
   - `hours` for D−60 … D+1, with actuals where known and NaN for D+1
   - `price_dev`, `daytype`
   - the forecast frame with the column names `load_forecasts` produces

   This keeps the tuned decision rules (hourly shape, charge limit) identical to the backtest. Guard the patch with
   a lock.
5. **Return a `LivePlan`** (§4): blocks, hours, bids, summary (expected cost, expected battery saving, EUR/CHF), the
   input panel, the recent days for context charts, the data status and the overrides used.
6. **Log:** each plan made without overrides is saved to `data/live/log/<delivery_date>.json`. Later, if actuals
   exist in the refreshed tables, the log endpoint adds them so the app can show a track record.

**Start charge level:** default `soc_start_frac × capacity`. The user can set it in the tab, because in reality it
comes from the battery's own meter.

**API endpoints (FastAPI, add to `api/server.py`):**
- `GET  /api/live/status` → `{fetched_at, delivery_date, sources: [...]}` (from the cache; no download)
- `POST /api/live/refresh` body `{force?: bool}` → same shape, after downloading (can take 1–3 minutes)
- `POST /api/live/plan` body `{battery, soc_start_mwh?, overrides?}` → `LivePlan` (refreshes first if there is no
  cache for today)
- `GET  /api/live/log` → list of `{delivery_date, made_at, blocks: [{demand_fc_mw, price_fc, demand_actual_mw?,
  price_actual?}], summary}`

Invalid input → HTTP 422 with a readable message, as the existing endpoints do.

**Tests** (`tests/test_live_plan.py`):
- `live_plan` on a stored date (e.g. 2026-10-15) with the stored tables cut at that date's forecast time gives the
  **same block forecasts and plan** as `reports/predictions_*.parquet` and `plan_day(settle=False)`, within 1e-6
- the overrides change the forecast in the expected direction
- the API returns 422 for a bad battery

---

## 3. Part C – Web tab (`web/src/routes/Live.tsx` + menu)

- **Menu:** add **"Plan live"** as the first item. Keep the other pages.
- **Data status bar:** one chip per source (green ok / amber estimated or stale / red missing), the last timestamp,
  and a **"Get today's data"** button that calls `POST /api/live/refresh`. Show a progress message, because the
  download takes 1–3 minutes.
- **Inputs panel** (pre-filled from `LivePlan.inputs`, editable):
  - temperature shift slider (−10 … +10 °C)
  - "Tomorrow is a holiday" checkbox
  - gas price (EUR/MWh)
  - demand correction (−20 … +20 %)
  - battery start level (MWh)

  Plus a read-only table of the most important inputs (yesterday's and last week's demand per block, today's Swiss
  prices per block, tomorrow's temperature and sunshine per block) with a status badge each. A **"Re-plan"** button
  calls `POST /api/live/plan`.
- **Result:** reuse the existing components and style of the Tomorrow page:
  - the headline sentence (`ui/sentence.ts`) and the six block cards (`ui/Blocks.tsx`)
  - demand and price charts with the forecast band, plus the last 7 days for context
  - the hourly bid table with **"Download bids (CSV)"**
  - expected cost and expected battery saving in CHF
- **Track record:** a small table from `GET /api/live/log`: past live forecasts vs actuals once known.
- **No planning service:** a clear message with the Windows and macOS commands to start it. The rest of the app
  keeps working.
- **Types:** add the TypeScript types (`LivePlan`, `LiveStatus`, `LiveLogEntry`) to `web/src/data/types.ts` and the
  calls to `web/src/data/api.ts`.
- **Checks:** `npx tsc --noEmit` and `npx vite build` must pass.

Also fix the start script so it works on Windows: `web/package.json` `api` script and `web/scripts/start.ts` pick
`.venv/Scripts/python.exe` on Windows and `.venv/bin/python` elsewhere. Add an npm-only path (`npm run dev` +
`npm run api`) to `web/README.md`.

---

## 4. Contract: `LivePlan` (JSON)

```ts
interface LivePlan {
  made_at_utc: string; delivery_date: string; issue_time_local: string;  // "2026-11-21 10:00"
  weekday: string; is_holiday: boolean; holiday_name: string | null; event_name: string | null;
  battery: BatterySettings; soc_start_mwh: number;
  blocks: { block: number; label: string; hours: number;
    demand_fc_mw: number; demand_q10_mw: number | null; demand_q90_mw: number | null; demand_naive_mw: number | null;
    price_fc: number; price_q10: number | null; price_q90: number | null; price_naive: number | null;
    buy_mwh: number; charge_mwh: number; discharge_mwh: number; sell_mwh: number; soc_end_mwh: number;
    option: string; charge_limit_eur_mwh: number | null }[];
  hours: { utc: string; hour: string; block: number; demand_fc_mw: number; price_fc: number | null;
    demand_bid_mwh: number; charge_bid_mwh: number; charge_limit_eur_mwh: number | null;
    planned_discharge_mwh: number; soc_mwh: number | null }[];
  bids: { hour: string; utc: string; block: number; bid_type: string; volume_mwh: number;
    limit_price_eur_mwh: number | null }[];
  summary: { energy_to_buy_mwh: number; charged_mwh: number; discharged_mwh: number;
    expected_cost_chf: number; expected_battery_saving_chf: number; eurchf: number };
  inputs: { key: string; label: string; unit: string; values: (number | null)[];  // per block, or 1 value
    status: "ok" | "estimated" | "stale" | "missing"; source: string; as_of: string | null }[];
  recent: { date: string; demand_mw: (number | null)[]; price: (number | null)[] }[];  // last 7 days, 6 blocks
  sources: { source: string; label: string; last_timestamp_utc: string | null; ok: boolean; message: string }[];
  overrides: { temp_shift_c: number; is_holiday: boolean | null; gas_eur_mwh: number | null; demand_scale_pct: number };
  warnings: string[];
}
```

---

## 5. Done when

1. `python -m src.live.refresh` downloads today's data and prints a status table.
2. `uvicorn api.server:app --port 8000` plus `npm run dev` lets a user open **Plan live**, click **Get today's data**,
   and see tomorrow's plan, bids, inputs and data status within a few minutes.
3. Changing the temperature shift and pressing **Re-plan** changes the forecast and the plan.
4. The existing test suite still passes, and the new tests pass.
5. The branch `live-forecast-tab` is pushed with a README section **"Plan live"** explaining how to run it and its
   limits:
   - models trained until September 2026
   - ewz data arrives late, so the latest demand is estimated
   - observed values are replaced by forecasts only where the backtest did the same
