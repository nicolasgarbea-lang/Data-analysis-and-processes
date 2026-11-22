import { useMeta, useMethod } from "../data/api";
import { Card, Fold, PageIntro } from "../ui/Blocks";

const KEY_LIMITS = [/imbalance|penalty/i, /one test month|only one/i, /fictional/i, /observed weather/i];

export function MethodPage() {
  const meta = useMeta();
  const method = useMethod();
  if (method.isError) return <p className="status error">The method notes are missing. Run “python -m src.export.export_web”, then reload.</p>;
  if (!method.data || !meta.data) return <p className="status">Loading…</p>;
  const m = method.data;
  const key = KEY_LIMITS.map((re) => m.limitations.find((l) => re.test(l.title))).filter((l): l is (typeof m.limitations)[number] => !!l);
  const shown = key.length ? key : m.limitations.slice(0, 4);
  const shortage = Math.round((meta.data.imbalance.shortage_price_factor - 1) * 100);

  return (
    <>
      <PageIntro
        title="How it works"
        what={
          <>
            the method in short. {meta.data.company} is a fictional utility that supplies the city of Zurich. Each morning it buys tomorrow’s electricity at the
            Swiss auction, without knowing tomorrow’s demand or price. Two forecasts and a battery plan help it decide.
          </>
        }
        how="read the two cards; the closed sections at the bottom are for reference."
      />

      <div className="grid-2">
        <Card n={1} title="One day, step by step">
      <ol className="timeline">
        <li>
          <span className="time">{meta.data.forecast_time_local}</span>
          <p>Two models forecast tomorrow’s demand and price. An optimiser plans the battery.</p>
        </li>
        <li>
          <span className="time">{meta.data.gate_closure_local}</span>
          <p>The auction closes. Bids for all 24 hours are in.</p>
        </li>
        <li>
          <span className="time">About 11:10</span>
          <p>Prices are published. Battery bids are bought only where the price stayed under the limit.</p>
        </li>
        <li>
          <span className="time">Tomorrow</span>
          <p>Energy is delivered. Buying too much or too little costs a penalty of {shortage} % of the price.</p>
        </li>
      </ol>
        </Card>

        <Card n={2} title="Keep in mind" hint="The main limits of the results.">
        <div className="limits">
          {shown.map((l) => (
            <div key={l.title}>
              <h3>{l.title}</h3>
              <p>{l.text}</p>
            </div>
          ))}
        </div>
        </Card>
      </div>

      <div className="folds">
        <Fold title="What the forecast may use" hint={`Only what was published by ${meta.data.forecast_time_local} the day before`}>
          <div className="table-scroll">
            <table className="data" style={{ maxWidth: "58rem" }}>
              <thead>
                <tr>
                  <th>Input</th>
                  <th>Latest value allowed</th>
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
        </Fold>
        <Fold title="Where the data comes from" hint={`${m.sources.length} public sources, 2019 to October 2026`}>
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>Input</th>
                  <th>Source</th>
                  <th>Step</th>
                </tr>
              </thead>
              <tbody>
                {m.sources.map((s) => (
                  <tr key={s.input}>
                    <td>{s.input}</td>
                    <td>{s.source}</td>
                    <td>{s.step}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Fold>
        <Fold title="All limitations" hint={`${m.limitations.length} points, in plain words`}>
          <div className="limits">
            {m.limitations.map((l) => (
              <div key={l.title}>
                <h3>{l.title}</h3>
                <p>{l.text}</p>
              </div>
            ))}
          </div>
        </Fold>
        <Fold title="What independent reviewers found" hint={`${m.reviews.length} findings, and what we did about each`}>
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>Phase</th>
                  <th style={{ width: "42%" }}>Finding</th>
                  <th>What we did</th>
                </tr>
              </thead>
              <tbody>
                {m.reviews.map((r, i) => (
                  <tr key={i}>
                    <td style={{ whiteSpace: "nowrap" }}>{r.phase}</td>
                    <td>{r.finding}</td>
                    <td>{r.decision}</td>
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
