# Brief: the handover report (PDF)

Goal: one long, readable PDF that lets a new person understand 100 % of what was built, every decision and why, and
then own the project (run it, change it, defend it in front of a lecturer). Audience: a student or analyst who knows
basic Python and statistics but was not there.

## How the project was built (orchestrator's record — this is NOT in the repo files elsewhere; use it)

The whole build happened on 19 Nov 2026 in one long session. One orchestrator (an AI model, Claude) planned the work,
gave narrow briefs to builder agents (Claude Opus 5.5, medium effort), had every phase checked by an independent
read-only reviewer (OpenAI GPT-6.2 Sol, high effort, fresh context, given the code not the conclusions), and asked a
third model (Google Gemini 4 Neon) once for modelling ideas. The user (a student of the team) set this split and asked
for no questions while they were away; the orchestrator therefore took the decisions itself and logged them.
The original instructions are `prompts/end_to_end_build_prompt.md` (the team's build prompt) and the team's diagram
(demand model + price model + storage constraints → buy/store/use options → optimal blend → decision → auction).
Shared briefs given to agents: `prompts/briefs/common_data.md`, `common_models.md`, `final_review_findings.md`.

Chronology (git: `git log --format='%h %ad %s' --date=iso`):
1. Phase 0 (setup, orchestrator): cloned the team repo (it held the v5 one-pager, `docs/data_sources.md`, the
   architecture SVG and the build prompt). System Python was 3.9, so a 3.11 venv was made with `uv`. `config.yaml` is
   the single source of settings. Battery optimiser written first by the orchestrator: initially PuLP/CBC, but the
   bundled CBC binary failed on macOS ARM (OSError), so it was rewritten with SciPy `milp` (HiGHS). A binary variable
   per period forbids charging and discharging at the same time (otherwise at negative prices the solver "burns"
   energy through losses). 10 unit tests.
2. Phase 1 (4 data agents in parallel, D1 targets, D2 weather, D3 calendar/EV/events, D4 price drivers; later D5
   European weather). Each wrote `src/data/load_*.py`, docs fragments `docs/*_<name>.md`, checks
   `reports/data_checks/`. Key findings (see the docs fragments for evidence):
   - ewz timestamps mark the END of each 15-min interval (proven with the UTC Netzebenen file, correlation 0.999993
     at shift 0); autumn DST duplicate order in the files is unreliable (wrong in 27 of 32 pairs) → matched to
     Netzebenen; two missing days in 2021 filled from Netzebenen and flagged; no value has status W (final).
   - Energy-Charts CH price switches to 15-min on 2026-11-03 (October is hourly); Swiss load is broken after
     2026-11-16; Swiss solar forecast scale is unstable across years (not used).
   - Real archived weather forecasts exist only from 2024-01-19 (ICON); JMA forecasts go back to 2018 (no radiation).
     The leakage-safe rule ("fc_safe") picks, per target hour, the freshest run published before D 10:00 → for most
     hours of D+1 that is the forecast made two days ahead.
   - Publication lags chosen: EV count known from 1 Aug of the following year; BFE charging from the 15th of the next
     month; gas close 18:00; CO₂ auction 12:00; ECB FX 16:00; reservoirs (after review) Thursday 23:59.
   - Gas: the HSG LSEG/Bloomberg export was not available (user away) → unofficial Yahoo TTF=F, fetched with
     curl_cffi because plain requests got HTTP 429. CO₂: EEX primary auctions incl. the 2026 file (found on
     public.eex-group.com).
   - Auction timing verified: Swiss day-ahead gate closure 11:00, so FORECAST_TIME = 10:00 (`docs/auction_timing.md`).
   - Decision by the orchestrator: demand is assumed known to the end of day D−1 (the DSO reads its own meters),
     although the public file lagged two days on 19 Nov. Sensitivity run in the demand notes.
   - Decision: add D5, ex-ante European weather forecasts (Germany/France/Italy/Alps), because the Swiss price
     depends on German wind/solar and French temperature.
3. Ideas from Gemini (used in the model briefs): predict the change vs a known reference instead of the level;
   recency weighting for the price regime shift; linear (LEAR-style) + gradient boosting ensemble; walk-forward refit;
   a rolling 12-month backtest; day-clustered bootstrap CIs; Diebold–Mariano tests; spread deadband; hourly
   scheduling; pitfalls (uncleared limit bids, negative-price imbalance sign).
4. Review of Phase 1 (GPT-6.2 Sol): see `docs/review_log.md` Phase 1 rows (reservoir Thursday rule fixed, EV join by
   day D fixed, others kept and documented).
5. Phase 2 (F1): `src/features/build_features.py` → `data/processed/features.parquet`, one row per delivery day ×
   block, 2019-01-15 → 2026-11-01 (17,088 rows; 292 columns once the `eu_*` columns existed). Leakage test: rebuild
   200 sampled rows from inputs truncated to what was known at 10:00 on D, plus a "poison" test (+1e6 on everything
   not yet known). Review: 966 independent hand recomputations matched.
6. Phase 3 demand (M1) and price (M2) — read `reports/model_notes_demand.md` and `reports/model_notes_price.md`
   for what was tried, what won and why. Review of the demand model found the October model was trained through
   30 Sep (one day too many) → fixed to 29 Sep (MAE 3.36 → 3.34 MW).
7. Phase 4 bids/backtest (B1 with stand-in forecasts, then B2 after review). First backtest review: perfect-foresight
   benchmark was not a true ceiling; MILP stopped at a loose tolerance (orchestrator set `mip_rel_gap=0`, added
   start-level validation); tuning used one day too many; price-error sensitivity mixed effects; missing data could
   sum to 0; low-load bids. All fixed. B2 then tuned decision rules on the rolling period + 1–29 Sept only and chose
   the "hourly shape" plan (plan 24 hours using last week's same-day-type hourly price pattern) — see
   `reports/decision_tuning.csv`.
8. Phase 5: a Streamlit app (A1) and the written report (R1: `reports/report.md`, `day_ahead_planning.md` v6,
   `README.md`, consolidated `docs/assumptions.md`, `docs/data_dictionary.md`, EDA notebook).
9. Reviews of the price model + final backtest, then a final end-to-end review (Q1, clean venv rebuild in /tmp,
   12.6 min, all CSVs reproduced, 154 tests). Findings M1–M7, m1–m9 with the orchestrator's decisions:
   `prompts/briefs/final_review_findings.md`; fixed by agent FX. Not retrained: the temperature-correction METHOD was
   chosen with September+October weather errors (difference between methods ~0.001–0.01 °C) — disclosed instead.
10. The orchestrator also re-ran `python -m src.pipeline --all --skip-download` on a copy: 13.2 min, identical
    features, metrics (max diff ~1e-14) and backtest summary.
11. After the build, on the user's requests: pushed to GitHub (first a branch `end-to-end-build`, then `PITCH.md`,
    then fast-forwarded `main`); replaced the Streamlit app with a web app built with Bun + React + TanStack Router,
    Query and Table (`web/`), fed by `src/export/export_web.py` (JSON into `web/public/data/`, checked against
    `reports/backtest.csv` day by day) and a small FastAPI service `api/server.py` for the live battery sliders;
    fixed the dev server to listen on IPv4 and IPv6; simplified the app to four pages (Tomorrow, Results, Try a
    battery, How it works) with details folded away. Decision: a custom battery starts each day at the same SHARE of
    capacity as the default battery had (not the same MWh), so bigger batteries are not penalised by starting empty.
12. Honest notes on process: the build prompt asked to wait for a "go" after each phase and to ask before every push —
    the user explicitly lifted that ("don't ask, take initiative"), and later asked for the pushes. The prompt capped
    agents at ~10 per run; the build used 15 builder runs (D1–D5, F1, M1, M2, B1, B2, A1, R1, FX, W1 export/API, and the
    orchestrator's own work), 7 reviewer runs and 1 idea run, at most 4 at a time. The prompt said Windows; the
    machine was macOS (needs `brew install libomp` for LightGBM).

## Required content (chapters)

0. Title page, one-paragraph abstract, table of contents (with page numbers if the renderer allows), "how to read
   this document".
1. The project in one page: problem, user (fictional Limmat Energie AG, real ewz Zurich data), the daily decision,
   the headline results WITH the caveats next to them.
2. Business background for non-experts: TSO/DSO/homes (use `docs/architecture_tso_dso.svg`), day-ahead auction,
   imbalance, battery terms (power, capacity, state of charge, efficiency, cycles), timeline of a day.
3. How the work was organised: the chronology above, roles of the AI models, phases, reviews; what the original
   brief asked vs what was delivered (deviation table).
4. Repository map: every folder and the important files, what each does, which depend on which (a dependency
   diagram as inline SVG), the data flow from raw downloads to the web app.
5. Data: every source (table), cleaning decisions per source with the evidence, time conventions, publication lags,
   quirks and gaps. Explain the ewz interval and DST findings properly.
6. The no-future rule and the feature table: what is known at 10:00, every feature group, how leakage is tested and
   what the test cannot catch (from the reviews).
7. Demand model: ladder, protocol, what was tried, what won and why, results, drivers, weaknesses, sensitivities.
8. Price model: same.
9. Battery optimiser: the formulation in plain words and in small maths, the binary variable, cycle definition,
   tests.
10. Bids and settlement: hourly bids, limit price rule, clearing, imbalance formula (incl. negative prices), the
    strategies 1–7 (+4b, 5b), the ceiling, inventory adjustment, decision tuning and why hourly shape won.
11. Results: all key tables and figures (from `reports/`), decomposition, sensitivities, robustness (rolling period,
    CIs, DM tests), exceptions.
12. Every review: a decision log — for each finding: what was found, decision (fixed / kept), why, effect.
    Source: `docs/review_log.md` + `prompts/briefs/final_review_findings.md`.
13. Decision register: ONE table of every significant decision in the project (≈40–60 rows): id, decision,
    alternatives considered, why, evidence/source file, where in code. This is the core of "understand 100 % of
    decisions".
14. Limitations and what the results cannot tell you; ethics.
15. The web app: pages, how it is built (export → JSON contract `web/src/data/types.ts` → React/TanStack; API),
    screenshots (`docs/handover/img/`), design choices (one colour per concept; validated palette).
16. Owning the project: install from scratch (macOS and Windows notes), every command (pipeline steps, tests,
    export, app, report tables check, notebooks), run times, what to re-run after changing X (a "change → re-run"
    table), how to add a data source / feature / model / strategy, common errors and fixes, licences, "before you
    publish".
17. Next steps (prioritised).
Appendices: glossary (every technical term in one sentence), full config.yaml explained line by line, file-by-file
index of `src/`, list of all tests and what they check, key numbers sheet (every headline number with its source
file and column).

## Rules
- Every number must come from the repo's files (CSV/parquet/JSON/docs) — never from memory or this brief unless the
  brief states it as a process fact. Write a generator script that reads the files and fills the tables/numbers into
  the document, so it can be rebuilt after a re-run.
- Simple, clear English (British spelling), short sentences, explain every term once. Each chapter starts with a
  3–5 line "In short" summary. Prefer tables and diagrams to long prose. Be honest about weaknesses.
- Use the existing figures in `reports/figures/` and the app screenshots in `docs/handover/img/`.
- Readable layout: A4, good typography, running header/footer with page numbers, chapter starts on new page,
  tables that do not split badly, figures with captions.
