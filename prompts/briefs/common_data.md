# Common brief for all data agents (Phase 1)

Project: day-ahead electricity planning for a fictional Zurich DSO (university project). Repo root:
`/Users/lorik/Documents/Business analytics Group Project` (macOS). Read `prompts/end_to_end_build_prompt.md`
(§3 time rules, §4 data sources, §5 layout) and `docs/data_sources.md` before you start. `config.yaml` + `src/config.py`
hold settings and paths.

## Rules
- Python: use the existing venv `.venv/bin/python` (3.11). Do NOT create another venv. If you need a new package,
  install with `uv pip install --python .venv/bin/python <pkg>` and append it to `requirements.in`.
- Run python that reads downloaded files with `-I` is NOT required here; just run modules as `.venv/bin/python -m src.data.load_xxx` from the repo root.
- Do NOT run git commands (no commit, no push, no checkout). The orchestrator commits.
- Other agents work in the same folder at the same time. Only create/edit the files listed in your scope. Never edit
  `config.yaml`, `requirements.txt`, `README.md` or other agents' files.
- No invented data, URLs or numbers. If a source fails, try to diagnose (retry, backoff, alternative official URL). If it
  really cannot be had, use the documented fallback and say so clearly in your final report and in your assumptions file.
- Raw period: 2019-01-01 → 2026-10-31 (fetch a few days past the end if available, at least up to 2026-11-02 UTC, so
  local-time days are complete). Today is 2026-11-19.
- Everything stored in UTC. Timestamps = START of the interval, tz-aware (`datetime64[ns, UTC]`), column `timestamp_utc`
  (daily tables: column `date` as plain date, meaning the local Zurich calendar day or the trading day, state which).
- Units in column names (e.g. `load_kwh_15min`, `price_eur_mwh`, `temp_c`).
- Downloads go to `data/raw/<source>/` (cached: don't re-download if the file exists unless `--force`). Processed parquet
  to `data/processed/<name>.parquet`.
- Each loader is a module `src/data/load_<source>.py` with a `main(skip_download: bool = False)` function and
  `if __name__ == "__main__":` CLI (`--skip-download`, `--force`). With `skip_download=True` it must rebuild the
  processed parquet from the cached raw files only. It will later be called by `src/pipeline.py`.
- Each loader writes/overwrites a short check file `reports/data_checks/<name>.md` (rows, first and last timestamp,
  % missing, duplicates removed, anything odd). Use a small shared helper only inside your own files.
- Be polite to APIs: Energy-Charts blocks after ~15 quick calls → monthly or yearly chunks, ≥5 s pause, retry with
  exponential backoff on 429/5xx. Cache every chunk on disk as raw JSON so a rerun does not refetch.
- Tests: write `tests/test_loaders_<yourname>.py` (pytest) that checks your processed parquet files: tz-aware UTC,
  no duplicate timestamps, sorted, coverage of the period, plausible value ranges, missing share. Tests must read
  processed files only (no network). Run `.venv/bin/python -m pytest tests/test_loaders_<yourname>.py` and make it pass.
- Docs: write `docs/data_dictionary_<yourname>.md` (one table row per column: file, column, unit, source, time
  convention, publication lag) and `docs/assumptions_<yourname>.md` (one line per assumption with a one-line reason).
- Keep code simple and readable (it is a university project; students must be able to explain it). Docstrings in plain English.

## Final report (your last message)
Short: files created, row counts/coverage per processed file, checks done, problems + fallbacks used, anything the
feature builder must know (time conventions, gaps, quirks).
