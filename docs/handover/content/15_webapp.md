# 15 The web app

<div class="inshort" markdown="1">

A web app built with Bun, React and TanStack (Router, Query, Table) shows the plan for any day of September and
October 2026, the month's results, a live "try a battery" page and the method. It reads JSON files written by
`src/export/export_web.py`, whose shapes are fixed in `web/src/data/types.ts`. Only the battery page needs Python:
it calls a small FastAPI service, `api/server.py`.

</div>

## The four pages

| Page (route) | What it shows | Needs Python? |
|---|---|---|
| **Tomorrow** (`#/`) | the decision of one day in one sentence, the money, and "the day at a glance": decision per block, price forecast with its likely range, battery use, actual values; folded: the hourly bids and the day's bill | no |
| **Results** (`#/results`) | October's saving with the caveat box, saving day by day, forecast quality, drivers, every strategy, what the result depends on, every model, patterns in the data, the months before October | no |
| **Try a battery** (`#/battery`) | sliders for power, capacity, efficiency (more settings folded); re-plans a day and runs October with that battery | **yes** (`POST /api/plan`, `POST /api/month`) |
| **How it works** (`#/how`) | the method, the time rules, the data sources and the limitations in plain words | no |

{{img:docs/handover/img/app_tomorrow.png|Tomorrow page for 1 October 2026: one sentence with the decision, the realised cost and savings, and the day on one time axis (blue = stored, amber = used, plum = price).|88%}}

{{img:tmp:app_results_open_1.png|Results page with every section opened (part 1): saving day by day, forecast quality, what the forecasts rely on.|80%}}

{{img:tmp:app_results_open_2.png|Results page, part 2: every strategy compared and what the result depends on (penalty, battery size, price error).|80%}}

{{img:tmp:app_results_open_3.png|Results page, part 3: every model tried, patterns in the data and the months before October.|80%}}

{{img:docs/handover/img/app_battery.png|Try a battery: move a slider and the day is planned again; "Run October" settles all 31 days with that battery.|85%}}

{{img:docs/handover/img/app_how.png|How it works: method, time rules, sources and limitations.|85%}}

## How it is built

**Export → JSON contract → React.**

1. `python -m src.export.export_web` reads the backtest, the predictions and the result files and writes JSON into
   `web/public/data/`. Every number is read or computed from repo files at export time. For every day of September and
   October it rebuilds the product's day plan with the **same function** the API uses (`build_day_plan`) and carries the
   battery level from day to day exactly as in the backtest; `tests/test_export_web.py` checks the exported days against
   `reports/backtest.csv`.
2. `web/src/data/types.ts` is the **data contract**: every JSON shape. `tests/test_export_web.py` checks the exported
   JSON against pydantic models that **mirror these types by hand** (extra keys are an error, required keys must be
   present). The browser does not check anything: it casts the JSON to the TypeScript types. So the two copies can
   drift apart – whenever a shape changes, update `types.ts` **and** the pydantic models in the test together.
3. The React app loads the files with TanStack Query (`web/src/data/api.ts`), routes with TanStack Router (hash
   routes `#/…`, so any static host works without rewrites) and draws charts as plain SVG with d3 scales.

{{t:web_files|The exported files on the build machine.}}

{{t:web_types|The shapes in `web/src/data/types.ts` (read from the file).}}

{{t:web_routes|Front-end source files.}}

## The planning API

`api/server.py` (FastAPI, port 8000) has three endpoints: `GET /api/health`, `POST /api/plan` (a `DayPlan` for one
date and battery) and `POST /api/month` (October with that battery: baseline, ML without battery, the product and the
hourly ceiling, inventory-adjusted like the backtest; results cached per battery setting). Invalid input returns HTTP
422 with a readable message. Inputs are validated by pydantic (e.g. power 1–200 MW, capacity 1–400 MWh, minimum charge
level below maximum).

**Start level of a custom battery.** The two endpoints differ:

- `POST /api/plan` (one day) starts at the **same share of capacity** that the default battery had on that morning in
  the stored backtest, clipped into the new battery's range (`start_level` in `api/server.py`). Keeping the MWh instead
  would make a bigger battery start nearly empty and look worse than it is. The day plans back to `soc_start_frac`.
- `POST /api/month` (all of October) starts on the first test day ({{c:periods.test_start}}) at the battery's own `soc_start_frac` and then carries **its
  own** settled end level from day to day, like the backtest (`month_result` in `src/export/export_web.py`).

The API caches its inputs and month results in memory: restart it after re-running the pipeline.

## Design choices

- **One colour per concept, everywhere:** blue {{n:col_stored}} = energy stored, amber {{n:col_used}} = energy used from the battery,
  plum {{n:col_price}} = price, green = demand forecast and money saved, a thin dark line = what really happened. The same colours
  are used in the diagrams of this report.
- **One sentence first.** Each page opens with the decision or result in plain words, then the evidence; details are
  folded away.
- **Caveats next to numbers.** The October saving is shown with the penalty assumption and the interval beside it.
- **No internet needed** for the three read-only pages; the font (Archivo) is bundled.

## Running and deploying

```bash
.venv/bin/python -m src.export.export_web   # write web/public/data/
cd web && bun install
bun run start      # planning service (port 8000) + web app on http://localhost:5173
bun run build      # type-check + static site in web/dist/
```

`web/dist/` can be put on any static host (for example GitHub Pages); everything except the battery sliders works
there. Before any public deployment read "Before you publish" in chapter 16.
