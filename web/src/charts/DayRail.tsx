import { useMemo, useState } from "react";
import { scaleLinear } from "d3-scale";
import type { DayPlan, Option } from "../data/types";
import { dec1, int } from "../lib/format";
import { niceTicks, useWidth } from "./base";

export const OPTION_WORDS: Record<Option, string> = {
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

type Strip = "tiles" | "price" | "battery";
const HEIGHT: Record<Strip | "axis", number> = { axis: 24, tiles: 54, price: 100, battery: 84 };
const GUTTER = 120;
const RIGHT = 16;
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
 * The day at a glance. Three strips share one time axis (the hours of the delivery day):
 * the decision per block, the price, and what the battery does each hour.
 * Forecasts are drawn in colour, what really happened in thin dark ink.
 */
export function DayRail({ plan, showActual = true }: { plan: DayPlan; showActual?: boolean }) {
  const [ref, width] = useWidth<HTMLDivElement>(1100);
  const [hover, setHover] = useState<number | null>(null);
  const n = plan.hours.length;
  const inner = Math.max(width - GUTTER - RIGHT, 200);
  const x = (i: number) => GUTTER + (i / n) * inner;
  const bw = inner / n;

  const spans = useMemo(() => {
    const out: { block: number; from: number; to: number }[] = [];
    plan.hours.forEach((h, i) => {
      const last = out[out.length - 1];
      if (last && last.block === h.block) last.to = i + 1;
      else out.push({ block: h.block, from: i, to: i + 1 });
    });
    return out;
  }, [plan]);

  const top = { tiles: HEIGHT.axis, price: HEIGHT.axis + HEIGHT.tiles + GAP, battery: HEIGHT.axis + HEIGHT.tiles + HEIGHT.price + 2 * GAP };
  const total = top.battery + HEIGHT.battery + 6;

  // price
  const priceVals = plan.hours.flatMap((h) => [h.price_fc ?? NaN, showActual ? h.price_actual : NaN]).filter(isFinite);
  const bandVals = plan.blocks.flatMap((b) => [b.price_q10 ?? NaN, b.price_q90 ?? NaN]).filter(isFinite);
  const pLo = Math.min(0, ...priceVals, ...bandVals);
  const pHi = Math.max(...priceVals, ...bandVals) * 1.05;
  const yP = scaleLinear().domain([pLo, pHi]).range([top.price + HEIGHT.price, top.price + 14]);

  // battery: energy in each hour, stored above the line, used below
  const pMax = Math.max(plan.battery.power_mw, ...plan.hours.map((h) => Math.max(h.charge_bid_mwh, h.planned_discharge_mwh)));
  const yB = scaleLinear().domain([-pMax, pMax]).range([top.battery + HEIGHT.battery, top.battery + 8]);

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const i = Math.floor(((e.clientX - rect.left - GUTTER) / inner) * n);
    setHover(i >= 0 && i < n ? i : null);
  };
  const h = hover != null ? plan.hours[hover] : null;
  const readoutLeft = hover != null ? (x(hover + 0.5) > width * 0.62 ? x(hover) - 212 : x(hover + 1) + 12) : 0;

  const label = (y: number, name: string, unit: string) => (
    <g>
      <text className="strip-name" x={0} y={y + 14}>
        {name}
      </text>
      <text className="strip-unit" x={0} y={y + 30}>
        {unit}
      </text>
    </g>
  );

  return (
    <div className="rail" ref={ref}>
      <svg
        height={total}
        viewBox={`0 0 ${width} ${total}`}
        role="img"
        aria-label={`Plan for ${plan.date}: the decision for each 4-hour block, the price and what the battery does in each hour.`}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {spans.map((s) => (
          <text key={s.block} x={x(s.from)} y={17} textAnchor={s.from === 0 ? "start" : "middle"}>
            {plan.hours[s.from].hour}
          </text>
        ))}
        <text x={x(n)} y={17} textAnchor="end">
          24:00
        </text>
        {[...spans.map((s) => s.from), n].map((i) => (
          <line key={i} x1={x(i)} x2={x(i)} y1={HEIGHT.axis} y2={total - 6} stroke="var(--rule)" />
        ))}

        {/* decision per block */}
        {label(top.tiles, "Decision", "per block")}
        {spans.map((s) => {
          const b = plan.blocks[s.block];
          const w = x(s.to) - x(s.from) - 6;
          const charging = b.charge_mwh > 0.05;
          const using = b.discharge_mwh > 0.05;
          const fill = charging ? "var(--charge-tint)" : using ? "var(--use-tint)" : "var(--paper)";
          const edge = charging ? "var(--charge)" : using ? "var(--use)" : "var(--ink-3)";
          const fig = charging ? `store ${dec1(b.charge_mwh)} MWh` : using ? `use ${dec1(b.discharge_mwh)} MWh` : `${int(b.buy_mwh)} MWh`;
          return (
            <g key={s.block}>
              <rect x={x(s.from) + 3} y={top.tiles + 4} width={w} height={HEIGHT.tiles - 8} rx={7} fill={fill} />
              <rect x={x(s.from) + 3} y={top.tiles + 4} width={5} height={HEIGHT.tiles - 8} rx={2.5} fill={edge} />
              <text className="tile-word" x={x(s.from) + 17} y={top.tiles + 28}>
                {w > 132 ? OPTION_WORDS[b.option] : OPTION_SHORT[b.option]}
              </text>
              <text className="tile-fig" x={x(s.from) + 17} y={top.tiles + 46}>
                {fig}
              </text>
            </g>
          );
        })}

        {/* price */}
        {label(top.price, "Price", "EUR per MWh")}
        {niceTicks(pLo, pHi, 3).map((t) => (
          <g key={t}>
            <line x1={GUTTER} x2={GUTTER + inner} y1={yP(t)} y2={yP(t)} stroke="var(--rule-soft)" />
            <text x={GUTTER - 8} y={yP(t) + 4} textAnchor="end">
              {int(t)}
            </text>
          </g>
        ))}
        {spans.map((s) => {
          const b = plan.blocks[s.block];
          if (b.price_q10 == null || b.price_q90 == null) return null;
          return <rect key={s.block} x={x(s.from)} width={x(s.to) - x(s.from)} y={yP(b.price_q90)} height={Math.max(yP(b.price_q10) - yP(b.price_q90), 0)} fill="var(--price-tint)" />;
        })}
        <path d={stepPath(plan.hours.map((r) => r.price_fc), x, yP)} fill="none" stroke="var(--price)" strokeWidth={2.25} strokeLinejoin="round" />
        {showActual && <path d={stepPath(plan.hours.map((r) => r.price_actual), x, yP)} fill="none" stroke="var(--ink)" strokeWidth={1.25} />}

        {/* battery */}
        {label(top.battery, "Battery", "MWh per hour")}
        <text x={GUTTER - 8} y={yB(pMax / 2) + 4} textAnchor="end">
          store
        </text>
        <text x={GUTTER - 8} y={yB(-pMax / 2) + 4} textAnchor="end">
          use
        </text>
        <line x1={GUTTER} x2={GUTTER + inner} y1={yB(0)} y2={yB(0)} stroke="var(--ink-3)" />
        {plan.hours.map((r, i) => {
          const g = 2;
          const stored = showActual ? r.charge_actual_mwh : r.charge_bid_mwh;
          const used = showActual ? r.discharge_actual_mwh : r.planned_discharge_mwh;
          return (
            <g key={r.utc}>
              {r.charge_bid_mwh - stored > 0.05 && (
                <rect x={x(i) + g} width={bw - 2 * g} y={yB(r.charge_bid_mwh)} height={yB(0) - yB(r.charge_bid_mwh)} fill="none" stroke="var(--charge)" strokeDasharray="3 3" rx={3} />
              )}
              {stored > 0.01 && <rect x={x(i) + g} width={bw - 2 * g} y={yB(stored)} height={yB(0) - yB(stored)} fill="var(--charge)" rx={3} />}
              {r.planned_discharge_mwh - used > 0.05 && (
                <rect x={x(i) + g} width={bw - 2 * g} y={yB(0)} height={yB(-r.planned_discharge_mwh) - yB(0)} fill="none" stroke="var(--use)" strokeDasharray="3 3" rx={3} />
              )}
              {used > 0.01 && <rect x={x(i) + g} width={bw - 2 * g} y={yB(0)} height={yB(-used) - yB(0)} fill="var(--use)" rx={3} />}
            </g>
          );
        })}

        {hover != null && <rect x={x(hover)} width={bw} y={HEIGHT.axis} height={total - HEIGHT.axis - 6} fill="var(--ink)" opacity={0.07} />}
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
                <dt>Actual price</dt>
                <dd>{dec1(h.price_actual)}</dd>
              </>
            )}
            <dt>Bought for the city</dt>
            <dd>{dec1(h.demand_bid_mwh)} MWh</dd>
            {h.charge_bid_mwh > 0.01 && (
              <>
                <dt>Stored</dt>
                <dd>{dec1(showActual ? h.charge_actual_mwh : h.charge_bid_mwh)} MWh</dd>
              </>
            )}
            {h.planned_discharge_mwh > 0.01 && (
              <>
                <dt>Used from battery</dt>
                <dd>{dec1(showActual ? h.discharge_actual_mwh : h.planned_discharge_mwh)} MWh</dd>
              </>
            )}
            <dt>In the battery after</dt>
            <dd>{dec1(h.soc_mwh)} MWh</dd>
          </dl>
        </div>
      )}
    </div>
  );
}

export function RailLegend({ showActual }: { showActual: boolean }) {
  return (
    <div className="legend" aria-hidden="true">
      <span>
        <i className="swatch line" style={{ color: "var(--price)" }} /> Price forecast
      </span>
      <span>
        <i className="swatch" style={{ background: "var(--price-tint)" }} /> Likely price range
      </span>
      {showActual && (
        <span>
          <i className="swatch line thin" style={{ color: "var(--ink)" }} /> Actual price
        </span>
      )}
      <span>
        <i className="swatch" style={{ background: "var(--charge)" }} /> Stored
      </span>
      <span>
        <i className="swatch" style={{ background: "var(--use)" }} /> Used
      </span>
      {showActual && (
        <span>
          <i className="swatch outline" /> Planned, did not happen
        </span>
      )}
    </div>
  );
}
