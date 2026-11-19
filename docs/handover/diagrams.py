"""Inline SVG diagrams for the handover report (boxes and arrows, one colour per concept).

Colours follow the web app: stored energy = blue, used energy = amber, price = plum,
demand / money saved = green, ink = dark teal-grey. Each function returns an <svg> string.
"""
from __future__ import annotations

from html import escape

INK = "#12262B"
MUTED = "#5B6B70"
LINE = "#9AA7AB"
PAPER = "#F4F6F6"
STORED = "#1D5FD1"
USED = "#C47A0B"
PRICE = "#8A2F6B"
DEMAND = "#17986A"
SAVING = "#1F7A52"
TINT = {STORED: "#E6EEFB", USED: "#FAF0E1", PRICE: "#F4E8F0", DEMAND: "#E4F4EE", SAVING: "#E4F1EA",
        INK: "#E9EDEE", MUTED: "#EEF1F1"}


def _svg(w: int, h: int, body: str, label: str) -> str:
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{escape(label)}" '
            f'xmlns="http://www.w3.org/2000/svg" font-family="Archivo Variable, Helvetica, Arial, sans-serif">'
            f'<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/></marker></defs>'
            f'{body}</svg>')


def box(x, y, w, h, lines, color=INK, bold_first=True, size=11, fill=None, align="middle") -> str:
    fill = fill or TINT.get(color, PAPER)
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{fill}" stroke="{color}" stroke-width="1.2"/>']
    if isinstance(lines, str):
        lines = [lines]
    n = len(lines)
    lh = size + 3
    y0 = y + h / 2 - (n - 1) * lh / 2 + size * 0.35
    tx = x + w / 2 if align == "middle" else x + 8
    for i, ln in enumerate(lines):
        wt = "650" if (i == 0 and bold_first) else "400"
        col = INK if i == 0 else MUTED
        fs = size if i == 0 else size - 1.5
        out.append(f'<text x="{tx}" y="{y0 + i * lh:.1f}" text-anchor="{align if align == "middle" else "start"}" '
                   f'font-size="{fs}" font-weight="{wt}" fill="{col}">{escape(ln)}</text>')
    return "".join(out)


def arrow(x1, y1, x2, y2, color=MUTED, dash=False, label=None, lx=None, ly=None) -> str:
    d = ' stroke-dasharray="4 3"' if dash else ""
    s = (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.3"{d} '
         f'marker-end="url(#ah)"/>')
    if label:
        s += text(lx if lx is not None else (x1 + x2) / 2, ly if ly is not None else (y1 + y2) / 2 - 4, label, 9.5, MUTED)
    return s


def path(dstr, color=MUTED, dash=False) -> str:
    d = ' stroke-dasharray="4 3"' if dash else ""
    return f'<path d="{dstr}" fill="none" stroke="{color}" stroke-width="1.3"{d} marker-end="url(#ah)"/>'


def text(x, y, s, size=10, color=INK, anchor="middle", weight="400") -> str:
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" font-weight="{weight}" '
            f'fill="{color}">{escape(s)}</text>')


# ----------------------------------------------------------------------------- diagrams
def architecture() -> str:
    """The team's diagram as built: three inputs -> options -> optimal blend -> decision -> bids -> settlement."""
    b = []
    b.append(box(10, 10, 200, 58, ["Demand model", "Zurich load, MW per block", "src/models/demand.py"], DEMAND))
    b.append(box(240, 10, 200, 58, ["Price model", "Swiss price, EUR/MWh per block", "src/models/price.py"], PRICE))
    b.append(box(470, 10, 200, 58, ["Storage constraints", "20 MW / 40 MWh, 10–90 %, 90 %", "config.yaml"], STORED))
    for x in (110, 340, 570):
        b.append(arrow(x, 68, 340, 98))
    b.append(box(170, 100, 340, 46, ["Buy and store / use storage?", "buy · buy and store · use storage and buy · use storage"], INK))
    b.append(arrow(340, 146, 340, 166))
    b.append(box(170, 168, 340, 46, ["Optimal blend", "mixed-integer program per day · src/optimisation/battery_lp.py"], INK))
    b.append(arrow(340, 214, 340, 234))
    b.append(box(170, 236, 340, 46, ["Decision", "6-block plan with option labels · src/decision/bids.py"], INK))
    b.append(arrow(340, 282, 340, 302))
    b.append(box(170, 304, 340, 46, ["Auction purchase", "hourly bids: volume + limit price · src/decision/bids.py"], INK))
    b.append(arrow(340, 350, 340, 370))
    b.append(box(170, 372, 340, 46, ["Backtest settlement (new)", "actual prices and demand, imbalance · src/backtest/"], SAVING))
    b.append(text(560, 395, "→ reports/ → web app", 10, MUTED, "start"))
    return _svg(680, 425, "".join(b), "Architecture from the team's diagram")


def day_timeline() -> str:
    """One day of the process on a time axis (day D and D+1)."""
    b = []
    y = 70
    b.append(f'<line x1="20" y1="{y}" x2="660" y2="{y}" stroke="{INK}" stroke-width="1.5"/>')
    ticks = [(40, "D 00:00"), (140, "D 10:00"), (200, "D 11:00"), (250, "~11:10"), (310, "~12:45"),
             (420, "D+1 00:00"), (640, "D+2")]
    for x, lab in ticks:
        b.append(f'<line x1="{x}" y1="{y - 5}" x2="{x}" y2="{y + 5}" stroke="{INK}"/>')
        b.append(text(x, y + 18, lab, 9.5, MUTED))
    b.append(f'<rect x="420" y="{y - 9}" width="220" height="18" fill="{TINT[DEMAND]}" stroke="none"/>')
    b.append(text(530, y + 4, "delivery day D+1 (6 blocks, 23/24/25 h)", 9.5, SAVING))
    items = [(140, 10, "Forecast", "demand + price, 6 blocks", DEMAND),
             (200, 100, "Gate closure", "Swiss auction, bids in", PRICE),
             (310, 10, "Neighbours' results", "DE/FR/AT/IT for D+1 (too late)", MUTED),
             (520, 100, "Battery runs", "charge / discharge", STORED),
             (640, 10, "Settlement", "imbalance, actuals", SAVING)]
    for x, yy, t1, t2, col in items:
        bx = min(max(x - 75, 5), 525)
        if t1 == "Neighbours' results":
            bx = 232
        if t1 == "Forecast":
            bx = 60
        b.append(box(bx, yy, 150, 38, [t1, t2], col, size=10.5))
        b.append(f'<line x1="{x}" y1="{yy + 38 if yy < y else yy}" x2="{x}" y2="{y}" stroke="{col}" stroke-dasharray="3 2"/>')
    return _svg(680, 150, "".join(b), "Timeline of one planning day")


def dataflow() -> str:
    """From raw downloads to the web app."""
    b = []
    col_x = [10, 150, 290, 430, 570]
    heads = ["Sources (internet)", "Loaders", "Clean tables", "Models & decision", "Outputs"]
    for x, h in zip(col_x, heads):
        b.append(text(x + 55, 16, h, 10.5, INK, weight="650"))
    b.append(box(10, 28, 110, 250, ["ewz, Energy-Charts,", "MeteoSwiss, Open-Meteo,", "ECB, EEX, BFE, Yahoo,",
                                    "Stadt Zürich, OxCGRT,", "football-data", "", "→ data/raw/ (cache)"], MUTED, bold_first=False, size=10))
    b.append(arrow(120, 150, 148, 150))
    b.append(box(150, 28, 110, 250, ["src/data/", "load_*.py", "(one per source)", "", "+ data/manual/", "events_zurich.csv", "",
                                     "checks →", "reports/data_checks/"], INK, size=10))
    b.append(arrow(260, 150, 288, 150))
    b.append(box(290, 28, 110, 110, ["data/processed/", "*.parquet (UTC)", "demand, prices,", "weather, calendar …"], INK, size=10))
    b.append(arrow(345, 138, 345, 166))
    b.append(box(290, 168, 110, 110, ["features.parquet", "1 row = day × block", "src/features/", "+ hourly_actuals"], INK, size=10))
    b.append(arrow(400, 200, 428, 70))
    b.append(arrow(400, 222, 428, 160))
    b.append(box(430, 28, 110, 80, ["src/models/", "demand.py, price.py", "→ models/*.joblib", "→ predictions_*.parquet"], DEMAND, size=10))
    b.append(arrow(485, 108, 485, 126))
    b.append(box(430, 128, 110, 80, ["src/backtest/", "+ optimisation/", "+ decision/bids.py", "settle with actuals"], STORED, size=10))
    b.append(arrow(400, 260, 428, 190, dash=True))
    b.append(text(392, 296, "actuals", 9.5, MUTED, "end"))
    b.append(box(430, 228, 110, 50, ["src/export/", "export_web.py"], INK, size=10))
    b.append(arrow(485, 208, 485, 226))
    b.append(arrow(540, 60, 568, 60))
    b.append(box(570, 28, 100, 64, ["reports/", "metrics, backtest,", "figures, notes"], SAVING, size=10))
    b.append(arrow(540, 168, 568, 70))
    b.append(box(570, 128, 100, 64, ["reports/", "report.md", "(tables checked)"], SAVING, size=10))
    b.append(arrow(540, 253, 568, 253))
    b.append(box(570, 220, 100, 58, ["web/public/data", "JSON → web app"], PRICE, size=10))
    b.append(box(430, 300, 240, 40, ["api/server.py (FastAPI)", "re-plans a day / month for the battery sliders"], STORED, size=10))
    b.append(path("M 620 278 L 620 298", MUTED, dash=True))
    b.append(text(10, 360, "src/pipeline.py runs every step in this order (left to right)", 10, MUTED, "start"))
    return _svg(680, 370, "".join(b), "Data flow from downloads to the web app")


def dependencies() -> str:
    """Which module imports which (checked against the import lines)."""
    b = []
    nodes = {
        "config": (290, 10, "src/config.py", "config.yaml"),
        "loaders": (10, 90, "src/data/*", "one loader per source"),
        "features": (170, 90, "src/features/", "build_features, feature_sets"),
        "common": (330, 90, "src/models/common.py", "+ price_common.py"),
        "lp": (500, 90, "src/optimisation/", "battery_lp.py"),
        "models": (250, 170, "src/models/", "demand.py, price.py"),
        "bids": (500, 170, "src/decision/", "bids.py"),
        "backtest": (420, 250, "src/backtest/", "run_backtest, analysis"),
        "export": (420, 330, "src/export/", "export_web.py"),
        "api": (250, 330, "api/server.py", "FastAPI"),
        "pipeline": (10, 250, "src/pipeline.py", "runs every step"),
        "report": (10, 330, "reports/make_report_tables.py", "reads reports/*.csv only"),
    }
    colors = {"models": DEMAND, "lp": STORED, "bids": STORED, "backtest": STORED, "api": PRICE, "export": PRICE}
    W, H = 160, 44
    for k, (x, y, t1, t2) in nodes.items():
        b.append(box(x, y, W, H, [t1, t2], colors.get(k, INK), size=10.5))

    def c(k, side):
        x, y, *_ = nodes[k]
        return {"top": (x + W / 2, y), "bottom": (x + W / 2, y + H), "left": (x, y + H / 2), "right": (x + W, y + H / 2)}[side]
    edges = [("features", "top", "config", "bottom"), ("loaders", "top", "config", "left"),
             ("models", "top", "features", "bottom"), ("models", "top", "common", "bottom"),
             ("bids", "top", "lp", "bottom"), ("backtest", "top", "bids", "bottom"),
             ("backtest", "top", "lp", "bottom"), ("export", "top", "backtest", "bottom"),
             ("api", "right", "export", "left"), ("lp", "top", "config", "right")]
    for a_, sa, b_, sb in edges:
        (x1, y1), (x2, y2) = c(a_, sa), c(b_, sb)
        b.append(arrow(x1, y1, x2, y2))
    for k in ["loaders", "features", "models", "backtest", "export"]:
        x1, y1 = c("pipeline", "right")
        x2, y2 = c(k, "left") if k not in ("loaders",) else c(k, "bottom")
        b.append(arrow(x1, y1, x2, y2, dash=True))
    b.append(text(340, 395, "solid arrow = imports (A → B: A uses B) · dashed = calls / reads", 9.5, MUTED))
    return _svg(680, 405, "".join(b), "Module dependencies")


def phases() -> str:
    """Build chronology on 19 Nov 2026: builders, reviewers, idea model."""
    b = []
    rows = [("Phase 0 · setup", "orchestrator: venv, config, battery MILP + 10 tests", INK, "12:16"),
            ("Phase 1 · data", "D1 targets · D2 weather · D3 calendar/EV/events · D4 price drivers · D5 EU weather", INK, "12:33"),
            ("Ideas", "Gemini 4 Neon: change vs reference, recency weights, ensembles, CIs, DM tests …", PRICE, ""),
            ("Phase 2 · features", "F1: features.parquet + leakage tests", INK, "13:23"),
            ("Phase 3 · models", "M1 demand · M2 price (optimiser fixes after review)", DEMAND, "13:58–14:13"),
            ("Phase 4 · bids, backtest", "B1 (stand-in forecasts) → B2 (ML forecasts, tuning, hourly shape)", STORED, "14:53"),
            ("Phase 5 · app, report", "A1 Streamlit app · R1 report, one-pager, docs, EDA", INK, "15:12"),
            ("Final review + fixes", "Q1 clean rebuild, findings M1–M7, m1–m9 · FX fixes", SAVING, "15:56"),
            ("After the build", "pitch · W1 web app (Bun + TanStack) + export + API · simplified to 4 pages", PRICE, "16:55–17:30")]
    y = 8
    for name, what, col, t in rows:
        b.append(box(10, y, 150, 30, [name], col, size=10.5))
        b.append(f'<rect x="170" y="{y}" width="420" height="30" rx="5" fill="{PAPER}" stroke="{LINE}"/>')
        b.append(text(180, y + 19, what, 9.8, INK, "start"))
        b.append(text(670, y + 19, t, 9.8, MUTED, "end"))
        if name not in ("Ideas", "After the build", "Final review + fixes"):
            b.append(f'<circle cx="600" cy="{y + 15}" r="5" fill="{SAVING}"/>')
        y += 36
    b.append(text(170, y + 12, "● = phase reviewed by GPT-6.2 Sol", 9.5, SAVING, "start"))
    b.append(text(670, y + 12, "commit time", 9.5, MUTED, "end"))
    return _svg(680, y + 20, "".join(b), "Build chronology")


def known_at() -> str:
    """What is known at 10:00 on day D (the no-future rule)."""
    b = []
    x0, x1 = 170, 660
    # axis: D-2 00:00 .. D+2 00:00 => 4 days
    def X(day_frac):  # 0 = D-2 00:00
        return x0 + (x1 - x0) * day_frac / 4
    fc = X(2 + 10 / 24)
    b.append(f'<rect x="{X(3)}" y="10" width="{X(4) - X(3)}" height="250" fill="{TINT[DEMAND]}"/>')
    b.append(text((X(3) + X(4)) / 2, 22, "delivery day D+1", 10, SAVING, weight="650"))
    lanes = [("Zurich demand", X(2), DEMAND, "to end of D−1 (DSO meters)"),
             ("CH + neighbour prices", X(3), PRICE, "all of day D"),
             ("Swiss load / generation", X(2), MUTED, "to end of D−1"),
             ("Observed weather", X(2 + 9 / 24), MUTED, "hours ending ≤ 09:00 on D"),
             ("Gas · CO₂ · EUR/CHF", X(2), MUTED, "last value published before 10:00"),
             ("Reservoir level", X(1.2), MUTED, "Sunday value from Thursday 23:59"),
             ("Weather forecast for D+1", None, STORED, "run published by 10:00 (mostly 2 days ahead)"),
             ("Calendar, events, holidays", None, INK, "known in advance")]
    y = 36
    for name, end, col, note in lanes:
        b.append(text(160, y + 13, name, 10, INK, "end"))
        if end is not None:
            b.append(f'<rect x="{x0}" y="{y + 3}" width="{end - x0}" height="14" fill="{TINT.get(col, PAPER)}" stroke="{col}"/>')
            b.append(text(min(end + 4, x1 - 2), y + 14, note, 9, MUTED, "start" if end < X(3.2) else "end"))
        elif col == STORED:
            b.append(f'<rect x="{X(3)}" y="{y + 3}" width="{X(4) - X(3)}" height="14" fill="{TINT[STORED]}" stroke="{STORED}" stroke-dasharray="3 2"/>')
            b.append(text(X(3) - 4, y + 14, note, 9, MUTED, "end"))
        else:
            b.append(f'<rect x="{x0}" y="{y + 3}" width="{x1 - x0}" height="14" fill="{TINT[INK]}" stroke="{LINE}"/>')
            b.append(text(x0 + 6, y + 14, note, 9, MUTED, "start"))
        y += 27
    b.append(f'<line x1="{fc}" y1="10" x2="{fc}" y2="{y + 4}" stroke="{PRICE}" stroke-width="1.6"/>')
    b.append(text(fc, y + 16, "D 10:00 forecast", 10, PRICE, weight="650"))
    for d, lab in [(0, "D−2"), (1, "D−1"), (2, "D"), (3, "D+1"), (4, "D+2")]:
        b.append(f'<line x1="{X(d)}" y1="30" x2="{X(d)}" y2="{y}" stroke="{LINE}" stroke-dasharray="2 3"/>')
        b.append(text(X(d) + 3, y + 16 if d != 2 else y + 30, lab, 9, MUTED, "start"))
    return _svg(680, y + 36, "".join(b), "What is known at 10:00 on day D")


def battery_flows() -> str:
    """Energy flows of one period in the optimiser."""
    b = []
    b.append(box(20, 70, 130, 50, ["Auction", "buy_t at price P_t"], PRICE))
    b.append(box(275, 10, 130, 50, ["Battery", "soc_t, 10–90 % of 40 MWh"], STORED))
    b.append(box(530, 70, 130, 50, ["City of Zurich", "demand D_t (forecast)"], DEMAND))
    b.append(arrow(150, 95, 528, 95, label="buy_t − ch_t goes straight to the city", ly=110))
    b.append(path("M 150 80 C 210 60, 220 40, 273 35", STORED))
    b.append(text(200, 42, "ch_t × √0.9", 10, STORED))
    b.append(path("M 405 35 C 460 40, 470 60, 528 80", USED))
    b.append(text(482, 42, "dis_t (÷ √0.9 from stock)", 10, USED))
    b.append(text(340, 145, "buy_t = D_t + ch_t − dis_t · ch_t and dis_t never both > 0 · Σ dis_t ≤ 32 MWh per day", 10, MUTED))
    return _svg(680, 160, "".join(b), "Energy flows in the battery plan")


def settlement() -> str:
    """From bids to the bill."""
    b = []
    b.append(box(10, 30, 140, 56, ["Hourly bids", "demand (any price)", "charge (limit price)"], INK, size=10.5))
    b.append(arrow(150, 58, 178, 58))
    b.append(box(180, 30, 140, 56, ["Auction clears", "actual price p_h", "charge bid: p_h ≤ limit?"], PRICE, size=10.5))
    b.append(arrow(320, 58, 348, 58))
    b.append(box(350, 30, 140, 56, ["Delivery", "battery follows what", "was really bought"], STORED, size=10.5))
    b.append(arrow(490, 58, 518, 58))
    b.append(box(520, 30, 150, 56, ["Imbalance", "shortage: p + 0.2·|p|", "surplus: p − 0.2·|p|"], USED, size=10.5))
    b.append(text(340, 112, "cost = auction purchases + imbalance settlement + wear (5 EUR/MWh discharged), in CHF via the ECB rate", 10, MUTED))
    return _svg(680, 122, "".join(b), "Settlement of one hour")


def roles() -> str:
    """Who did what in the build."""
    b = []
    b.append(box(255, 10, 170, 48, ["User (team student)", "set the model split, then away"], INK))
    b.append(arrow(340, 58, 340, 84))
    b.append(box(230, 86, 220, 54, ["Orchestrator (Claude)", "plans, writes briefs, decides,", "logs decisions, commits"], INK))
    b.append(box(10, 180, 200, 54, ["Builder agents", "Claude Opus 5.5, medium effort", "D1–D5, F1, M1, M2, B1, B2, A1, R1, FX, W1"], DEMAND))
    b.append(box(240, 180, 200, 54, ["Reviewer", "OpenAI GPT-6.2 Sol, high effort", "fresh context, read-only, gets the code"], SAVING))
    b.append(box(470, 180, 200, 54, ["Idea model", "Google Gemini 4 Neon", "asked once for modelling ideas"], PRICE))
    b.append(arrow(280, 140, 110, 178, label="narrow briefs", lx=170, ly=152))
    b.append(arrow(340, 140, 340, 178, label="code, not conclusions", lx=395, ly=165))
    b.append(arrow(400, 140, 570, 178, label="one question", lx=520, ly=152))
    return _svg(680, 245, "".join(b), "Roles in the build")
