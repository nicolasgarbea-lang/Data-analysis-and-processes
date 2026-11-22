import { useMemo, useState } from "react";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useDay, useMeta } from "../data/api";
import type { DayPlan } from "../data/types";
import { DayRail, RailLegend } from "../charts/DayRail";
import { DayPicker, defaultDate } from "../ui/DayPicker";
import { Figures, Fold, PageIntro, Step } from "../ui/Blocks";
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
      <PageIntro
        title="Replay a test day"
        what="one past day from the test (September or October 2026), planned exactly as the tool would have done it the morning before, and then compared with what really happened."
        how="(1) pick a day, (2) read the decision, (3) switch between the plan and reality, (4) open the bids or the bill if you want the detail."
      />

      <Step n={1} title="Pick a day" />
      <DayPicker meta={meta.data} date={date} onChange={(d) => navigate({ to: "/", search: { date: d } })} />
      {day.isError && <p className="status error">There is no plan for {date}. Pick a day in September or October 2026.</p>}
      {plan && (
        <>
          <Step n={2} title="The decision made the morning before" hint="The whole plan in one sentence. “Store” = charge the battery, “use” = take energy out of the battery instead of buying it." />
          <p className="statement long">{planSentence(plan)}</p>

          <Step
            n={3}
            title="Plan vs reality"
            hint="“The plan at 10:00” shows what was expected when the bids were sent. “What really happened” shows the real cost and saving after the real prices and demand were known."
          />
          <div className="daybar" style={{ marginTop: "0.5rem", marginBottom: "1rem" }}>
            <div className="segmented" role="group" aria-label="What to show">
              <button type="button" aria-pressed={!showActual} onClick={() => setShowActual(false)}>
                The plan at 10:00
              </button>
              <button type="button" aria-pressed={showActual} onClick={() => setShowActual(true)}>
                What really happened
              </button>
            </div>
          </div>
          <DayFigures plan={plan} showActual={showActual} />
          <div className="rail-wrap">
            <DayRail plan={plan} showActual={showActual} />
          </div>
          <RailLegend showActual={showActual} />

          <Step n={4} title="Details (optional)" />
          <div className="folds" style={{ marginTop: "0.5rem" }}>
            <Fold title={`The ${plan.bids.length} bids for the auction`} hint={`What is sent before ${meta.data.gate_closure_local}, hour by hour`}>
              <Bids plan={plan} />
            </Fold>
            <Fold title="Where the money went" hint="The day’s bill, line by line">
              <Bill plan={plan} />
            </Fold>
          </div>
        </>
      )}
    </>
  );
}

function DayFigures({ plan, showActual }: { plan: DayPlan; showActual: boolean }) {
  const s = plan.summary;
  if (!showActual)
    return (
      <Figures
        items={[
          { value: `${int(s.energy_to_buy_mwh)} MWh`, label: "to buy at the auction" },
          { value: chf(s.expected_cost_chf), label: "expected cost at forecast prices" },
          { value: chf(s.expected_battery_saving_chf), label: "expected saving from the battery", tone: "good" },
        ]}
      />
    );
  return (
    <Figures
      items={[
        { value: chf(s.realised_cost_chf), label: "what the day really cost" },
        { value: chf(s.realised_battery_saving_chf), label: `saved by the battery (${chf(s.expected_battery_saving_chf)} expected)`, tone: s.realised_battery_saving_chf >= 0 ? "good" : "bad" },
        {
          value: chf(s.realised_saving_vs_baseline_chf),
          label: "saved in total, against buying last week’s demand with no battery",
          tone: s.realised_saving_vs_baseline_chf >= 0 ? "good" : "bad",
        },
      ]}
    />
  );
}

function Bill({ plan }: { plan: DayPlan }) {
  const s = plan.summary;
  const auction = s.realised_cost_chf - s.imbalance_cost_chf - s.wear_cost_chf;
  return (
    <div style={{ maxWidth: "36rem" }}>
      <dl className="ledger">
        <div>
          <dt>Energy bought at the auction</dt>
          <dd>{chf(auction)}</dd>
        </div>
        <div>
          <dt>
            Settling what the forecast missed
            <small>of which penalty {chf(s.imbalance_penalty_chf)}</small>
          </dt>
          <dd>{chf(s.imbalance_cost_chf)}</dd>
        </div>
        <div>
          <dt>Battery wear</dt>
          <dd>{chf(s.wear_cost_chf)}</dd>
        </div>
        <div className="total">
          <dt>Total</dt>
          <dd>{chf(s.realised_cost_chf)}</dd>
        </div>
      </dl>
      <p className="note">
        {s.share_charge_cleared != null ? `${pct(s.share_charge_cleared * 100)} of the energy bid for the battery was bought. ` : ""}
        Prices are in EUR and converted at {dec2(s.eurchf)} CHF per EUR.
      </p>
    </div>
  );
}

function Bids({ plan }: { plan: DayPlan }) {
  const [batteryOnly, setBatteryOnly] = useState(false);
  const rows = useMemo(() => (batteryOnly ? plan.bids.filter((b) => b.bid_type === "charge") : plan.bids), [plan, batteryOnly]);
  const nCharge = plan.bids.filter((b) => b.bid_type === "charge").length;

  const download = () => {
    const lines = [
      ["delivery_date", "hour_local", "hour_utc", "bid_for", "volume_mwh", "limit_price_eur_mwh"],
      ...plan.bids.map((b) => [plan.date, b.hour, b.utc, b.bid_type === "charge" ? "battery" : "city", b.volume_mwh.toFixed(3), b.limit_price_eur_mwh == null ? "" : b.limit_price_eur_mwh.toFixed(2)]),
    ];
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.map((r) => r.join(",")).join("\n") + "\n"], { type: "text/csv" }));
    a.download = `bids_${plan.date}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <>
      <p className="explain">
        Energy for the city has no price limit: the city must be supplied, whatever the price. Energy for the battery is only bought if the price stays at or
        below the limit, otherwise storing it would lose money.
      </p>
      <div className="daybar" style={{ marginTop: "1rem", marginBottom: 0 }}>
        <div className="segmented" role="group" aria-label="Which bids">
          <button type="button" aria-pressed={!batteryOnly} onClick={() => setBatteryOnly(false)}>
            All
          </button>
          <button type="button" aria-pressed={batteryOnly} onClick={() => setBatteryOnly(true)} disabled={!nCharge}>
            Battery only ({nCharge})
          </button>
        </div>
        <button type="button" className="btn quiet" onClick={download}>
          Download as CSV
        </button>
      </div>
      <div className="table-scroll" style={{ maxWidth: "40rem" }}>
        <table className="data">
          <thead>
            <tr>
              <th>Hour</th>
              <th>For</th>
              <th className="r">MWh</th>
              <th className="r">Price limit, EUR/MWh</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => (
              <tr key={`${b.utc}-${b.bid_type}`}>
                <td className="num">{b.hour}</td>
                <td>
                  <i className={`dot ${b.bid_type === "charge" ? "charge" : ""}`} />
                  {b.bid_type === "charge" ? "Battery" : "City"}
                </td>
                <td className="r">{dec1(b.volume_mwh)}</td>
                <td className="r">{b.limit_price_eur_mwh == null ? "no limit" : dec2(b.limit_price_eur_mwh)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
