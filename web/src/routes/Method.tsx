import { useMeta, useMethod } from "../data/api";

export function MethodPage() {
  const meta = useMeta();
  const method = useMethod();
  if (method.isError) return <p className="status error">The method notes are missing. Run “python -m src.export.export_web”, then reload.</p>;
  if (!method.data || !meta.data) return <p className="status">Loading…</p>;
  const m = method.data;
  const phases = [...new Set(m.reviews.map((r) => r.phase))];
  return (
    <>
      <h1 className="statement long">One forecast a day, an hour before the auction closes.</h1>
      <p className="lede">
        {meta.data.company} is a fictional utility that supplies the city of Zurich. Every day it must buy tomorrow’s electricity at the Swiss day-ahead
        auction. At that moment it knows neither tomorrow’s demand nor tomorrow’s price.
      </p>

      <ol className="timeline">
        <li>
          <span className="time">{meta.data.forecast_time_local}</span>
          <p>The models forecast demand and price for the six 4-hour blocks of tomorrow. The optimiser plans the battery.</p>
        </li>
        <li>
          <span className="time">{meta.data.gate_closure_local}</span>
          <p>The auction closes. The bids for all 24 hours of tomorrow must be in.</p>
        </li>
        <li>
          <span className="time">About 11:10</span>
          <p>The auction publishes tomorrow’s prices. Bids for the battery clear only where the price stayed under the limit.</p>
        </li>
        <li>
          <span className="time">Tomorrow</span>
          <p>The energy is delivered. If the city needs more or less than was bought, the gap is settled at a worse price.</p>
        </li>
      </ol>

      <section className="section">
        <h2>How a day is settled</h2>
        <p>
          Every bought MWh is paid at the real hourly auction price. If the city is short, the missing energy costs the auction price plus{" "}
          {Math.round((meta.data.imbalance.shortage_price_factor - 1) * 100)} %. If too much was bought, the surplus is sold at the auction price minus{" "}
          {Math.round((1 - meta.data.imbalance.surplus_price_factor) * 100)} %. This penalty is our assumption, and most of the saving depends on it.
        </p>
        <p className="explain">
          The battery is planned {meta.data.decision.plan_resolution === "hourly_shape" ? "hour by hour, using the usual hourly price pattern of the last seven similar days" : "in the six 4-hour blocks"}.
          A bid to store energy carries a price limit: {Math.round(meta.data.decision.charge_limit_factor * 100)} % of the price expected when the energy is used
          again, minus the wear cost. These rules were chosen on the months before October.
        </p>
      </section>

      <section className="section">
        <h2>What is known at {meta.data.forecast_time_local}</h2>
        <p>A forecast may only use what was already published. An automatic test rebuilds the inputs from cut-off data to check this.</p>
        <div className="table-scroll">
          <table className="data" style={{ maxWidth: "58rem" }}>
            <thead>
              <tr>
                <th>Input</th>
                <th>Latest value the forecast may use</th>
              </tr>
            </thead>
            <tbody>
              {m.time_rules.map((r) => (
                <tr key={r.input}>
                  <td>{r.input}</td>
                  <td>{r.known}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section">
        <h2>What the results cannot tell you</h2>
        <div className="limits">
          {m.limitations.map((l) => (
            <div key={l.title}>
              <h3>{l.title}</h3>
              <p>{l.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <h2>Where the data comes from</h2>
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr>
                <th>Input</th>
                <th>Source</th>
                <th>Step</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {m.sources.map((s) => (
                <tr key={s.input}>
                  <td>{s.input}</td>
                  <td>{s.source}</td>
                  <td>{s.step}</td>
                  <td>{s.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section">
        <h2>What independent reviewers found</h2>
        <p>After each phase a different AI model checked the work with a fresh start and no right to change files. These are its findings and what we did.</p>
        {phases.map((p) => (
          <details key={p} className="review">
            <summary>
              {p} <span className="note">({m.reviews.filter((r) => r.phase === p).length} findings)</span>
            </summary>
            <div className="table-scroll">
              <table className="data">
                <thead>
                  <tr>
                    <th style={{ width: "50%" }}>Finding</th>
                    <th>What we did</th>
                  </tr>
                </thead>
                <tbody>
                  {m.reviews
                    .filter((r) => r.phase === p)
                    .map((r, i) => (
                      <tr key={i}>
                        <td>{r.finding}</td>
                        <td>{r.decision}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </details>
        ))}
      </section>
    </>
  );
}
