import { useMemo, useState } from "react";
import { createColumnHelper, flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type SortingState } from "@tanstack/react-table";
import { useBacktest } from "../data/api";
import type { Backtest, BacktestSplit, StrategyRow } from "../data/types";
import { ChartLegend, HBars, LineChart, StackedColumns } from "../charts/Charts";
import { Figure } from "../charts/base";
import { chf, dec1, fmtDayMonth, int, pct } from "../lib/format";

const k = (v: number) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}m` : Math.abs(v) >= 1000 ? `${Math.round(v / 1000)}k` : int(v));
const SERIES_STYLE: Record<string, { color: string; width?: number; dash?: string }> = {
  ml_battery: { color: "var(--saving)", width: 3 },
  ml_no_battery: { color: "var(--ink-2)", width: 2 },
  perfect_foresight_battery: { color: "var(--ink-3)", width: 1.5, dash: "5 4" },
  perfect_foresight_hourly_battery: { color: "var(--ink)", width: 1.5, dash: "2 3" },
};

export function Month() {
  const bt = useBacktest();
  const [which, setWhich] = useState<BacktestSplit["split"]>("test");
  if (bt.isError) return <p className="status error">The backtest results are missing. Run “python -m src.export.export_web”, then reload.</p>;
  if (!bt.data) return <p className="status">Loading the backtest…</p>;
  const s = bt.data.splits.find((x) => x.split === which) ?? bt.data.splits[0];
  const d = s.decomposition;
  const half = bt.data.imbalance.find((r) => Math.abs(r.shortage_factor - 1.1) < 1e-6);
  const base = bt.data.imbalance.find((r) => Math.abs(r.shortage_factor - 1.2) < 1e-6);
  const where = s.split === "test" ? "In October" : s.split === "val" ? "In September" : "From October 2025 to August 2026";

  return (
    <>
      <div className="daybar">
        <div className="segmented" role="group" aria-label="Period">
          {bt.data.splits.map((x) => (
            <button key={x.split} type="button" aria-pressed={x.split === which} onClick={() => setWhich(x.split)}>
              {x.split === "test" ? "October, the test" : x.split === "val" ? "September" : "Oct 2025 to Aug 2026"}
            </button>
          ))}
        </div>
        <span className="tag">{s.out_of_sample ? "Never used for any choice" : "Used to tune the rules, so not a clean test"}</span>
      </div>

      <h1 className="statement long">
        {where} the plan saved {chf(d.total_saving_chf)}.
      </h1>
      <p className="lede">
        That is against a simple rule: buy what the city used a week ago and leave the battery off. {chf(d.demand_forecast_part_chf)} came from forecasting
        demand better, {chf(d.battery_part_chf)} from the battery.
        {s.ci && (
          <>
            {" "}
            With only {s.days} days the saving is uncertain: between {chf(s.ci.block_low)} and {chf(s.ci.block_high)} is a fair range.
          </>
        )}
      </p>
      {half && base && (
        <p className="caveat">
          <strong>Read this number with care.</strong> {pct((100 * base.demand_part_chf) / base.total_saving_chf)} of the October saving comes from avoided
          penalties for buying the wrong amount, and we had to assume how big that penalty is (20 % of the price). At half the penalty the October saving
          falls to {chf(half.total_saving_chf)}. The battery part stays at about {chf(half.battery_part_chf)}. The company and its battery are fictional.
        </p>
      )}

      <section className="section">
        <h2>Money saved, day after day</h2>
        <p>Running total against the simple rule. The dashed lines know the future, so nobody can reach them.</p>
        <Figure>
          <LineChart
            labels={s.cumulative.dates.map(fmtDayMonth)}
            series={s.cumulative.series
              .filter((x) => SERIES_STYLE[x.key])
              .map((x) => ({ key: x.key, name: shortName(x.key), values: x.values, ...SERIES_STYLE[x.key] }))}
            yFormat={(v) => `${k(v)}`}
            yTitle="CHF saved so far"
            zero
            height={340}
            ariaLabel={`Cumulative saving in CHF against the simple rule, ${s.label}.`}
          />
        </Figure>
      </section>

      <section className="section two-col even">
        <div>
          <h2 className="h2">Where the saving comes from</h2>
          <HBars
            ariaLabel="Parts of the saving in CHF"
            format={chf}
            labelWidth={210}
            rows={[
              { label: "Better demand forecast", value: d.demand_forecast_part_chf, color: "var(--ink-2)" },
              { label: "Battery, plain block plan", value: d.block_default_battery_part_chf, color: "var(--charge)" },
              { label: "Battery, hourly fine-tuning", value: d.tuning_and_shaping_part_chf, color: "var(--charge)" },
              { label: "Total", value: d.total_saving_chf, color: "var(--saving)", strong: true },
            ]}
          />
          <p className="note">
            The product reaches {pct(d.pct_ceiling_captured_total)} of the saving that perfect foresight would give. The battery alone reaches{" "}
            {pct(d.pct_ceiling_battery_value_captured)} of its best possible value of {chf(d.ceiling_battery_value_chf)}.
          </p>
        </div>
        <div>
          <h2 className="h2">Each day’s saving</h2>
          <StackedColumns
            labels={s.daily.map((x) => x.date)}
            xTickFormat={fmtDayMonth}
            xTickEvery={Math.max(1, Math.round(s.daily.length / 6))}
            parts={[
              { key: "d", name: "Demand forecast", color: "var(--ink-2)", values: s.daily.map((x) => x.demand_part_chf) },
              { key: "b", name: "Battery", color: "var(--charge)", values: s.daily.map((x) => x.battery_part_chf) },
            ]}
            yFormat={(v) => k(v)}
            yTitle="CHF per day"
            ariaLabel="Daily saving split into the demand forecast part and the battery part"
          />
          <ChartLegend
            items={[
              { name: "Demand forecast", color: "var(--ink-2)", kind: "fill" },
              { name: "Battery", color: "var(--charge)", kind: "fill" },
            ]}
          />
        </div>
      </section>

      <section className="section">
        <h2>Every strategy we compared</h2>
        <p>Same days, same real prices and demand, same settlement rules. Only the forecasts and the use of the battery differ.</p>
        <StrategyTable rows={s.strategies} />
      </section>

      <Sensitivities bt={bt.data} />
    </>
  );
}

function shortName(key: string) {
  return (
    {
      ml_battery: "Our plan",
      ml_no_battery: "Our forecast, no battery",
      perfect_foresight_battery: "Perfect foresight, blocks",
      perfect_foresight_hourly_battery: "Perfect foresight, hourly",
    }[key] ?? key
  );
}

const col = createColumnHelper<StrategyRow>();

function StrategyTable({ rows }: { rows: StrategyRow[] }) {
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
      col.accessor("total_cost_chf", { header: "Total cost", cell: (c) => chf(c.getValue()), meta: { right: true } }),
      col.accessor("saving_vs_baseline_chf", {
        header: "Saved",
        cell: (c) => (
          <>
            {chf(c.getValue())}
            {c.row.original.saving_ci_low_chf != null && c.row.original.saving_ci_high_chf != null && c.row.original.kind !== "baseline" && (
              <span className="sub">
                {int(c.row.original.saving_ci_low_chf)} to {int(c.row.original.saving_ci_high_chf)}
              </span>
            )}
          </>
        ),
        meta: { right: true },
      }),
      col.accessor("imbalance_penalty_chf", { header: "Penalties", cell: (c) => chf(c.getValue()), meta: { right: true } }),
      col.accessor("cycles", { header: "Battery cycles", cell: (c) => (c.getValue() > 0.05 ? dec1(c.getValue()) : "–"), meta: { right: true } }),
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
      <p className="note">CHF. Savings count energy left in the battery at the end. The small figures under a saving are its likely range (19 in 20), assuming days are independent.</p>
    </div>
  );
}

function Sensitivities({ bt }: { bt: Backtest }) {
  const pe = bt.price_error;
  const pts = [...pe.points].sort((a, b) => a.mae_eur_mwh - b.mae_eur_mwh);
  return (
    <section className="section">
      <h2>What the October result depends on</h2>
      <p>Three things we changed, one at a time, to see how much the result moves.</p>
      <div className="three-col" style={{ marginTop: "1.5rem" }}>
        <div>
          <h3>The assumed penalty</h3>
          <p className="note">Penalty for buying the wrong amount, as a share of the price.</p>
          <StackedColumns
            height={230}
            labels={bt.imbalance.map((r) => `${Math.round((r.shortage_factor - 1) * 100)} %`)}
            xTickEvery={1}
            parts={[
              { key: "d", name: "Demand forecast", color: "var(--ink-2)", values: bt.imbalance.map((r) => r.demand_part_chf) },
              { key: "b", name: "Battery", color: "var(--charge)", values: bt.imbalance.map((r) => r.battery_part_chf) },
            ]}
            yFormat={(v) => k(v)}
            yTitle="CHF saved in October"
            ariaLabel="October saving for three assumed imbalance penalties"
          />
          <figcaption>The demand part rises and falls with the penalty. The battery part barely moves.</figcaption>
        </div>
        <div>
          <h3>The size of the battery</h3>
          <p className="note">Each battery holds two hours at full power.</p>
          <LineChart
            height={230}
            labels={bt.battery_size.map((r) => `${r.power_mw} MW`)}
            xTicks={bt.battery_size.map((_, i) => i)}
            series={[
              { key: "c", name: "Best possible", values: bt.battery_size.map((r) => r.ceiling_battery_value_chf), color: "var(--ink-3)", dash: "5 4", width: 1.5 },
              { key: "m", name: "Our plan", values: bt.battery_size.map((r) => r.ml_battery_value_chf), color: "var(--charge)", width: 2.5 },
            ]}
            marker
            zero
            yFormat={(v) => k(v)}
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
          <figcaption>The saving grows almost in step with size, because we assume the battery never moves the market price.</figcaption>
        </div>
        <div>
          <h3>How wrong the price forecast is</h3>
          <p className="note">We added random error to the true prices and planned with them.</p>
          <LineChart
            height={230}
            labels={pts.map((p) => `${dec1(p.mae_eur_mwh)} EUR/MWh error`)}
            xTicks={[0, Math.floor((pts.length - 1) / 2), pts.length - 1]}
            xTickFormat={(_, i) => dec1(pts[i].mae_eur_mwh)}
            series={[{ key: "l", name: "Lost saving", values: pts.map((p) => p.lost_chf), color: "var(--price)", width: 2.5 }]}
            marker
            zero
            yFormat={(v) => k(v)}
            yTitle="CHF of battery saving lost"
            directLabels={false}
            ariaLabel="Battery saving lost in October by size of price forecast error"
          />
          <figcaption>
            About {chf(pe.slope_chf_per_eur)} is lost per month for each EUR/MWh of average price error in this experiment. Our real forecast misses by{" "}
            {dec1(pe.ml.mae_eur_mwh)} EUR/MWh and lost {chf(pe.ml.lost_chf)}; the naive one misses by {dec1(pe.naive.mae_eur_mwh)}.
          </figcaption>
        </div>
      </div>
    </section>
  );
}
