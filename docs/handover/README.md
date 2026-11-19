# Handover report – sources and generator

This folder builds `reports/Project_Handover_Report.pdf`, the long handover report of the project (what was built,
every decision and why, how to run and change it). Every number and table in it is read from the repository's result
files at build time; nothing is typed in by hand.

## Rebuild the PDF

From the project folder:

```bash
.venv/bin/python docs/handover/build.py          # writes reports/Project_Handover_Report.pdf
.venv/bin/python docs/handover/build.py --html   # also keeps the HTML in docs/handover/out/ (for checking)
```

It takes well under a minute (it renders twice: the first pass finds the page numbers for the table of contents).
It works offline, and without `data/raw/` (the raw-folder table then says "raw cache unavailable").

**Needs** (in the project venv, listed in `requirements.in` and pinned in `requirements.txt`): `markdown`,
`playwright`, `pypdf`, plus `pandas`, `pyyaml`, `pillow` from the main project, and a
Chromium build for Playwright. If Playwright reports a missing browser:

```bash
uv pip install --python .venv/bin/python markdown playwright pypdf
.venv/bin/python -m playwright install chromium
```

**Rebuild the report after re-running the pipeline** (`python -m src.pipeline …`): the numbers then update by
themselves. The build also runs `pytest --collect-only` to count the tests.

## Folder layout

| Path | What |
|---|---|
| `build.py` | the generator: computes every number (`numbers()`), every generated table (`tables()`), fills the placeholders, renders HTML → PDF with headless Chromium, fixes links |
| `diagrams.py` | the inline SVG diagrams (architecture, timeline, data flow, dependencies, chronology, roles, battery flows, settlement, no-future rule) |
| `style.css` | print styles: A4, running header (chapter name), page numbers, tables, figures, boxes |
| `content/NN_*.md` | the prose, one file per chapter, read in file-name order (`00_front.md` = cover, contents, how to read) |
| `content/config_explain.yaml` | the plain-language explanation of each `config.yaml` key (Appendix B) |
| `content/key_numbers.yaml` | the list of headline numbers for the key numbers sheet (Appendix E) |
| `img/` | screenshots of the web app |
| `fonts/` | Archivo (the web app's font), bundled so the build needs no internet; licence in `fonts/LICENSE-Archivo.txt` |

## How to edit the text

Edit the Markdown in `content/`. Each file starts with `# <number> <Title>` (e.g. `# 7 Demand model`; appendices
use a letter). `##` headings appear in the table of contents. Use

```html
<div class="inshort" markdown="1">  … </div>   <!-- the "In short" box at the start of a chapter -->
<div class="caveat" markdown="1">   … </div>   <!-- an amber caveat next to a number -->
<div class="note" markdown="1">     … </div>   <!-- a grey note -->
```

Placeholders (an unknown one stops the build, so a number can never silently go missing):

| Placeholder | Inserts |
|---|---|
| `{{n:key}}` | a number or short text from `numbers()` in `build.py`, e.g. `{{n:dem_test_mae_best}}` |
| `{{c:battery.power_mw}}` | a value from `config.yaml` |
| `{{e:demand:A0:cv_mae}}` | one cell of `reports/experiments_<target>.csv` (experiment code, column) |
| `{{t:name}}` or `{{t:name\|caption}}` | a generated table (`tables()` in `build.py`, including all tables of `reports/make_report_tables.py`) |
| `{{fig:file.png\|caption}}` | a figure from `reports/figures/` |
| `{{img:path\|caption\|width}}` | any image in the repo (`tmp:` = the cropped screenshots made at build time) |
| `{{svg:name\|caption}}` | a diagram function in `diagrams.py` |

**Rule: never type a result number into the Markdown.** If you need a new number, add a key to `numbers()` that reads
it from the result file, then use `{{n:key}}`. Process facts (dates of the build, which model did what) are the
exception; they come from `prompts/briefs/handover_brief.md` and the git history.

Inline code that names a repo path (`` `src/pipeline.py` ``) becomes a link in the PDF, relative to `reports/`. The
build prints a warning for any such path that does not exist and does not link it.

## Checking the output

```bash
pdftoppm -r 50 -png reports/Project_Handover_Report.pdf /tmp/page   # one PNG per page (poppler)
```

Look at a chapter start, a wide table (Appendices B–D), a figure page and the last page.
