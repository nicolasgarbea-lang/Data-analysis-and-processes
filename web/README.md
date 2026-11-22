# Web app

The app that shows the day-ahead plan: what to buy tomorrow, what the battery does, what a month of it saved, and
what drives the forecasts. Built with [Bun](https://bun.sh), React and TanStack (Router, Query, Table). Charts are
plain SVG with d3 scales.

## Run it

From the project folder, once:

```bash
.venv/bin/python -m src.export.export_web   # writes the data files to web/public/data/
cd web && bun install
```

Then:

```bash
bun run start    # planning service (port 8000) + web app, open http://localhost:5173
```

or separately: `bun run api` (the Python service) and `bun run dev` (the web app).

### Without Bun (npm only, Windows, macOS, Linux)

Once, in `web/`: `npm install`. Then two terminals, both in `web/`:

```bash
npm run api    # the planning service on port 8000
npm run dev    # the web app, open http://localhost:5173
```

`npm run api` picks `.venv\Scripts\python.exe` on Windows and `.venv/bin/python` elsewhere
(`scripts/api.mjs`). `npm start` runs both in one terminal. To start the service by hand from the project folder:

```bash
.venv\Scripts\python -m uvicorn api.server:app --port 8000   # Windows
.venv/bin/python -m uvicorn api.server:app --port 8000       # macOS / Linux
```

## What needs the planning service

Three pages (Tomorrow, Results, How it works) read only the exported JSON files and work without Python. "Plan
live" plans tomorrow from today's data (`/api/live/status`, `/api/live/refresh`, `/api/live/plan`, `/api/live/log`)
and needs the service. The "Try a battery" page changes the battery and plans again, which needs the optimiser: it calls `api/server.py`
(`POST /api/plan`, `POST /api/month`). If the service is not running the page says so and shows the command.

## Build a static site

```bash
bun run build      # type-check + build into web/dist/
bun run preview    # serve the build on http://localhost:4173
```

`web/dist/` can be put on any static file host. Routes use the `#/` style, so no server rewrites are needed.

## Where things are

| Path | What |
|---|---|
| `src/data/types.ts` | the data contract: every JSON shape the Python exporter writes |
| `src/data/api.ts` | loading the JSON files and calling the planning service (TanStack Query) |
| `src/main.tsx` | the frame and the five routes (TanStack Router) |
| `src/routes/` | one file per page |
| `src/charts/DayRail.tsx` | the day at a glance: decision, price, battery, charge level, demand on one time axis |
| `src/charts/Charts.tsx` | line, bar, stacked column and heat-map charts |
| `src/styles.css` | colours, type and layout |
| `public/data/` | exported data (regenerate with `python -m src.export.export_web`) |

Colours mean the same thing everywhere: blue = energy stored, amber = energy used from the battery, plum = price,
green = demand forecast and money saved, thin dark line = what really happened.
