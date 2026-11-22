"""Live planning API for the web app.

Run from the repo root::

    .venv/bin/python -m uvicorn api.server:app --port 8000

Endpoints (JSON shapes: ``web/src/data/types.ts``):

* ``GET  /api/health`` -> ``{"ok": true}``
* ``POST /api/plan``   body ``PlanRequest``  -> ``DayPlan`` of the product for that day with the given
  battery (``split = "custom"``). Built by the same function as the exported day files
  (``src.export.export_web.build_day_plan``).
  Start charge level = the same SHARE of capacity that the default battery had at the start of that day in the
  stored backtest, clipped into the new battery's allowed range [soc_min_frac, soc_max_frac] x capacity.
  ``soc_start_frac`` is the level the plan returns to at the end of the day (as in the backtest); it is
  clipped into the same range, and the clipped value is returned in ``battery``.
* ``POST /api/month``  body ``MonthRequest`` -> ``MonthResult`` for the test month (October 2026): baseline,
  ML without battery, the product and the hourly ceiling with that battery, inventory-adjusted like the
  backtest. Results are cached per battery setting (LRU).

Invalid input -> HTTP 422 with ``{"detail": "<readable message>"}``.
"""
from __future__ import annotations

import datetime as dt
from contextlib import asynccontextmanager
from functools import lru_cache

from src.config import load_config
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.export import export_web as ex


class BatterySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    power_mw: float = Field(ge=1, le=1000)   # total of all units (app: up to 10 x 100 MW)
    capacity_mwh: float = Field(ge=1, le=4000)  # total of all units (app: up to 10 x 200 MWh)
    soc_min_frac: float = Field(ge=0, le=1)
    soc_max_frac: float = Field(ge=0, le=1)
    soc_start_frac: float = Field(ge=0, le=1)
    round_trip_efficiency: float = Field(ge=0.5, le=1)
    max_cycles_per_day: float = Field(ge=0, le=4)
    wear_cost_eur_per_mwh: float = Field(ge=0, le=50)
    allow_sell: bool = False

    @model_validator(mode="after")
    def _range(self):
        if not self.soc_min_frac < self.soc_max_frac:
            raise ValueError("soc_min_frac must be smaller than soc_max_frac")
        return self

    def settings(self) -> dict:
        d = self.model_dump()
        d["soc_start_frac"] = min(max(d["soc_start_frac"], d["soc_min_frac"]), d["soc_max_frac"])
        return d


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: dt.date
    battery: BatterySettings


class MonthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    battery: BatterySettings


@asynccontextmanager
async def _lifespan(app):
    """Load the data once at start-up so the first /api/plan answers quickly."""
    days = sorted(_plan_dates())
    if days:
        plan_for(days[-1], ex.default_battery_settings())
    yield


app = FastAPI(title="Limmat Energie day-ahead planning API", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class InputError(ValueError):
    pass


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    msgs = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e.get("loc", ()) if x != "body")
        msg = str(e.get("msg", "invalid value")).removeprefix("Value error, ")
        msgs.append(f"{loc}: {msg}" if loc else msg)
    return JSONResponse(status_code=422, content={"detail": "; ".join(msgs)})


@app.exception_handler(InputError)
async def _input_error(request: Request, exc: InputError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@lru_cache(maxsize=1)
def _plan_dates() -> dict:
    return {str(d): s for d, s in ex.export_dates()}


def start_level(date: str, settings: dict) -> float:
    """Start level for a custom battery: the SAME SHARE of capacity as the default battery had on
    that morning in the backtest, clipped into the new battery's range. (Keeping the MWh instead
    would make a bigger battery start nearly empty and look worse than it is.)"""
    lo = settings["soc_min_frac"] * settings["capacity_mwh"]
    hi = settings["soc_max_frac"] * settings["capacity_mwh"]
    carried = ex.carried_soc(date)
    default_capacity = float(load_config()["battery"]["capacity_mwh"])
    if carried is None:
        level = settings["soc_start_frac"] * settings["capacity_mwh"]
    else:
        level = carried / default_capacity * settings["capacity_mwh"]
    return min(max(level, lo), hi)


def plan_for(date: str, settings: dict) -> dict:
    if date not in _plan_dates():
        days = sorted(_plan_dates())
        raise InputError(f"date: {date} is not a planning day (choose a day from {days[0]} to {days[-1]})")
    plan = ex.build_day_plan(date, settings, start_level(date, settings), "custom")
    return ex.strip_raw(plan)


def _key(settings: dict) -> tuple:
    return tuple(sorted((k, float(v)) for k, v in settings.items()))


@lru_cache(maxsize=32)
def _month_cached(key: tuple) -> dict:
    s = dict(key)
    s["allow_sell"] = bool(s["allow_sell"])
    return ex.month_result(s)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/plan")
def plan(req: PlanRequest) -> JSONResponse:
    return JSONResponse(plan_for(str(req.date), req.battery.settings()))


@app.post("/api/month")
def month(req: MonthRequest) -> JSONResponse:
    return JSONResponse(_month_cached(_key(req.battery.settings())))


# ---------------------------------------------------------------------------
# Plan live: tomorrow from today's data (src/live/refresh.py + src/live/plan.py)
# ---------------------------------------------------------------------------
class LiveOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temp_shift_c: float = Field(default=0.0, ge=-15, le=15)
    is_holiday: bool | None = None
    gas_eur_mwh: float | None = Field(default=None, ge=0, le=1000)
    demand_scale_pct: float = Field(default=0.0, ge=-50, le=50)


class LivePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    battery: BatterySettings | None = None
    soc_start_mwh: float | None = Field(default=None, ge=0)
    overrides: LiveOverrides | None = None


class LiveRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = False


def _live_status(status: list | None, fetched_at: str | None) -> dict:
    from src.live import plan as lp
    return {"fetched_at_utc": fetched_at, "delivery_date": str(lp.tomorrow_local()), "sources": status or []}


def _live_tables(refresh_if_missing: bool):
    """(tables, status list, fetched_at) from today's cache; refresh first if there is none."""
    from src.live import refresh as lr
    cached = lr.load_cached_tables()
    if cached is None:
        if not refresh_if_missing:
            return None, [], None
        cached = lr.refresh_tables()
    tables, status = cached
    return tables, status, _fetched_at(status)


def _fetched_at(status) -> str | None:
    from src.live import refresh as lr
    f = getattr(lr, "fetched_at", None)
    if callable(f):
        try:
            return f()
        except Exception:  # noqa: BLE001 - optional helper
            return None
    for s in status or []:
        if isinstance(s, dict) and s.get("fetched_at_utc"):
            return s["fetched_at_utc"]
    return None


@app.get("/api/live/status")
def live_status() -> JSONResponse:
    _, status, fetched = _live_tables(refresh_if_missing=False)
    return JSONResponse(_live_status(status, fetched))


@app.post("/api/live/refresh")
def live_refresh(req: LiveRefreshRequest | None = None) -> JSONResponse:
    from src.live import refresh as lr
    _, status = lr.refresh_tables(force=bool(req and req.force))
    return JSONResponse(_live_status(status, _fetched_at(status)))


@app.post("/api/live/plan")
def live_plan(req: LivePlanRequest | None = None) -> JSONResponse:
    from src.live import plan as lp
    req = req or LivePlanRequest()
    tables, status, _ = _live_tables(refresh_if_missing=True)
    battery = req.battery.settings() if req.battery else None
    overrides = req.overrides.model_dump() if req.overrides else None
    if battery is not None and req.soc_start_mwh is not None:
        cap = battery["capacity_mwh"]
        if req.soc_start_mwh > cap:
            raise InputError(f"soc_start_mwh: must be at most the capacity ({cap:g} MWh)")
    try:
        plan = lp.live_plan(tables, battery=battery, soc_start_mwh=req.soc_start_mwh,
                            overrides=overrides, sources=status)
    except (ValueError, KeyError) as e:
        raise InputError(f"live plan failed: {e}") from e
    if lp.is_default(overrides, req.soc_start_mwh, battery):
        lp.save_log(plan)
    return JSONResponse(plan)


@app.get("/api/live/log")
def live_log() -> JSONResponse:
    from src.live import plan as lp
    tables, _, _ = _live_tables(refresh_if_missing=False)
    return JSONResponse(lp.read_log(tables))
