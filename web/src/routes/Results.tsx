import { useState } from "react";
import { useBacktest, useDrivers, useModels } from "../data/api";
import type { ModelInfo } from "../data/types";
import { HBars, LineChart } from "../charts/Charts";
import { Figures, Fold } from "../ui/Blocks";
import { chf, dec1, dec2, fmtDayMonth, int, pct } from "../lib/format";
import { k, Ladder, Patterns, Sensitivities, StrategyTable } from "./ResultsParts";

const LINES: Record<string, { name: string; color: string; width: number; dash?: string }> = {
  perfect_foresight_hourly_battery: { name: "Knowing the future", color: "var(--ink-3)", width: 1.5, dash: "4 4" },
  ml_battery: { name: "Our plan", color: "var(--saving)", width: 3 },
  ml_no_battery: { name: "Forecast only, no battery", color: "var(--ink-2)", width: 1.75 },
};

export function Results() {
  const bt = useBacktest();
  const models = useModels();
  const drivers = useDrivers();
  const [target, setTarget] = useState<"demand" | "price">("demand");
  if (bt.isError || models.isError) return <p className="status error">The results are missing. Run “python -m src.export.export_web”, then reload.</p>;
  if (!bt.data || !models.data) return <p className="status">Loading the results…</p>;

  const s = bt.data.splits.find((x) => x.split === "test") ?? bt.data.splits[0];
  const d = s.decomposition;
  const half = bt.data.imbalance.find((r) => Math.abs(r.shortage_factor - 1.1) < 1e-6);
  const earlier = bt.data.splits.filter((x) => x.split !== "test");
  const m = models.data[target];

  return (
    <>
      <h1 className="statement">In October the plan saved {chf(d.total_saving_chf)}.</h1>
      <p className="lede">Compared with what a utility could do without any model: buy what the city used a week ago, and leave the battery off.</p>

      <Figures
        items={[
          { value: chf(d.demand_forecast_part_chf), label: "from forecasting demand better, so fewer penalties for buying the wrong amount" },
          { value: chf(d.battery_part_chf), label: "from the battery: storing cheap energy and using it when the price is high" },
          { value: pct(d.pct_ceiling_captured_total), label: "of what knowing the future would have saved" },
        ]}
      />

      {half && s.ci && (
        <p className="caveat">
          <strong>Two things to keep in mind.</strong> The penalty for buying the wrong amount is our assumption (20 % of the price). At half that penalty the
          October saving is {chf(half.total_saving_chf)}; the battery part hardly changes. And 31 days is short: anything from {chf(s.ci.block_low)} to{" "}
          {chf(s.ci.block_high)} is plausible.
        </p>
      )}

      <section className="section">
        <h2>Saved, day by day</h2>
        <LineChart
          labels={s.cumulative.dates.map(fmtDayMonth)}
          series={s.cumulative.series.filter((x) => LINES[x.key]).map((x) => ({ key: x.key, values: x.values, ...LINES[x.key] }))}
          yFormat={k}
          yTitle="CHF saved so far in October"
          zero
          height={320}
          ariaLabel="Running total of the October saving for our plan, the forecast without battery, and perfect foresight"
        />
      </section>

      <section className="section">
        <h2>How good the forecasts are</h2>
        <p>Both models were chosen on September, then tested once on October.</p>
        <div className="two-col even" style={{ marginTop: "1.25rem" }}>
          <Accuracy m={models.data.demand} />
          <Accuracy m={models.data.price} />
        </div>

        <div className="daybar" style={{ marginTop: "2.5rem", marginBottom: 0 }}>
          <div className="segmented" role="group" aria-label="Which forecast">
            <button type="button" aria-pressed={target === "demand"} onClick={() => setTarget("demand")}>
              Demand
            </button>
            <button type="button" aria-pressed={target === "price"} onClick={() => setTarget("price")}>
              Price
            </button>
          </div>
          <span className="when">Every forecast of October, made the day before, against what happened</span>
        </div>
        <LineChart
          height={280}
          labels={m.test_series.map((r) => `${fmtDayMonth(r.date)}, ${["00–04", "04–08", "08–12", "12–16", "16–20", "20–24"][r.block]}`)}
          xTicks={m.test_series.map((r, i) => (r.block === 0 && [1, 8, 15, 22, 29].includes(Number(r.date.slice(8))) ? i : -1)).filter((i) => i >= 0)}
          xTickFormat={(_, i) => fmtDayMonth(m.test_series[i].date)}
          series={[
            { key: "f", name: "Forecast", values: m.test_series.map((r) => r.best), color: target === "demand" ? "var(--demand)" : "var(--price)", width: 2 },
            { key: "a", name: "Actual", values: m.test_series.map((r) => r.actual), color: "var(--ink)", width: 1 },
          ]}
          yTitle={m.unit}
          yFormat={int}
          ariaLabel={`Forecast and actual ${target} for every block of October 2026`}
        />
      </section>

      <div className="folds">
        <Fold title="What the forecasts rely on" hint="The inputs that matter most, and the ones that do not">
          <div className="two-col even">
            <Inputs m={models.data.demand} />
            <Inputs m={models.data.price} />
          </div>
          <p className="note" style={{ marginTop: "1.5rem" }}>
            Electric cars and big events such as the Street Parade added nothing measurable to the demand forecast.
          </p>
        </Fold>
        <Fold title="Every strategy compared" hint="From the simple rule up to knowing the future">
          <StrategyTable rows={s.strategies} />
        </Fold>
        <Fold title="What the result depends on" hint="The penalty, the battery size and the price forecast">
          <Sensitivities bt={bt.data} />
        </Fold>
        <Fold title="Every model we tried" hint="From “same as last week” to the final model">
          <div className="two-col even">
            <Ladder m={models.data.demand} />
            <Ladder m={models.data.price} />
          </div>
        </Fold>
        {drivers.data && (
          <Fold title="Patterns in the data" hint="Temperature, holidays, electric cars, wind and gas">
            <Patterns d={drivers.data} />
          </Fold>
        )}
        <Fold title="The months before October" hint="Not a clean test: the bidding rules were tuned on them">
          <div className="table-scroll">
            <table className="data" style={{ maxWidth: "40rem" }}>
              <thead>
                <tr>
                  <th>Period</th>
                  <th className="r">Days</th>
                  <th className="r">Saved</th>
                  <th className="r">From the battery</th>
                </tr>
              </thead>
              <tbody>
                {earlier.map((x) => (
                  <tr key={x.split}>
                    <td>{x.split === "val" ? "September 2026" : "October 2025 to August 2026"}</td>
                    <td className="r">{x.days}</td>
                    <td className="r">{chf(x.decomposition.total_saving_chf)}</td>
                    <td className="r">{chf(x.decomposition.battery_part_chf)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Fold>
      </div>
    </>
  );
}

function Accuracy({ m }: { m: ModelInfo }) {
  const best = m.ladder.find((r) => r.model === "best")!;
  const naive = m.ladder.find((r) => r.model === "naive")!;
  return (
    <div>
      <h3>
        {m.target === "demand" ? "Demand" : "Price"}: {Math.round(100 * (1 - best.test_mae / naive.test_mae))} % smaller miss
      </h3>
      <HBars
        ariaLabel={`Average ${m.target} forecast error in October, ${m.unit}`}
        format={(v) => `${dec2(v)} ${m.unit}`}
        labelWidth={150}
        rows={[
          { label: "Same as last week", value: naive.test_mae, color: "var(--ink-3)" },
          { label: "Our model", value: best.test_mae, color: m.target === "demand" ? "var(--demand)" : "var(--price)", strong: true },
        ]}
      />
      <p className="note">
        Average miss per 4-hour block{m.target === "demand" ? `, or ${dec1(best.test_pct)} % of demand` : ""}.
      </p>
    </div>
  );
}

function Inputs({ m }: { m: ModelInfo }) {
  return (
    <div>
      <h3>{m.target === "demand" ? "Demand forecast" : "Price forecast"}</h3>
      <HBars
        ariaLabel={`Most important inputs of the ${m.target} model`}
        format={dec1}
        stacked
        rows={m.importance.slice(0, 5).map((r) => ({ label: r.label, value: r.value, color: m.target === "demand" ? "var(--demand)" : "var(--price)" }))}
      />
      <p className="note">How much worse the forecast gets, in {m.unit}, if that input is scrambled.</p>
    </div>
  );
}
