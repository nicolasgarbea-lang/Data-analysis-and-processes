import { useState, type ReactNode } from "react";
import { scaleBand, scaleLinear } from "d3-scale";
import { line as d3line } from "d3-shape";
import { niceTicks, Tip, useWidth, type TipState } from "./base";
import { int } from "../lib/format";

export interface Series {
  key: string;
  name: string;
  values: (number | null)[];
  color: string;
  width?: number;
  dash?: string;
}

interface LineChartProps {
  labels: string[]; // one per x position
  series: Series[];
  height?: number;
  yTitle?: string;
  xTicks?: number[]; // positions to label
  xTickFormat?: (label: string, i: number) => string;
  yFormat?: (v: number) => string;
  band?: { lo: (number | null)[]; hi: (number | null)[]; color: string };
  zero?: boolean; // include zero in the y domain
  directLabels?: boolean;
  ariaLabel: string;
  marker?: boolean;
}

/** Index ranges [from, to) where both band edges are known; the band is drawn only there. */
function bandRuns(band: { lo: (number | null)[]; hi: (number | null)[] }): [number, number][] {
  const ok = (i: number) => band.lo[i] != null && band.hi[i] != null && isFinite(band.lo[i] as number) && isFinite(band.hi[i] as number);
  const runs: [number, number][] = [];
  const n = Math.min(band.lo.length, band.hi.length);
  for (let i = 0; i < n; i++) {
    if (!ok(i)) continue;
    let j = i;
    while (j < n && ok(j)) j++;
    runs.push([i, j]);
    i = j;
  }
  return runs;
}

/** Lines over an ordered x axis, with a crosshair that reads every series at once. */
export function LineChart({ labels, series, height = 280, yTitle, xTicks, xTickFormat, yFormat = int, band, zero = false, directLabels = true, ariaLabel, marker = false }: LineChartProps) {
  const [ref, width] = useWidth<HTMLDivElement>(700);
  const [hover, setHover] = useState<number | null>(null);
  const m = { top: 18, right: directLabels ? 150 : 16, bottom: 28, left: 56 };
  const n = labels.length;
  const all = series.flatMap((s) => s.values).concat(band ? [...band.lo, ...band.hi] : []).filter((v): v is number => v != null && isFinite(v));
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (zero) {
    lo = Math.min(lo, 0);
    hi = Math.max(hi, 0);
  }
  const padY = (hi - lo) * 0.06 || 1;
  const x = scaleLinear().domain([0, Math.max(n - 1, 1)]).range([m.left, width - m.right]);
  const y = scaleLinear().domain([lo - (zero && lo === 0 ? 0 : padY), hi + padY]).range([height - m.bottom, m.top]);
  const path = d3line<number | null>()
    .defined((v) => v != null && isFinite(v))
    .x((_, i) => x(i))
    .y((v) => y(v as number));
  const ticks = niceTicks(y.domain()[0], y.domain()[1], 4);
  const xt = xTicks ?? Array.from({ length: Math.min(n, 7) }, (_, k) => Math.round((k * (n - 1)) / Math.max(Math.min(n, 7) - 1, 1)));

  // direct labels at the line ends, nudged apart so they never overlap
  const ends = series
    .map((s) => {
      let i = s.values.length - 1;
      while (i > 0 && (s.values[i] == null || !isFinite(s.values[i] as number))) i--;
      return { s, y: y(s.values[i] as number) };
    })
    .sort((a, b) => a.y - b.y);
  for (let k = 1; k < ends.length; k++) if (ends[k].y - ends[k - 1].y < 15) ends[k].y = ends[k - 1].y + 15;

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const i = Math.round(x.invert(e.clientX - rect.left));
    setHover(i >= 0 && i < n ? i : null);
  };
  const tip: TipState | null =
    hover == null
      ? null
      : {
          x: Math.min(Math.max(x(hover), 90), width - 90),
          y: m.top + 8,
          title: labels[hover],
          rows: series.filter((s) => s.values[hover] != null).map((s) => [s.name, yFormat(s.values[hover] as number)]),
        };

  return (
    <div className="chart" ref={ref}>
      <svg height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {yTitle && (
          <text className="axis-title" x={0} y={10}>
            {yTitle}
          </text>
        )}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.left} x2={width - m.right} y1={y(t)} y2={y(t)} stroke={t === 0 ? "var(--ink-3)" : "var(--rule-soft)"} />
            <text x={m.left - 8} y={y(t) + 4} textAnchor="end">
              {yFormat(t)}
            </text>
          </g>
        ))}
        {xt.map((i) => (
          <text key={i} x={x(i)} y={height - 8} textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"}>
            {xTickFormat ? xTickFormat(labels[i], i) : labels[i]}
          </text>
        ))}
        {band &&
          bandRuns(band).map(([from, to]) => (
            <path
              key={from}
              d={
                band.hi
                  .slice(from, to)
                  .map((v, k) => `${k ? "L" : "M"}${x(from + k)},${y(v as number)}`)
                  .join("") +
                band.lo
                  .slice(from, to)
                  .map((v, k) => [from + k, v as number] as const)
                  .reverse()
                  .map(([i, v]) => `L${x(i)},${y(v)}`)
                  .join("") +
                "Z"
              }
              fill={band.color}
            />
          ))}
        {series.map((s) => (
          <g key={s.key}>
            <path d={path(s.values) ?? ""} fill="none" stroke={s.color} strokeWidth={s.width ?? 2} strokeDasharray={s.dash} strokeLinejoin="round" strokeLinecap="round" />
            {marker && s.values.map((v, i) => (v == null ? null : <circle key={i} cx={x(i)} cy={y(v)} r={4} fill={s.color} stroke="var(--surface)" strokeWidth={2} />))}
          </g>
        ))}
        {directLabels &&
          ends.map(({ s, y: ly }) => (
            <g key={s.key}>
              <line x1={width - m.right + 4} x2={width - m.right + 14} y1={ly} y2={ly} stroke={s.color} strokeWidth={s.width ?? 2} strokeDasharray={s.dash} />
              <text className="direct" x={width - m.right + 19} y={ly + 4}>
                {s.name}
              </text>
            </g>
          ))}
        {hover != null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={m.top} y2={height - m.bottom} stroke="var(--ink-3)" />
            {series.map((s) => (s.values[hover] == null ? null : <circle key={s.key} cx={x(hover)} cy={y(s.values[hover] as number)} r={4.5} fill={s.color} stroke="var(--surface)" strokeWidth={2} />))}
          </g>
        )}
      </svg>
      <Tip tip={tip} />
    </div>
  );
}

interface HBarProps {
  rows: { label: string; value: number; color?: string; note?: string; lo?: number; hi?: number; strong?: boolean }[];
  format?: (v: number) => string;
  labelWidth?: number;
  ariaLabel: string;
  max?: number;
  stacked?: boolean; // write each label on its own line above its bar (for long labels)
}

/** Horizontal bars with the value written at the end of each bar. Optional range whisker. */
export function HBars({ rows, format = int, labelWidth = 190, ariaLabel, max, stacked = false }: HBarProps) {
  const [ref, width] = useWidth<HTMLDivElement>(520);
  const rowH = stacked ? 44 : 30;
  const barH = stacked ? 14 : 18;
  const barTop = stacked ? 21 : 5;
  const lw = stacked ? 0 : Math.min(labelWidth, width * 0.45);
  const lo = Math.min(0, ...rows.map((r) => r.value));
  const hi = max ?? Math.max(0, ...rows.map((r) => Math.max(r.value, r.hi ?? r.value)));
  const x = scaleLinear().domain([lo, hi]).range([lw + (lo < 0 ? 4 : 0), width - 76]);
  const height = rows.length * rowH + 6;
  return (
    <div className="chart" ref={ref}>
      <svg height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel}>
        {rows.map((row, i) => {
          const y0 = i * rowH + barTop;
          const x0 = x(Math.min(0, row.value));
          const w = Math.max(Math.abs(x(row.value) - x(0)), 1.5);
          const end = Math.max(x(Math.max(row.value, 0)), row.hi != null ? x(row.hi) : 0);
          return (
            <g key={row.label}>
              <text className={row.strong ? "direct" : undefined} x={0} y={stacked ? i * rowH + 14 : y0 + 13}>
                {row.label}
              </text>
              <rect x={x0} y={y0} width={w} height={barH} rx={4} fill={row.color ?? "var(--ink-2)"} />
              {row.lo != null && row.hi != null && <line x1={x(row.lo)} x2={x(row.hi)} y1={y0 + barH / 2} y2={y0 + barH / 2} stroke="var(--ink)" strokeWidth={1.5} />}
              <text className={row.strong ? "direct" : undefined} x={end + 7} y={y0 + barH / 2 + 4}>
                {format(row.value)}
              </text>
            </g>
          );
        })}
        <line x1={x(0)} x2={x(0)} y1={0} y2={height} stroke="var(--ink-3)" />
      </svg>
    </div>
  );
}

interface StackedProps {
  labels: string[];
  parts: { key: string; name: string; color: string; values: number[] }[];
  height?: number;
  yFormat?: (v: number) => string;
  xTickEvery?: number;
  xTickFormat?: (label: string) => string;
  ariaLabel: string;
  yTitle?: string;
}

/** Stacked columns; positive parts stack up, negative parts stack down. */
export function StackedColumns({ labels, parts, height = 260, yFormat = int, xTickEvery = 5, xTickFormat, ariaLabel, yTitle }: StackedProps) {
  const [ref, width] = useWidth<HTMLDivElement>(700);
  const [hover, setHover] = useState<number | null>(null);
  const m = { top: 18, right: 12, bottom: 28, left: 64 };
  const n = labels.length;
  const totals = labels.map((_, i) => {
    let pos = 0;
    let neg = 0;
    parts.forEach((p) => (p.values[i] >= 0 ? (pos += p.values[i]) : (neg += p.values[i])));
    return { pos, neg };
  });
  const lo = Math.min(0, ...totals.map((t) => t.neg));
  const hi = Math.max(0, ...totals.map((t) => t.pos));
  const xb = scaleBand<number>().domain(labels.map((_, i) => i)).range([m.left, width - m.right]).paddingInner(n > 60 ? 0 : 0.18);
  const y = scaleLinear().domain([lo * 1.05, hi * 1.05]).range([height - m.bottom, m.top]);
  const ticks = niceTicks(y.domain()[0], y.domain()[1], 4);
  const tip: TipState | null =
    hover == null
      ? null
      : {
          x: Math.min(Math.max((xb(hover) ?? 0) + xb.bandwidth() / 2, 110), width - 110),
          y: m.top + 8,
          title: xTickFormat ? xTickFormat(labels[hover]) : labels[hover],
          rows: [...parts.map((p) => [p.name, yFormat(p.values[hover])] as [string, string]), ["Total", yFormat(parts.reduce((a, p) => a + p.values[hover], 0))]],
        };
  return (
    <div className="chart" ref={ref}>
      <svg
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={ariaLabel}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const i = Math.floor(((e.clientX - rect.left - m.left) / (width - m.left - m.right)) * n);
          setHover(i >= 0 && i < n ? i : null);
        }}
        onMouseLeave={() => setHover(null)}
      >
        {yTitle && (
          <text className="axis-title" x={0} y={10}>
            {yTitle}
          </text>
        )}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.left} x2={width - m.right} y1={y(t)} y2={y(t)} stroke={t === 0 ? "var(--ink-3)" : "var(--rule-soft)"} />
            <text x={m.left - 8} y={y(t) + 4} textAnchor="end">
              {yFormat(t)}
            </text>
          </g>
        ))}
        {labels.map((lab, i) => {
          let up = 0;
          let down = 0;
          return (
            <g key={lab} opacity={hover == null || hover === i ? 1 : 0.55}>
              {parts.map((p) => {
                const v = p.values[i];
                const y0 = v >= 0 ? y(up + v) : y(down);
                const h = Math.abs(y(v) - y(0));
                if (v >= 0) up += v;
                else down += v;
                return <rect key={p.key} x={xb(i)} width={Math.max(xb.bandwidth(), 1)} y={y0 + (v >= 0 && up > v ? 0 : 0)} height={Math.max(h - (n > 60 ? 0 : 1.5), 0.5)} fill={p.color} rx={n > 60 ? 0 : 2} />;
              })}
              {i % xTickEvery === 0 && (
                <text x={(xb(i) ?? 0) + xb.bandwidth() / 2} y={height - 8} textAnchor="middle">
                  {xTickFormat ? xTickFormat(lab) : lab}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <Tip tip={tip} />
    </div>
  );
}

/** A grid of cells shaded from light to dark by value (one hue). */
export function Heatmap({ rows, cols, values, format = int, ariaLabel, hue = "var(--price)" }: { rows: string[]; cols: string[]; values: number[][]; format?: (v: number) => string; ariaLabel: string; hue?: string }) {
  const [ref, width] = useWidth<HTMLDivElement>(520);
  const [hover, setHover] = useState<[number, number] | null>(null);
  const left = 62;
  const top = 22;
  const cw = (width - left) / cols.length;
  const ch = 22;
  const flat = values.flat().filter((v) => v != null && isFinite(v));
  const lo = Math.min(...flat);
  const hi = Math.max(...flat);
  const height = top + rows.length * ch;
  return (
    <div className="chart" ref={ref}>
      <svg height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel} onMouseLeave={() => setHover(null)}>
        {cols.map((c, j) => (
          <text key={c} x={left + j * cw + cw / 2} y={14} textAnchor="middle">
            {c}
          </text>
        ))}
        {rows.map((r, i) => (
          <g key={r}>
            {(i % 2 === 0 || rows.length <= 12) && (
              <text x={left - 8} y={top + i * ch + 15} textAnchor="end">
                {r}
              </text>
            )}
            {cols.map((c, j) => {
              const v = values[i]?.[j];
              const t = v == null || !isFinite(v) ? 0 : (v - lo) / (hi - lo || 1);
              return (
                <rect
                  key={c}
                  x={left + j * cw + 1}
                  y={top + i * ch + 1}
                  width={cw - 2}
                  height={ch - 2}
                  rx={2}
                  fill={v == null ? "var(--rule-soft)" : `color-mix(in oklab, ${hue} ${Math.round(8 + t * 92)}%, var(--surface))`}
                  onMouseEnter={() => setHover([i, j])}
                />
              );
            })}
          </g>
        ))}
      </svg>
      <Tip tip={hover ? { x: left + hover[1] * cw + cw / 2, y: top + hover[0] * ch, title: `${rows[hover[0]]}, ${cols[hover[1]]}`, rows: [["Mean price", `${format(values[hover[0]][hover[1]])} EUR/MWh`]] } : null} />
    </div>
  );
}

export function ChartLegend({ items }: { items: { name: string; color: string; kind?: "line" | "fill" | "thin" }[] }) {
  return (
    <div className="legend" aria-hidden="true">
      {items.map((it) => (
        <span key={it.name}>
          {it.kind === "fill" ? <i className="swatch" style={{ background: it.color }} /> : <i className={`swatch line${it.kind === "thin" ? " thin" : ""}`} style={{ color: it.color }} />}
          {it.name}
        </span>
      ))}
    </div>
  );
}

export function Block({ title, children, explain }: { title: string; explain?: ReactNode; children: ReactNode }) {
  return (
    <div>
      <h3>{title}</h3>
      {explain ? <p className="note">{explain}</p> : null}
      {children}
    </div>
  );
}
