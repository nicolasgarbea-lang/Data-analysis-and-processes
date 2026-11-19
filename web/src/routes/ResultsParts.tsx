// The detail behind the Results page. Each piece sits in a closed section.
import { useMemo, useState } from "react";
import { createColumnHelper, flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type SortingState } from "@tanstack/react-table";
import type { Backtest, Drivers, ModelInfo, StrategyRow } from "../data/types";
import { ChartLegend, HBars, Heatmap, LineChart, StackedColumns } from "../charts/Charts";
import { chf, dec1, dec2, int, pct } from "../lib/format";

export const k = (v: number) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}m` : Math.abs(v) >= 1000 ? `${Math.round(v / 1000)}k` : int(v));

const col = createColumnHelper<StrategyRow>();

export function StrategyTable({ rows }: { rows: StrategyRow[] }) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const columns = useMemo(
    () => [
      col.accessor("name", {
        header: "Strategy",
        cell: (c) => (
          <>
            {c.getValue()}
            <span className="sub">{c.row.original.note}</span>
          </>
        ),
      }),
      col.accessor("saving_vs_baseline_chf", { header: "Saved", cell: (c) => chf(c.getValue()), meta: { right: true } }),
      col.accessor("imbalance_penalty_chf", { header: "Penalties paid", cell: (c) => chf(c.getValue()), meta: { right: true } }),
      col.accessor((r) => r.pct_of_ceiling ?? -Infinity, { id: "pct", header: "Share of best possible", cell: (c) => pct(c.row.original.pct_of_ceiling), meta: { right: true } }),
    ],
    [],
  );
  const table = useReactTable({ data: rows, columns, state: { sorting }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });
  return (
    <div className="table-scroll">
      <table className="data">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => {
                const right = (h.column.columnDef.meta as { right?: boolean } | undefined)?.right;
                const dir = h.column.getIsSorted();
                return (
                  <th key={h.id} className={right ? "r" : undefined} aria-sort={dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none"}>
                    <button type="button" onClick={h.column.getToggleSortingHandler()} title="Sort">
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {dir === "asc" ? " ↑" : dir === "desc" ? " ↓" : ""}
                    </button>
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((r) => (
            <tr key={r.id} className={r.original.kind === "product" ? "is-product" : undefined}>
              {r.getVisibleCells().map((c) => {
                const right = (c.column.columnDef.meta as { right?: boolean } | undefined)?.right;
                return (
                  <td key={c.id} className={right ? "r" : undefined}>
                    {flexRender(c.column.columnDef.cell, c.getContext())}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">October 2026, CHF. Same days, real prices and real demand for every strategy; only the forecasts and the use of the battery differ.</p>
    </div>
  );
}

export function Sensitivities({ bt }: { bt: Backtest }) {
  const pe = bt.price_error;
  const pts = [...pe.points].sort((a, b) => a.mae_eur_mwh - b.mae_eur_mwh);
  return (
    <div className="three-col">
      <div>
        <h3>The assumed penalty</h3>
        <p className="note">Penalty for buying the wrong amount, as a share of the price.</p>
        <StackedColumns
          height={220}
          labels={bt.imbalance.map((r) => `${Math.round((r.shortage_factor - 1) * 100)} %`)}
          xTickEvery={1}
          parts={[
            { key: "d", name: "Demand forecast", color: "var(--ink-2)", values: bt.imbalance.map((r) => r.demand_part_chf) },
            { key: "b", name: "Battery", color: "var(--charge)", values: bt.imbalance.map((r) => r.battery_part_chf) },
          ]}
          yFormat={k}
          yTitle="CHF saved in October"
          ariaLabel="October saving for three assumed penalties"
        />
        <ChartLegend
          items={[
            { name: "Demand forecast", color: "var(--ink-2)", kind: "fill" },
            { name: "Battery", color: "var(--charge)", kind: "fill" },
          ]}
        />
      </div>
      <div>
        <h3>The size of the battery</h3>
        <p className="note">Each battery holds two hours at full power.</p>
        <LineChart
          height={220}
          labels={bt.battery_size.map((r) => `${r.power_mw} MW`)}
          xTicks={bt.battery_size.map((_, i) => i)}
          series={[
            { key: "c", name: "Best possible", values: bt.battery_size.map((r) => r.ceiling_battery_value_chf), color: "var(--ink-3)", dash: "5 4", width: 1.5 },
            { key: "m", name: "Our plan", values: bt.battery_size.map((r) => r.ml_battery_value_chf), color: "var(--charge)", width: 2.5 },
          ]}
          marker
          zero
          yFormat={k}
          yTitle="CHF saved by the battery"
          directLabels={false}
          ariaLabel="Battery saving in October by battery size"
        />
        <ChartLegend
          items={[
            { name: "Our plan", color: "var(--charge)" },
            { name: "Best possible", color: "var(--ink-3)", kind: "thin" },
          ]}
        />
      </div>
      <div>
        <h3>A worse price forecast</h3>
        <p className="note">Random error added to the true prices, then planned with them.</p>
        <LineChart
          height={220}
          labels={pts.map((p) => `${dec1(p.mae_eur_mwh)} EUR/MWh error`)}
          xTicks={[0, Math.floor((pts.length - 1) / 2), pts.length - 1]}
          xTickFormat={(_, i) => dec1(pts[i].mae_eur_mwh)}
          series={[{ key: "l", name: "Lost saving", values: pts.map((p) => p.lost_chf), color: "var(--price)", width: 2.5 }]}
          marker
          zero
          yFormat={k}
          yTitle="CHF of battery saving lost"
          directLabels={false}
          ariaLabel="Battery saving lost in October by size of price error"
        />
        <p className="note">About {chf(pe.slope_chf_per_eur)} lost per month for each EUR/MWh of price error.</p>
      </div>
    </div>
  );
}

export function Ladder({ m }: { m: ModelInfo }) {
  return (
    <div className="table-scroll">
      <table className="data">
        <caption>
          <h3>{m.target === "demand" ? "Demand" : "Price"}, average miss in {m.unit}</h3>
        </caption>
        <thead>
          <tr>
            <th>Model</th>
            <th className="r">September</th>
            <th className="r">October</th>
          </tr>
        </thead>
        <tbody>
          {m.ladder.map((r) => (
            <tr key={r.model} className={r.model === "best" ? "is-product" : undefined}>
              <td>{r.name}</td>
              <td className="r">{dec2(r.val_mae)}</td>
              <td className="r">{dec2(r.test_mae)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const PROFILE_COLORS = ["var(--ink)", "var(--charge)", "var(--use)", "var(--price)"];

export function Patterns({ d }: { d: Drivers }) {
  const temp = d.temp_demand.filter((b) => [0, 2, 4].includes(b.block));
  return (
    <>
      <div className="three-col">
        <div>
          <h3>Cold days need more power</h3>
          <LineChart
            height={220}
            labels={temp[0]?.points.map((p) => `${p.temp_c} °C`) ?? []}
            xTicks={(temp[0]?.points ?? []).map((p, i) => (p.temp_c % 8 === 0 ? i : -1)).filter((i) => i >= 0)}
            xTickFormat={(l) => l.replace(" °C", "°")}
            series={temp.map((b, i) => ({ key: b.label, name: b.label, values: b.points.map((p) => p.demand_mw), color: ["var(--ink-3)", "var(--demand)", "var(--use)"][i], width: 2 }))}
            yTitle="MW on working days, by outside temperature"
            ariaLabel="Demand by outside temperature"
          />
        </div>
        <div>
          <h3>Holidays look like Sundays</h3>
          <LineChart
            height={220}
            labels={d.profile[0]?.hours.map((h) => `${String(h).padStart(2, "0")}:00`) ?? []}
            xTicks={[0, 6, 12, 18, 23]}
            series={d.profile.map((p, i) => ({ key: p.daytype, name: p.daytype, values: p.demand_mw, color: PROFILE_COLORS[i], width: i === 0 ? 2.5 : 1.75 }))}
            yTitle="MW, average day"
            directLabels={false}
            ariaLabel="Average hourly demand by type of day"
          />
          <ChartLegend items={d.profile.map((p, i) => ({ name: p.daytype, color: PROFILE_COLORS[i] }))} />
        </div>
        <div>
          <h3>Electric cars: no visible effect yet</h3>
          <LineChart
            height={220}
            labels={d.ev.map((p) => String(p.year))}
            series={[{ key: "n", name: "Night demand", values: d.ev.map((p) => p.night_demand_mw), color: "var(--ink)", width: 2.5 }]}
            marker
            zero
            directLabels={false}
            yTitle="MW at 00–04, yearly average"
            ariaLabel="Night demand by year"
          />
          <p className="note">
            {int(d.ev[0]?.ev_count)} electric cars in {d.ev[0]?.year}, {int(d.ev[d.ev.length - 1]?.ev_count)} in {d.ev[d.ev.length - 1]?.year}. Night demand did not follow.
          </p>
        </div>
      </div>
      <div className="three-col" style={{ marginTop: "2.5rem" }}>
        <div>
          <h3>The price is lowest at midday in summer</h3>
          <Heatmap rows={d.price_heatmap.months} cols={d.price_heatmap.blocks} values={d.price_heatmap.values} ariaLabel="Mean price by month and block" />
          <p className="note">Mean price in EUR/MWh, darker is dearer. This daily swing is what the battery earns from.</p>
        </div>
        <div>
          <h3>Wind in Germany pushes it down</h3>
          <HBars
            ariaLabel="Swiss price against its recent average by German wind forecast"
            format={(v) => `${v > 0 ? "+" : "−"}${dec1(Math.abs(v))}`}
            labelWidth={110}
            rows={d.wind_price.map((r) => ({ label: r.wind_bin, value: r.price_vs_recent_eur, color: r.price_vs_recent_eur >= 0 ? "var(--price)" : "var(--charge)" }))}
          />
          <p className="note">Price against its average of the past four weeks, EUR/MWh, by forecast wind speed in northern Germany.</p>
        </div>
        <div>
          <h3>Gas sets the level</h3>
          <LineChart
            height={220}
            labels={d.gas_price.map((p) => p.month)}
            xTicks={d.gas_price.map((p, i) => (p.month.endsWith("-01") && Number(p.month.slice(0, 4)) % 2 === 1 ? i : -1)).filter((i) => i >= 0)}
            xTickFormat={(l) => l.slice(0, 4)}
            series={[
              { key: "p", name: "Power", values: d.gas_price.map((p) => p.price_eur_mwh), color: "var(--price)", width: 2 },
              { key: "g", name: "Gas", values: d.gas_price.map((p) => p.gas_eur_mwh), color: "var(--use)", width: 2 },
            ]}
            directLabels={false}
            yTitle="EUR per MWh, monthly average"
            ariaLabel="Monthly Swiss power price and gas price"
          />
          <ChartLegend
            items={[
              { name: "Swiss power", color: "var(--price)" },
              { name: "Gas", color: "var(--use)" },
            ]}
          />
        </div>
      </div>
    </>
  );
}
