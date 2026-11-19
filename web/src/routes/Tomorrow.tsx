import { useMemo, useState } from "react";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { createColumnHelper, flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type SortingState } from "@tanstack/react-table";
import { useDay, useMeta } from "../data/api";
import type { BidRow, DayPlan } from "../data/types";
import { DayRail, OPTION_WORDS, RailLegend } from "../charts/DayRail";
import { DayPicker, defaultDate } from "../ui/DayPicker";
import { planSentence } from "../ui/sentence";
import { chf, dec1, dec2, int, pct } from "../lib/format";

const route = getRouteApi("/");

export function Tomorrow() {
  const meta = useMeta();
  const search = route.useSearch();
  const navigate = useNavigate();
  const date = search.date ?? (meta.data ? defaultDate(meta.data) : undefined);
  const day = useDay(date);
  const [showActual, setShowActual] = useState(true);

  if (meta.isError) return <p className="status error">The plan data is missing. Run “python -m src.export.export_web” in the project folder, then reload.</p>;
  if (!meta.data || !date) return <p className="status">Loading the plan…</p>;
  const plan = day.data;

  return (
    <>
      <DayPicker meta={meta.data} date={date} onChange={(d) => navigate({ to: "/", search: { date: d } })} />
      {day.isError && <p className="status error">There is no plan for {date}. Pick a day in September or October 2026.</p>}
      {plan && (
        <>
          <h1 className="statement long">{planSentence(plan)}</h1>
          <p className="lede">
            At forecast prices the battery should save {chf(plan.summary.expected_battery_saving_chf)} on this day.{" "}
            {showActual && <>After the auction and the real demand it saved {chf(plan.summary.realised_battery_saving_chf)}.</>}
          </p>

          <div className="daybar" style={{ marginTop: "1.5rem", marginBottom: 0 }}>
            <div className="segmented" role="group" aria-label="What to show">
              <button type="button" aria-pressed={showActual} onClick={() => setShowActual(true)}>
                Plan and what happened
              </button>
              <button type="button" aria-pressed={!showActual} onClick={() => setShowActual(false)}>
                Plan only, as at 10:00
              </button>
            </div>
          </div>

          <div className="rail-wrap">
            <DayRail plan={plan} showActual={showActual} />
          </div>
          <RailLegend showActual={showActual} />

          <section className="section two-col">
            <div>
              <h2 className="h2">{showActual ? "What the day cost" : "What the day should cost"}</h2>
              <Settlement plan={plan} showActual={showActual} />
            </div>
            <div>
              <h2 className="h2">The decision, block by block</h2>
              <BlockTable plan={plan} />
            </div>
          </section>

          <section className="section">
            <h2>Bids to submit before {meta.data.gate_closure_local}</h2>
            <p>
              Energy for the city is bought at any price, because the city must be supplied. Energy for the battery is only bought if the auction price stays
              at or below the limit.
            </p>
            <BidTable plan={plan} />
          </section>
        </>
      )}
    </>
  );
}

function Settlement({ plan, showActual }: { plan: DayPlan; showActual: boolean }) {
  const s = plan.summary;
  if (!showActual)
    return (
      <dl className="ledger">
        <div>
          <dt>Energy to buy</dt>
          <dd>{int(s.energy_to_buy_mwh)} MWh</dd>
        </div>
        <div>
          <dt>Charge level at midnight</dt>
          <dd>{dec1(s.soc_start_mwh)} MWh</dd>
        </div>
        <div className="total">
          <dt>Expected cost</dt>
          <dd>{chf(s.expected_cost_chf)}</dd>
        </div>
        <div className="good">
          <dt>Expected saving from the battery</dt>
          <dd>{chf(s.expected_battery_saving_chf)}</dd>
        </div>
      </dl>
    );
  const auction = s.realised_cost_chf - s.imbalance_cost_chf - s.wear_cost_chf;
  return (
    <>
      <dl className="ledger">
        <div>
          <dt>Bought at the auction</dt>
          <dd>{chf(auction)}</dd>
        </div>
        <div>
          <dt>
            Settling the forecast miss
            <small>of which penalty {chf(s.imbalance_penalty_chf)}</small>
          </dt>
          <dd>{chf(s.imbalance_cost_chf)}</dd>
        </div>
        <div>
          <dt>Battery wear</dt>
          <dd>{chf(s.wear_cost_chf)}</dd>
        </div>
        <div className="total">
          <dt>Total for the day</dt>
          <dd>{chf(s.realised_cost_chf)}</dd>
        </div>
        <div>
          <dt>Expected at 10:00 the day before</dt>
          <dd>{chf(s.expected_cost_chf)}</dd>
        </div>
        <div className={s.realised_battery_saving_chf >= 0 ? "good" : "bad"}>
          <dt>Saved by the battery</dt>
          <dd>{chf(s.realised_battery_saving_chf)}</dd>
        </div>
        <div className={s.realised_saving_vs_baseline_chf >= 0 ? "good" : "bad"}>
          <dt>
            Saved against the simple rule
            <small>buy last week’s demand, no battery</small>
          </dt>
          <dd>{chf(s.realised_saving_vs_baseline_chf)}</dd>
        </div>
      </dl>
      {s.share_charge_cleared != null && (
        <p className="note">
          {pct(s.share_charge_cleared * 100)} of the energy bid for the battery cleared. One CHF was {dec2(1 / s.eurchf)} EUR.
        </p>
      )}
    </>
  );
}

function BlockTable({ plan }: { plan: DayPlan }) {
  return (
    <div className="table-scroll">
      <table className="data">
        <thead>
          <tr>
            <th>Block</th>
            <th>Decision</th>
            <th className="r">Buy</th>
            <th className="r">Store</th>
            <th className="r">Use</th>
            <th className="r">Level after</th>
            <th className="r">Price</th>
          </tr>
        </thead>
        <tbody>
          {plan.blocks.map((b) => (
            <tr key={b.block}>
              <td className="num">{b.label}</td>
              <td>
                <i className={`dot ${b.charge_mwh > 0.05 ? "charge" : b.discharge_mwh > 0.05 ? "use" : ""}`} />
                {OPTION_WORDS[b.option]}
              </td>
              <td className="r">{int(b.buy_mwh)}</td>
              <td className="r">{b.charge_mwh > 0.05 ? dec1(b.charge_mwh) : "–"}</td>
              <td className="r">{b.discharge_mwh > 0.05 ? dec1(b.discharge_mwh) : "–"}</td>
              <td className="r">{dec1(b.soc_end_mwh)}</td>
              <td className="r">{dec1(b.price_fc)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">Energy in MWh, price forecast in EUR per MWh.</p>
    </div>
  );
}

const col = createColumnHelper<BidRow>();

function BidTable({ plan }: { plan: DayPlan }) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [only, setOnly] = useState<"all" | "charge">("all");
  const data = useMemo(() => (only === "all" ? plan.bids : plan.bids.filter((b) => b.bid_type === "charge")), [plan, only]);
  const columns = useMemo(
    () => [
      col.accessor("utc", { header: "Hour", cell: (c) => c.row.original.hour, sortingFn: "alphanumeric" }),
      col.accessor("bid_type", { header: "For", cell: (c) => (c.getValue() === "charge" ? "Battery" : "City") }),
      col.accessor("volume_mwh", { header: "Volume, MWh", cell: (c) => dec1(c.getValue()), meta: { right: true } }),
      col.accessor((r) => r.limit_price_eur_mwh ?? Infinity, {
        id: "limit",
        header: "Price limit, EUR per MWh",
        cell: (c) => (c.row.original.limit_price_eur_mwh == null ? "any price" : dec2(c.row.original.limit_price_eur_mwh)),
        meta: { right: true },
      }),
    ],
    [],
  );
  const table = useReactTable({ data, columns, state: { sorting }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });
  const nCharge = plan.bids.filter((b) => b.bid_type === "charge").length;

  const download = () => {
    const rows = [["delivery_date", "hour_local", "hour_utc", "bid_for", "volume_mwh", "limit_price_eur_mwh"], ...plan.bids.map((b) => [plan.date, b.hour, b.utc, b.bid_type === "charge" ? "battery" : "city", b.volume_mwh.toFixed(3), b.limit_price_eur_mwh == null ? "" : b.limit_price_eur_mwh.toFixed(2)])];
    const blob = new Blob([rows.map((r) => r.join(",")).join("\n") + "\n"], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `bids_${plan.date}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <>
      <div className="daybar" style={{ marginTop: "1rem", marginBottom: 0 }}>
        <div className="segmented" role="group" aria-label="Which bids">
          <button type="button" aria-pressed={only === "all"} onClick={() => setOnly("all")}>
            All {plan.bids.length} bids
          </button>
          <button type="button" aria-pressed={only === "charge"} onClick={() => setOnly("charge")} disabled={!nCharge}>
            Battery only ({nCharge})
          </button>
        </div>
        <button type="button" className="btn quiet" onClick={download}>
          Download bids as CSV
        </button>
      </div>
      <div className="table-scroll" style={{ maxHeight: "26rem", overflowY: "auto", maxWidth: "46rem" }}>
        <table className="data">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => {
                  const right = (h.column.columnDef.meta as { right?: boolean } | undefined)?.right;
                  const dir = h.column.getIsSorted();
                  return (
                    <th key={h.id} className={right ? "r" : undefined} aria-sort={dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none"} style={{ position: "sticky", top: 0, background: "var(--paper)" }}>
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
              <tr key={r.id}>
                {r.getVisibleCells().map((c) => {
                  const right = (c.column.columnDef.meta as { right?: boolean } | undefined)?.right;
                  return (
                    <td key={c.id} className={right ? "r" : c.column.id === "utc" ? "num" : undefined}>
                      {c.column.id === "bid_type" && <i className={`dot ${r.original.bid_type === "charge" ? "charge" : ""}`} />}
                      {flexRender(c.column.columnDef.cell, c.getContext())}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
