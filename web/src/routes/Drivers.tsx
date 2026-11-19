import { useState } from "react";
import { useDrivers, useModels } from "../data/api";
import type { ModelInfo } from "../data/types";
import { ChartLegend, HBars, Heatmap, LineChart } from "../charts/Charts";
import { dec1, dec2, fmtDayMonth, int } from "../lib/format";

const MODEL_COLOR = { demand: "var(--demand)", price: "var(--price)" } as const;

export function DriversPage() {
  const models = useModels();
  const drivers = useDrivers();
  const [target, setTarget] = useState<"demand" | "price">("demand");
  if (models.isError || drivers.isError) return <p className="status error">The model results are missing. Run “python -m src.export.export_web”, then reload.</p>;
  if (!models.data || !drivers.data) return <p className="status">Loading the models…</p>;
  const m = models.data[target];
  const best = m.ladder.find((r) => r.model === "best")!;
  const naive = m.ladder.find((r) => r.model === "naive")!;
  const d = drivers.data;
  const cut = Math.round(100 * (1 - best.test_mae / naive.test_mae));
  const typical = m.test_series.reduce((a, r) => a + r.actual, 0) / Math.max(m.test_series.length, 1);

  return (
    <>
      <div className="daybar">
        <div className="segmented" role="group" aria-label="Which forecast">
          <button type="button" aria-pressed={target === "demand"} onClick={() => setTarget("demand")}>
            Demand forecast
          </button>
          <button type="button" aria-pressed={target === "price"} onClick={() => setTarget("price")}>
            Price forecast
          </button>
        </div>
      </div>
      <h1 className="statement long">
        {target === "demand"
          ? `The demand forecast misses by ${dec1(best.test_mae)} MW on a city that draws about ${int(typical)}.`
          : `The price forecast misses by ${dec1(best.test_mae)} EUR on a price near ${int(typical)}.`}
      </h1>
      <p className="lede">
        Measured on October 2026, which the model never saw. “Same block last week” misses by {dec1(naive.test_mae)} {m.unit}, so the model cuts the error
        by {cut} %.
      </p>

      <section className="section two-col even">
        <div>
          <h2 className="h2">From the simplest rule to the best model</h2>
          <p className="explain">Average miss in October, in {m.unit}. The thin line is the likely range.</p>
          <HBars
            ariaLabel={`Average error in October by model, in ${m.unit}`}
            format={dec2}
            labelWidth={170}
            rows={m.ladder.map((r) => ({
              label: r.name,
              value: r.test_mae,
              lo: r.test_ci_low,
              hi: r.test_ci_high,
              color: r.model === "best" ? MODEL_COLOR[target] : "var(--ink-3)",
              strong: r.model === "best",
            }))}
          />
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>Model</th>
                  <th className="r">September</th>
                  <th className="r">October</th>
                  <th className="r">{m.pct_metric}, October</th>
                  <th className="r">Oct 2025 to Aug 2026</th>
                </tr>
              </thead>
              <tbody>
                {m.ladder.map((r) => (
                  <tr key={r.model} className={r.model === "best" ? "is-product" : undefined}>
                    <td>{r.name}</td>
                    <td className="r">{dec2(r.val_mae)}</td>
                    <td className="r">{dec2(r.test_mae)}</td>
                    <td className="r">{dec2(r.test_pct)} %</td>
                    <td className="r">{r.rolling_mae == null ? "–" : dec2(r.rolling_mae)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="note">The model was chosen on September and then run once on October. {m.best_description}</p>
          </div>
        </div>
        <div>
          <h2 className="h2">What the model leans on</h2>
          <p className="explain">How much worse the forecast gets, in {m.unit}, when one input is scrambled.</p>
          <HBars ariaLabel="Importance of each input" format={dec2} stacked rows={m.importance.slice(0, 10).map((r) => ({ label: r.label, value: r.value, color: MODEL_COLOR[target] }))} />
        </div>
      </section>

      <section className="section">
        <h2>Every forecast of the test month</h2>
        <p>Six blocks a day for 31 days. The coloured line is the forecast made the day before, the dark line is what happened.</p>
        <LineChart
          height={300}
          labels={m.test_series.map((r) => `${fmtDayMonth(r.date)}, block ${r.block + 1}`)}
          xTicks={m.test_series.map((r, i) => (r.block === 0 && [1, 8, 15, 22, 29].includes(Number(r.date.slice(8))) ? i : -1)).filter((i) => i >= 0)}
          xTickFormat={(_, i) => fmtDayMonth(m.test_series[i].date)}
          band={m.test_series[0]?.q10 != null ? { lo: m.test_series.map((r) => r.q10), hi: m.test_series.map((r) => r.q90), color: target === "demand" ? "var(--saving-tint)" : "var(--price-tint)" } : undefined}
          series={[
            { key: "f", name: "Forecast", values: m.test_series.map((r) => r.best), color: MODEL_COLOR[target], width: 2 },
            { key: "a", name: "Actual", values: m.test_series.map((r) => r.actual), color: "var(--ink)", width: 1 },
          ]}
          yTitle={m.unit}
          yFormat={int}
          ariaLabel={`Forecast and actual ${target} for every block of October 2026`}
        />
      </section>

      <section className="section">
        <h2>What moves demand in Zurich</h2>
        <p>Plain charts from the data, to show the patterns the model picks up.</p>
        <div className="three-col" style={{ marginTop: "1.5rem" }}>
          <div>
            <h3>Cold days need more power</h3>
            <LineChart
              height={230}
              labels={d.temp_demand[0]?.points.map((p) => `${p.temp_c} °C`) ?? []}
              series={pickBlocks(d.temp_demand).map((b, i) => ({ key: b.label, name: b.label, values: b.points.map((p) => p.demand_mw), color: ["var(--ink-3)", "var(--demand)", "var(--use)"][i], width: 2 }))}
              xTicks={(d.temp_demand[0]?.points ?? []).map((p, i) => (p.temp_c % 8 === 0 ? i : -1)).filter((i) => i >= 0)}
              xTickFormat={(l) => l.replace(" °C", "°")}
              yTitle="MW, working days, by outside temperature"
              ariaLabel="Demand by outside temperature for three blocks of the day"
            />
            <figcaption>Demand is lowest near 15 to 20 °C. It rises when it gets cold, and a little when it gets hot.</figcaption>
          </div>
          <div>
            <h3>Sunshine: no simple pattern in the raw data</h3>
            <LineChart
              height={230}
              labels={d.radiation_demand.map((p) => `${int(p.radiation_wm2)} W/m²`)}
              series={[{ key: "r", name: "12–16", values: d.radiation_demand.map((p) => p.demand_mw), color: "var(--use)", width: 2.5 }]}
              xTickFormat={(l) => l.replace(" W/m²", "")}
              marker
              zero
              directLabels={false}
              yTitle="MW at 12–16, working days, April to September"
              ariaLabel="Midday demand by solar radiation"
            />
            <figcaption>
              Afternoon demand by solar radiation, in watts per square metre. Taken alone, sunshine barely moves demand. The model still ranks the radiation
              forecast among its top inputs, because it reads it together with temperature and season.
            </figcaption>
          </div>
          <div>
            <h3>Working days, Saturdays, Sundays</h3>
            <LineChart
              height={230}
              labels={d.profile[0]?.hours.map((h) => `${String(h).padStart(2, "0")}:00`) ?? []}
              xTicks={[0, 6, 12, 18, 23]}
              series={d.profile.map((p, i) => ({ key: p.daytype, name: p.daytype, values: p.demand_mw, color: ["var(--ink)", "var(--charge)", "var(--use)", "var(--price)"][i], width: i === 0 ? 2.5 : 1.75 }))}
              yTitle="MW, average of the last 12 months"
              directLabels={false}
              ariaLabel="Average hourly demand by type of day"
            />
            <ChartLegend items={d.profile.map((p, i) => ({ name: p.daytype, color: ["var(--ink)", "var(--charge)", "var(--use)", "var(--price)"][i] }))} />
            <figcaption>Public holidays look like Sundays. Knowing the calendar is worth more than any other input except past demand.</figcaption>
          </div>
          <div>
            <h3>Electric cars: no visible effect yet</h3>
            <LineChart
              height={230}
              labels={d.ev.map((p) => String(p.year))}
              series={[{ key: "n", name: "Night demand", values: d.ev.map((p) => p.night_demand_mw), color: "var(--ink)", width: 2.5 }]}
              marker
              zero
              directLabels={false}
              yTitle="MW at 00–04, yearly average"
              ariaLabel="Night demand by year"
            />
            <figcaption>
              Electric cars in the city went from {int(d.ev[0]?.ev_count)} in {d.ev[0]?.year} to {int(d.ev[d.ev.length - 1]?.ev_count)} in {d.ev[d.ev.length - 1]?.year}. Night
              demand did not follow, and the model was no better with the car count than without it.
            </figcaption>
          </div>
          <div>
            <h3>A big event barely shows</h3>
            <LineChart
              height={230}
              labels={d.street_parade[0]?.hours.map((h) => `${String(h).padStart(2, "0")}:00`) ?? []}
              xTicks={[0, 6, 12, 18, 23]}
              series={d.street_parade.map((p, i) => ({ key: p.label, name: p.label, values: p.demand_mw, color: i === 0 ? "var(--price)" : "var(--ink-3)", width: i === 0 ? 2.5 : 1.75 }))}
              yTitle="MW"
              directLabels={false}
              ariaLabel="Demand on Street Parade day against nearby Saturdays"
            />
            <ChartLegend items={d.street_parade.map((p, i) => ({ name: p.label, color: i === 0 ? "var(--price)" : "var(--ink-3)" }))} />
            <figcaption>Street Parade brings hundreds of thousands of people to the lake, yet the city’s load stays close to a normal Saturday.</figcaption>
          </div>
          <div>
            <h3>School holidays take a little off</h3>
            <LineChart
              height={230}
              labels={d.school_holiday[0]?.hours.map((h) => `${String(h).padStart(2, "0")}:00`) ?? []}
              xTicks={[0, 6, 12, 18, 23]}
              series={d.school_holiday.map((p, i) => ({ key: p.label, name: p.label, values: p.demand_mw, color: i === 0 ? "var(--charge)" : "var(--ink-3)", width: i === 0 ? 2.5 : 1.75 }))}
              yTitle="MW, October 2026 weekdays"
              directLabels={false}
              ariaLabel="Demand on school holiday weekdays against other weekdays"
            />
            <ChartLegend items={d.school_holiday.map((p, i) => ({ name: p.label, color: i === 0 ? "var(--charge)" : "var(--ink-3)" }))} />
            <figcaption>Autumn holiday weekdays against the other weekdays of the month.</figcaption>
          </div>
        </div>
      </section>

      <section className="section">
        <h2>What moves the Swiss price</h2>
        <div className="three-col" style={{ marginTop: "1.5rem" }}>
          <div>
            <h3>Cheap at midday in summer, dear on winter evenings</h3>
            <Heatmap rows={d.price_heatmap.months} cols={d.price_heatmap.blocks} values={d.price_heatmap.values} ariaLabel="Mean price by month and block of the day" />
            <figcaption>Mean price in EUR per MWh, darker is dearer. This daily shape is what the battery earns from.</figcaption>
          </div>
          <div>
            <h3>Wind in Germany pushes the price down</h3>
            <HBars
              ariaLabel="Swiss price against its recent average by German wind forecast"
              format={(v) => `${v > 0 ? "+" : "−"}${dec1(Math.abs(v))}`}
              labelWidth={130}
              rows={d.wind_price.map((r) => ({ label: r.wind_bin, value: r.price_vs_recent_eur, color: r.price_vs_recent_eur >= 0 ? "var(--price)" : "var(--charge)" }))}
            />
            <figcaption>Swiss price minus its average of the four weeks before, in EUR per MWh, by how windy the forecast for northern Germany is.</figcaption>
          </div>
          <div>
            <h3>Gas sets the level</h3>
            <LineChart
              height={230}
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
                { name: "Gas (TTF)", color: "var(--use)" },
              ]}
            />
            <figcaption>Both in EUR per MWh, so they share one scale. The 2022 crisis shows how closely power follows gas.</figcaption>
          </div>
        </div>
      </section>
    </>
  );
}

/** Night, midday and evening blocks are enough to show the pattern without a tangle of six lines. */
function pickBlocks(all: { block: number; label: string; points: { temp_c: number; demand_mw: number; n: number }[] }[]) {
  const want = [0, 2, 4];
  const chosen = all.filter((b) => want.includes(b.block));
  return chosen.length ? chosen : all.slice(0, 3);
}
