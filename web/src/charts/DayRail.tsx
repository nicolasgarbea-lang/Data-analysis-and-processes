import { useMemo, useState } from "react";
import { scaleLinear } from "d3-scale";
import type { DayPlan, Option } from "../data/types";
import { dec1, int } from "../lib/format";
import { niceTicks, useWidth } from "./base";

const OPTION_WORDS: Record<Option, string> = {
  buy: "Buy",
  buy_and_store: "Buy and store",
  use_storage_and_buy: "Use storage and buy",
  use_storage: "Use storage",
};
const OPTION_SHORT: Record<Option, string> = {
  buy: "Buy",
  buy_and_store: "Buy + store",
  use_storage_and_buy: "Use + buy",
  use_storage: "Use storage",
};

const GUTTER = 148; // room for the strip names on the left
const RIGHT = 20;
const STRIPS = { axis: 26, tiles: 64, price: 118, battery: 104, level: 78, demand: 112 };
const GAP = 18;

/** Step path through hourly values: each value holds for its whole hour. */
function stepPath(values: (number | null)[], x: (i: number) => number, y: (v: number) => number) {
  let d = "";
  let pen = false;
  values.forEach((v, i) => {
    if (v == null || !isFinite(v)) {
      pen = false;
      return;
    }
    d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}L${x(i + 1).toFixed(1)},${y(v).toFixed(1)}`;
    pen = true;
  });
  return d;
}

/**
 * The day at a glance. Five strips share one time axis (the hours of the delivery day):
 * the decision per block, the price, what the battery does, how full it is, and what the city needs.
 * Forecasts are drawn in colour, what really happened in thin dark ink.
 */
export function DayRail({ plan, showActual = true, compact = false }: { plan: DayPlan; showActual?: boolean; compact?: boolean }) {
  const [ref, width] = useWidth<HTMLDivElement>(1100);
  const [hover, setHover] = useState<number | null>(null);
  const n = plan.hours.length;
  const inner = Math.max(width - GUTTER - RIGHT, 200);
  const x = (i: number) => GUTTER + (i / n) * inner;

  // where each block starts and ends, in hour positions
  const spans = useMemo(() => {
    const out: { block: number; from: number; to: number }[] = [];
    plan.hours.forEach((h, i) => {
      const last = out[out.length - 1];
      if (last && last.block === h.block) last.to = i + 1;
      else out.push({ block: h.block, from: i, to: i + 1 });
    });
    return out;
  }, [plan]);

  const tops = useMemo(() => {
    let y = 0;
    const t: Record<string, number> = {};
    (Object.keys(STRIPS) as (keyof typeof STRIPS)[]).forEach((k) => {
      if (compact && k === "demand") return;
      t[k] = y;
      y += STRIPS[k] + (k === "axis" ? 0 : GAP);
    });
    t.total = y;
    return t;
  }, [compact]);

  // --- price strip
  const priceVals = plan.hours.flatMap((h) => [h.price_fc ?? NaN, showActual ? h.price_actual : NaN]).filter(isFinite);
  const bandVals = plan.blocks.flatMap((b) => [b.price_q10 ?? NaN, b.price_q90 ?? NaN]).filter(isFinite);
  const pLo = Math.min(0, ...priceVals, ...bandVals);
  const pHi = Math.max(...priceVals, ...bandVals) * 1.05;
  const yP = scaleLinear().domain([pLo, pHi]).range([tops.price + STRIPS.price, tops.price + 16]);

  // --- battery strip (MWh per hour = MW)
  const pMax = Math.max(plan.battery.power_mw, ...plan.hours.map((h) => Math.max(h.charge_bid_mwh, h.planned_discharge_mwh)));
  const midB = tops.battery + STRIPS.battery / 2 + 6;
  const yB = scaleLinear().domain([-pMax, pMax]).range([tops.battery + STRIPS.battery, tops.battery + 12]);

  // --- charge level strip
  const cap = plan.battery.capacity_mwh;
  const yL = scaleLinear().domain([0, cap]).range([tops.level + STRIPS.level, tops.level + 12]);
  const levelActual = [plan.summary.soc_start_mwh, ...plan.hours.map((h) => h.soc_mwh)];
  const levelPath = levelActual.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${yL(v).toFixed(1)}`).join("");

  // --- demand strip
  const dVals = plan.hours.flatMap((h) => [h.demand_fc_mw, showActual ? h.demand_actual_mw : NaN]).filter(isFinite);
  const dBand = plan.blocks.flatMap((b) => [b.demand_q10_mw ?? NaN, b.demand_q90_mw ?? NaN]).filter(isFinite);
  const dLo = Math.min(...dVals, ...dBand);
  const dHi = Math.max(...dVals, ...dBand);
  const pad = (dHi - dLo) * 0.12 || 10;
  const yD = scaleLinear().domain([dLo - pad, dHi + pad]).range([(tops.demand ?? 0) + STRIPS.demand, (tops.demand ?? 0) + 14]);

  const bw = inner / n;
  const h = hover != null ? plan.hours[hover] : null;
  const readoutLeft = hover != null ? (x(hover + 0.5) > width * 0.62 ? x(hover) - 216 : x(hover + 1) + 12) : 0;

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const i = Math.floor(((e.clientX - rect.left - GUTTER) / inner) * n);
    setHover(i >= 0 && i < n ? i : null);
  };

  const stripLabel = (key: string, name: string, unit: string) => (
    <g>
      <text className="strip-name" x={0} y={tops[key] + 14}>
        {name}
      </text>
      <text className="strip-unit" x={0} y={tops[key] + 30}>
        {unit}
      </text>
    </g>
  );

  const yAxis = (ticks: number[], y: (v: number) => number, fmt: (v: number) => string = int) =>
    ticks.map((t) => (
      <g key={t}>
        <line x1={GUTTER} x2={GUTTER + inner} y1={y(t)} y2={y(t)} stroke="var(--rule-soft)" />
        <text x={GUTTER - 8} y={y(t) + 4} textAnchor="end">
          {fmt(t)}
        </text>
      </g>
    ));

  return (
    <div className="rail" ref={ref}>
      <svg
        height={tops.total}
        viewBox={`0 0 ${width} ${tops.total}`}
        role="img"
        aria-label={`Plan for ${plan.date}: decision per block, price, battery charge and discharge, charge level${compact ? "" : " and city demand"} for each hour. The same numbers are in the tables below.`}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {/* hours along the top */}
        {spans.map((s) => (
          <text key={s.block} x={x(s.from)} y={17} textAnchor={s.from === 0 ? "start" : "middle"}>
            {plan.hours[s.from].hour}
          </text>
        ))}
        <text x={x(n)} y={17} textAnchor="end">
          24:00
        </text>

        {/* block boundaries run through every strip */}
        {spans.map((s) => (
          <line key={s.block} x1={x(s.from)} x2={x(s.from)} y1={STRIPS.axis} y2={tops.total - GAP} stroke="var(--rule)" />
        ))}
        <line x1={x(n)} x2={x(n)} y1={STRIPS.axis} y2={tops.total - GAP} stroke="var(--rule)" />

        {/* 1 decision tiles */}
        {stripLabel("tiles", "Decision", "per 4-hour block")}
        {spans.map((s) => {
          const b = plan.blocks[s.block];
          const w = x(s.to) - x(s.from) - 6;
          const fill = b.charge_mwh > 0.05 ? "var(--charge-tint)" : b.discharge_mwh > 0.05 ? "var(--use-tint)" : "var(--paper)";
          const edge = b.charge_mwh > 0.05 ? "var(--charge)" : b.discharge_mwh > 0.05 ? "var(--use)" : "var(--ink-3)";
          const word = w > 132 ? OPTION_WORDS[b.option] : OPTION_SHORT[b.option];
          const fig =
            b.charge_mwh > 0.05 ? `store ${dec1(b.charge_mwh)} MWh` : b.discharge_mwh > 0.05 ? `use ${dec1(b.discharge_mwh)} MWh` : `${int(b.buy_mwh)} MWh`;
          return (
            <g key={s.block}>
              <rect x={x(s.from) + 3} y={tops.tiles + 4} width={w} height={STRIPS.tiles - 8} rx={7} fill={fill} />
              <rect x={x(s.from) + 3} y={tops.tiles + 4} width={5} height={STRIPS.tiles - 8} rx={2.5} fill={edge} />
              <text className="tile-word" x={x(s.from) + 17} y={tops.tiles + 28}>
                {word}
              </text>
              <text className="tile-fig" x={x(s.from) + 17} y={tops.tiles + 46}>
                {fig}
              </text>
            </g>
          );
        })}

        {/* 2 price */}
        {stripLabel("price", "Price", "EUR per MWh")}
        {yAxis(niceTicks(pLo, pHi, 3), yP)}
        {spans.map((s) => {
          const b = plan.blocks[s.block];
          if (b.price_q10 == null || b.price_q90 == null) return null;
          return (
            <rect key={s.block} x={x(s.from)} width={x(s.to) - x(s.from)} y={yP(b.price_q90)} height={Math.max(yP(b.price_q10) - yP(b.price_q90), 0)} fill="var(--price-tint)" />
          );
        })}
        <path d={stepPath(plan.hours.map((r) => r.price_fc), x, yP)} fill="none" stroke="var(--price)" strokeWidth={2.25} strokeLinejoin="round" />
        {showActual && <path d={stepPath(plan.hours.map((r) => r.price_actual), x, yP)} fill="none" stroke="var(--ink)" strokeWidth={1.25} />}

        {/* 3 battery */}
        {stripLabel("battery", "Battery", "MWh in each hour")}
        <text x={GUTTER - 8} y={yB(pMax) + 4} textAnchor="end">
          {`store ${int(pMax)}`}
        </text>
        <text x={GUTTER - 8} y={yB(-pMax) + 4} textAnchor="end">
          {`use ${int(pMax)}`}
        </text>
        <line x1={GUTTER} x2={GUTTER + inner} y1={yB(0)} y2={yB(0)} stroke="var(--ink-3)" />
        {plan.hours.map((r, i) => {
          const g = 2;
          const cleared = showActual ? r.charge_actual_mwh : r.charge_bid_mwh;
          const used = showActual ? r.discharge_actual_mwh : r.planned_discharge_mwh;
          return (
            <g key={r.utc}>
              {r.charge_bid_mwh - cleared > 0.05 && (
                <rect x={x(i) + g} width={bw - 2 * g} y={yB(r.charge_bid_mwh)} height={yB(0) - yB(r.charge_bid_mwh)} fill="none" stroke="var(--charge)" strokeDasharray="3 3" rx={3} />
              )}
              {cleared > 0.01 && <rect x={x(i) + g} width={bw - 2 * g} y={yB(cleared)} height={yB(0) - yB(cleared)} fill="var(--charge)" rx={3} />}
              {r.planned_discharge_mwh - used > 0.05 && (
                <rect x={x(i) + g} width={bw - 2 * g} y={yB(0)} height={yB(-r.planned_discharge_mwh) - yB(0)} fill="none" stroke="var(--use)" strokeDasharray="3 3" rx={3} />
              )}
              {used > 0.01 && <rect x={x(i) + g} width={bw - 2 * g} y={yB(0)} height={yB(-used) - yB(0)} fill="var(--use)" rx={3} />}
            </g>
          );
        })}

        {/* 4 charge level */}
        {stripLabel("level", "Charge level", "MWh in the battery")}
        {[plan.battery.soc_min_frac * cap, plan.battery.soc_max_frac * cap].map((v) => (
          <g key={v}>
            <line x1={GUTTER} x2={GUTTER + inner} y1={yL(v)} y2={yL(v)} stroke="var(--ink-3)" strokeDasharray="2 4" />
            <text x={GUTTER - 8} y={yL(v) + 4} textAnchor="end">
              {int(v)}
            </text>
          </g>
        ))}
        <path key={`${plan.date}-${plan.battery.capacity_mwh}-${plan.battery.power_mw}`} className="draw-once" pathLength={1} d={levelPath} fill="none" stroke="var(--ink)" strokeWidth={2.25} strokeLinejoin="round" />

        {/* 5 demand */}
        {!compact && (
          <g>
            {stripLabel("demand", "City demand", "MW")}
            {yAxis(niceTicks(dLo - pad, dHi + pad, 3), yD)}
            {spans.map((s) => {
              const b = plan.blocks[s.block];
              if (b.demand_q10_mw == null || b.demand_q90_mw == null) return null;
              return (
                <rect key={s.block} x={x(s.from)} width={x(s.to) - x(s.from)} y={yD(b.demand_q90_mw)} height={Math.max(yD(b.demand_q10_mw) - yD(b.demand_q90_mw), 0)} fill="var(--rule-soft)" />
              );
            })}
            <path d={stepPath(plan.hours.map((r) => r.demand_fc_mw), x, yD)} fill="none" stroke="var(--demand)" strokeWidth={2.25} strokeLinejoin="round" />
            {showActual && <path d={stepPath(plan.hours.map((r) => r.demand_actual_mw), x, yD)} fill="none" stroke="var(--ink)" strokeWidth={1.25} />}
          </g>
        )}

        {hover != null && <rect x={x(hover)} width={bw} y={STRIPS.axis} height={tops.total - STRIPS.axis - GAP} fill="var(--ink)" opacity={0.07} />}
      </svg>

      {h && (
        <div className="rail-readout" style={{ left: readoutLeft }}>
          <h4>
            {h.hour} to {plan.hours[hover! + 1]?.hour ?? "24:00"}
          </h4>
          <dl>
            <dt>Price forecast</dt>
            <dd>{h.price_fc == null ? "–" : dec1(h.price_fc)}</dd>
            {showActual && (
              <>
                <dt>Price, actual</dt>
                <dd>{dec1(h.price_actual)}</dd>
              </>
            )}
            <dt>Demand forecast</dt>
            <dd>{dec1(h.demand_fc_mw)} MW</dd>
            {showActual && (
              <>
                <dt>Demand, actual</dt>
                <dd>{dec1(h.demand_actual_mw)} MW</dd>
              </>
            )}
            <dt>Bid for the city</dt>
            <dd>{dec1(h.demand_bid_mwh)} MWh</dd>
            {h.charge_bid_mwh > 0.01 && (
              <>
                <dt>Bid to store</dt>
                <dd>
                  {dec1(h.charge_bid_mwh)} MWh{h.charge_limit_eur_mwh != null ? ` up to ${dec1(h.charge_limit_eur_mwh)}` : ""}
                </dd>
                {showActual && (
                  <>
                    <dt>Stored</dt>
                    <dd>{dec1(h.charge_actual_mwh)} MWh</dd>
                  </>
                )}
              </>
            )}
            {h.planned_discharge_mwh > 0.01 && (
              <>
                <dt>Used from battery</dt>
                <dd>{dec1(showActual ? h.discharge_actual_mwh : h.planned_discharge_mwh)} MWh</dd>
              </>
            )}
            <dt>Charge level</dt>
            <dd>{dec1(h.soc_mwh)} MWh</dd>
          </dl>
        </div>
      )}
    </div>
  );
}

export function RailLegend({ showActual, compact = false }: { showActual: boolean; compact?: boolean }) {
  return (
    <div className="legend" aria-hidden="true">
      <span>
        <i className="swatch line" style={{ color: "var(--price)" }} /> Price forecast
      </span>
      {!compact && (
        <span>
          <i className="swatch line" style={{ color: "var(--demand)" }} /> Demand forecast
        </span>
      )}
      <span>
        <i className="swatch" style={{ background: "var(--price-tint)" }} /> Likely range (8 in 10 days)
      </span>
      {showActual && (
        <span>
          <i className="swatch line thin" style={{ color: "var(--ink)" }} /> What really happened
        </span>
      )}
      <span>
        <i className="swatch" style={{ background: "var(--charge)" }} /> Stored
      </span>
      <span>
        <i className="swatch" style={{ background: "var(--use)" }} /> Used
      </span>
      <span>
        <i className="swatch outline" /> Planned, but did not happen
      </span>
    </div>
  );
}

export { OPTION_WORDS };
