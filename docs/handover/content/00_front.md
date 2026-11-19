# Front matter

<div class="cover" markdown="1">
<div class="kicker">HSG · Business Analytics &amp; Data Science Applications · HS 2026 · Group project</div>
<h1>Day-ahead planning for a Zurich DSO</h1>
<div class="sub">Project handover report: what was built, every decision and why, and how to run, change and defend it</div>
<div class="band"><span style="background:#17986A"></span><span style="background:#8A2F6B"></span><span style="background:#1D5FD1"></span><span style="background:#C47A0B"></span></div>
<div class="abstract" markdown="1">

**Abstract.** *Limmat Energie AG* is a fictional distribution system operator (DSO) for the city of Zurich, with the
real ewz city load as its demand and a fictional {{c:battery.power_mw}} MW / {{c:battery.capacity_mwh}} MWh grid battery. Every day at
{{c:auction.forecast_time_local}}, one hour before the Swiss day-ahead auction closes, the project forecasts tomorrow's demand and Swiss price for six
4-hour blocks, plans the battery with a small mixed-integer program, turns the plan into hourly auction bids and, in a
backtest, settles the bids with what really happened. In the test month October 2026 the demand forecast missed by
{{n:dem_test_mae_best}} MW on average (naive rule {{n:dem_test_mae_naive}} MW), the price forecast by {{n:pri_test_mae_best}} EUR/MWh
(naive {{n:pri_test_mae_naive}}), and the simulated saving against a simple rule was CHF {{n:total_saving_chf_test}}, of which about
{{n:pct_demand_of_saving_test}} % is avoided **assumed** imbalance penalty. This report explains the whole project for a new owner.

</div>
<div class="meta">Built from the repository on {{n:build_date}} by <code>docs/handover/build.py</code>. Every number and table is read from the result files at build time. The company and the battery are fictional; demand and prices are real; every money figure is a simulation.</div>
</div>

[[TOC]]

<div class="howto" markdown="1">

## How to read this document

**Who it is for.** A student or analyst who knows basic Python and statistics but was not there when the project was
built. After reading it you should be able to run the project, change it, and answer a lecturer's questions about it.

**Three ways to read it.**

| If you have … | Read |
|---|---|
| 10 minutes | Chapter 1 (the project in one page) and the "In short" box at the start of every chapter |
| one hour | Chapters 1–3, 11 (results), 13 (decision register) and 14 (limitations) |
| a day, because you now own the project | Everything, then run the commands in chapter 16 |

**Conventions.**

- Every chapter starts with an **In short** box (3–5 lines). Amber boxes are **caveats** that belong next to a number.
- `Code font` names a file, a column or a command. File names are links: they open the file in the repository
  (relative to the `reports/` folder where this PDF lives).
- **Money** is in CHF (converted hour by hour with the ECB EUR/CHF rate of the delivery day) unless a column says EUR.
  **October 2026 is the test month**, September 2026 the validation month, and "rolling" means the robustness run
  from 1 October 2025 to 31 August 2026.
- **Day D** is the day the forecast is made (at 10:00 Zurich time); **D+1** is the delivery day.
- Strategy numbers (1 baseline … 4 product … 6 ceiling) are explained in chapter 10.

**Where the numbers come from.** Nothing in this document is typed in by hand. The generator
`docs/handover/build.py` reads `reports/*.csv`, `reports/*.parquet`, `data/processed/*.parquet`,
`config.yaml`, the model settings in `models/` and the Markdown files in `docs/` and fills them into the text and the
tables. The tables that also appear in `reports/report.md` are produced by the same code
(`reports/make_report_tables.py`). Facts about **how** the project was built (dates, which AI model did what) come from
the orchestrator's record in `prompts/briefs/handover_brief.md` and from the git history; they are process facts, not
results.

**What this document is not.** It is not the graded report (`reports/report.md`) and not the one-pager
(`day_ahead_planning.md`). It repeats their results but adds the build history, the reasons behind every decision,
and the practical knowledge needed to keep the project alive.

</div>
