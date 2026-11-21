import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { refreshLive, useApiHealth, useLiveLog, useLivePlan, useLiveStatus, useMeta } from "../data/api";
import type { LiveLogEntry, LivePlan, LivePlanRequest, LiveSource, Option } from "../data/types";
import { LineChart, ChartLegend } from "../charts/Charts";
import { OPTION_WORDS } from "../charts/DayRail";
import { Figures, Fold } from "../ui/Blocks";
import { planSentence } from "../ui/sentence";
import { chf, dec1, dec2, fmtDayMonth, fmtLongDate, int } from "../lib/format";
import { StartCommands } from "../ui/StartService";
import "./live.css";

// ---------- small helpers ----------

/** Timestamps from the service are UTC; accept "2026-11-21T09:00:00Z", "+00:00" or a bare "2026-11-21 09:00:00". */
function parseUtc(s: string | null | undefined): Date | null {
  if (!s) return null;
  let t = s.trim().replace(" ", "T");
  if (/^\d{4}-\d{2}-\d{2}$/.test(t)) t += "T00:00:00";
  if (!/(Z|[+-]\d{2}:?\d{2})$/.test(t)) t += "Z";
  const d = new Date(t);
  return isNaN(d.getTime()) ? null : d;
}
const zurichDayTime = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Zurich", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const atDayTime = (s: string | null | undefined) => {
  const d = parseUtc(s);
  return d ? zurichDayTime.format(d) : "–";
};

type Tone = "good" | "warn" | "bad";
const sourceTone = (s: LiveSource): Tone => (!s.ok ? "bad" : /estimat|stale/i.test(s.message) ? "warn" : "good");
const inputTone: Record<LivePlan["inputs"][number]["status"], Tone> = { ok: "good", estimated: "warn", stale: "warn", missing: "bad" };
const optionWord = (o: string) => OPTION_WORDS[o as Option] ?? o.replace(/_/g, " ");
const num = (v: number | null | undefined) => (v == null ? "–" : Math.abs(v) >= 100 ? int(v) : dec1(v));
const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

function useElapsed(running: boolean) {
  const [sec, setSec] = useState(0);
  useEffect(() => {
    if (!running) return;
    setSec(0);
    const start = Date.now();
    const t = setInterval(() => setSec(Math.round((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(t);
  }, [running]);
  return sec;
}

// ---------- the page ----------

interface Form {
  temp: number;
  holiday: boolean | null; // null = follow the calendar
  gas: string; // "" = latest stored value
  scale: number;
  soc: string; // "" = what the plan carries over
}
const EMPTY_FORM: Form = { temp: 0, holiday: null, gas: "", scale: 0, soc: "" };

export function Live() {
  const meta = useMeta();
  const health = useApiHealth();
  const online = health.data === true;
  const qc = useQueryClient();

  const [req, setReq] = useState<LivePlanRequest | null>(null);
  useEffect(() => {
    if (meta.data && !req) setReq({ battery: meta.data.battery });
  }, [meta.data, req]);

  const status = useLiveStatus(online);
  const plan = useLivePlan(req, online);
  const log = useLiveLog(online);
  // a plan without what-ifs is saved to the track record on the server: reload the log after each new plan
  const madeAt = plan.data?.made_at_utc;
  useEffect(() => {
    if (madeAt) qc.invalidateQueries({ queryKey: ["live-log"] });
  }, [madeAt, qc]);
  const [form, setForm] = useState<Form>(EMPTY_FORM);

  const refresh = useMutation({
    mutationFn: () => refreshLive(false),
    onSuccess: (s) => {
      qc.setQueryData(["live-status"], s);
      qc.invalidateQueries({ queryKey: ["live-plan"] });
      qc.invalidateQueries({ queryKey: ["live-log"] });
    },
  });
  const elapsed = useElapsed(refresh.isPending);

  if (health.isLoading) return <p className="status">Looking for the planning service…</p>;
  if (!online) return <Offline />;
  if (meta.isError) return <p className="status error">The battery settings are missing. Run “python -m src.export.export_web” in the project folder, then reload.</p>;

  const p = plan.data;
  const sources = status.data?.sources ?? p?.sources ?? [];
  const delivery = p?.delivery_date ?? status.data?.delivery_date;

  const replan = () => {
    if (!meta.data) return;
    const gas = form.gas.trim() === "" ? null : Number(form.gas);
    const soc = form.soc.trim() === "" ? undefined : Number(form.soc);
    setReq({
      battery: meta.data.battery,
      ...(soc != null && isFinite(soc) ? { soc_start_mwh: soc } : {}),
      overrides: { temp_shift_c: form.temp, is_holiday: form.holiday, gas_eur_mwh: gas != null && isFinite(gas) ? gas : null, demand_scale_pct: form.scale },
    });
  };

  return (
    <>
      <h1 className="statement">{delivery ? `Plan for ${fmtLongDate(delivery)}` : "Plan for tomorrow"}</h1>
      {p && (
        <p className="live-made">
          Made {atDayTime(p.made_at_utc)} from the data known at {p.issue_time_local}.
          {p.is_holiday && ` ${p.holiday_name ?? "A public holiday"}.`}
          {p.event_name && ` ${p.event_name}.`}
        </p>
      )}

      <div className="live-status" aria-label="Data status">
        <div className="chips">
          {sources.length === 0 && <span className="note">{status.isLoading ? "Checking the data…" : "No data status yet."}</span>}
          {sources.map((s) => (
            <span key={s.source} className={`chip ${sourceTone(s)}`} title={`${s.message || (s.ok ? "Up to date" : "Missing")}\nLast data: ${atDayTime(s.last_timestamp_utc)}`}>
              {s.label}
              <small>{s.last_timestamp_utc ? atDayTime(s.last_timestamp_utc) : "no data"}</small>
            </span>
          ))}
        </div>
        <button type="button" className="btn" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          {refresh.isPending ? "Downloading…" : "Get today’s data"}
        </button>
        {refresh.isPending && <p className="live-progress">Downloading today’s data, this takes 1–3 minutes… ({elapsed} s)</p>}
        {refresh.isError && <p className="live-progress status error">The download failed: {(refresh.error as Error).message}</p>}
        {status.data?.fetched_at_utc && !refresh.isPending && <p className="live-progress">Last download {atDayTime(status.data.fetched_at_utc)}. Hover a source for details.</p>}
      </div>

      <section className="section">
        <h2 className="h2">What if</h2>
        <p className="explain">Change an input and press Re-plan. The forecast and the battery plan are made again with the same models as the test.</p>
        <InputsForm form={form} setForm={setForm} plan={p} capacity={meta.data?.battery.capacity_mwh} />
        <div className="daybar" style={{ marginTop: "1.25rem", marginBottom: 0 }}>
          <button type="button" className="btn" onClick={replan} disabled={!meta.data || plan.isFetching}>
            {plan.isFetching ? "Planning…" : "Re-plan"}
          </button>
          <button type="button" className="btn quiet" onClick={() => setForm(EMPTY_FORM)}>
            Reset inputs
          </button>
        </div>
        {p && p.inputs.length > 0 && (
          <Fold title="The inputs the plan used" hint="Latest known values, with where they come from">
            <InputsTable plan={p} />
          </Fold>
        )}
      </section>

      {plan.isError && <p className="status error">Tomorrow could not be planned: {(plan.error as Error).message}</p>}
      {!p && plan.isLoading && <p className="status">Planning tomorrow…</p>}
      {p && (
        <div style={{ opacity: plan.isFetching ? 0.6 : 1 }}>
          <Result plan={p} />
        </div>
      )}

      <section className="section">
        <h2 className="h2">Track record</h2>
        <p className="explain">Every live plan is kept. Once the real demand and prices are known, the forecast is compared with them.</p>
        <TrackRecord entries={log.data} error={log.isError ? (log.error as Error).message : null} />
      </section>
    </>
  );
}

// ---------- inputs ----------

function InputsForm({ form, setForm, plan, capacity }: { form: Form; setForm: (f: Form) => void; plan: LivePlan | undefined; capacity: number | undefined }) {
  const set = (patch: Partial<Form>) => setForm({ ...form, ...patch });
  const gasNow = plan?.inputs.find((i) => /gas/i.test(i.key))?.values.find((v) => v != null);
  const calendarHoliday = plan ? plan.is_holiday && plan.overrides.is_holiday == null : false;
  const holidayChecked = form.holiday ?? calendarHoliday;
  const signed = (v: number, unit: string) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${dec1(Math.abs(v))} ${unit}`;
  return (
    <div className="live-form">
      <div className="slider">
        <label htmlFor="live-temp">
          <span>Temperature shift</span>
          <output htmlFor="live-temp">{signed(form.temp, "°C")}</output>
        </label>
        <input id="live-temp" type="range" min={-10} max={10} step={0.5} value={form.temp} onChange={(e) => set({ temp: Number(e.target.value) })} />
        <small>Added to tomorrow’s temperature forecast, every hour</small>
      </div>
      <div className="slider">
        <label htmlFor="live-scale">
          <span>Demand correction</span>
          <output htmlFor="live-scale">{signed(form.scale, "%")}</output>
        </label>
        <input id="live-scale" type="range" min={-20} max={20} step={1} value={form.scale} onChange={(e) => set({ scale: Number(e.target.value) })} />
        <small>Scales the demand forecast up or down</small>
      </div>
      <div className="field">
        <label className="check">
          <input type="checkbox" checked={holidayChecked} onChange={(e) => set({ holiday: e.target.checked })} />
          <span>Tomorrow is a holiday</span>
        </label>
        <small>
          {form.holiday == null ? (
            "From the calendar"
          ) : (
            <>
              Set by hand.{" "}
              <button type="button" className="linklike" onClick={() => set({ holiday: null })}>
                Use the calendar
              </button>
            </>
          )}
        </small>
      </div>
      <div className="field">
        <label htmlFor="live-gas">Gas price, EUR/MWh</label>
        <input id="live-gas" type="number" step={0.5} min={0} value={form.gas} placeholder={gasNow != null ? dec2(gasNow) : "latest"} onChange={(e) => set({ gas: e.target.value })} />
        <small>Empty = latest known price</small>
      </div>
      <div className="field">
        <label htmlFor="live-soc">Battery level at midnight, MWh</label>
        <input
          id="live-soc"
          type="number"
          step={1}
          min={0}
          max={capacity}
          value={form.soc}
          placeholder={plan ? dec1(plan.soc_start_mwh) : ""}
          onChange={(e) => set({ soc: e.target.value })}
        />
        <small>Empty = what today’s plan leaves in it{capacity != null ? `, at most ${int(capacity)} MWh` : ""}</small>
      </div>
    </div>
  );
}

function InputsTable({ plan }: { plan: LivePlan }) {
  const labels = plan.blocks.map((b) => b.label);
  return (
    <div className="table-scroll">
      <table className="data">
        <thead>
          <tr>
            <th>Input</th>
            {labels.map((l) => (
              <th key={l} className="r">
                {l}
              </th>
            ))}
            <th>Unit</th>
            <th>Status</th>
            <th>Source</th>
            <th>As of</th>
          </tr>
        </thead>
        <tbody>
          {plan.inputs.map((inp) => (
            <tr key={inp.key}>
              <td>{inp.label}</td>
              {inp.values.length === labels.length ? (
                inp.values.map((v, i) => (
                  <td key={i} className="r">
                    {num(v)}
                  </td>
                ))
              ) : (
                <td className="r" colSpan={labels.length}>
                  {inp.values.map(num).join(", ")}
                </td>
              )}
              <td>{inp.unit}</td>
              <td>
                <span className={`badge ${inputTone[inp.status] ?? "warn"}`}>{inp.status}</span>
              </td>
              <td>{inp.source}</td>
              <td className="num">{atDayTime(inp.as_of)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------- result ----------

function Result({ plan }: { plan: LivePlan }) {
  const s = plan.summary;
  return (
    <section className="section">
      <h2 className="statement long" style={{ marginTop: 0 }}>
        {planSentence(plan)}
      </h2>
      <Figures
        items={[
          { value: `${int(s.energy_to_buy_mwh)} MWh`, label: "to buy at the auction" },
          { value: chf(s.expected_cost_chf), label: "expected cost at forecast prices" },
          { value: chf(s.expected_battery_saving_chf), label: "expected saving from the battery", tone: s.expected_battery_saving_chf >= 0 ? "good" : "bad" },
        ]}
      />
      <BlockCards plan={plan} />
      {plan.warnings.length > 0 && (
        <ul className="live-warnings" aria-label="Warnings">
          {plan.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
      <div className="two-col even" style={{ marginTop: "2.5rem" }}>
        <ContextChart plan={plan} kind="demand" />
        <ContextChart plan={plan} kind="price" />
      </div>
      <div className="folds">
        <Fold title={`The ${plan.bids.length} bids for the auction`} hint="Hour by hour, ready to download">
          <HourTable plan={plan} />
        </Fold>
      </div>
      <p className="note">Prices are in EUR and converted at {dec2(s.eurchf)} CHF per EUR.</p>
    </section>
  );
}

function BlockCards({ plan }: { plan: LivePlan }) {
  return (
    <div className="block-cards">
      {plan.blocks.map((b) => {
        const kind = b.charge_mwh > 0.5 ? "store" : b.discharge_mwh > 0.5 ? "use" : "";
        return (
          <article key={b.block} className={`block-card ${kind}`}>
            <h3>{b.label}</h3>
            <div className="word">{optionWord(b.option)}</div>
            <div className="row">
              <span>Need</span>
              <b>{int(b.demand_fc_mw)} MW</b>
            </div>
            {b.demand_q10_mw != null && b.demand_q90_mw != null && (
              <div className="range">
                {int(b.demand_q10_mw)}–{int(b.demand_q90_mw)}
              </div>
            )}
            <div className="row">
              <span>Price</span>
              <b>{int(b.price_fc)} €</b>
            </div>
            {b.price_q10 != null && b.price_q90 != null && (
              <div className="range">
                {int(b.price_q10)}–{int(b.price_q90)}
              </div>
            )}
            <div className="row">
              <span>Buy</span>
              <span>{int(b.buy_mwh)} MWh</span>
            </div>
            {b.charge_mwh > 0.5 && (
              <div className="row">
                <span>Store</span>
                <span>{int(b.charge_mwh)} MWh</span>
              </div>
            )}
            {b.charge_limit_eur_mwh != null && b.charge_mwh > 0.5 && <div className="range">if ≤ {int(b.charge_limit_eur_mwh)} €/MWh</div>}
            {b.discharge_mwh > 0.5 && (
              <div className="row">
                <span>Use</span>
                <span>{int(b.discharge_mwh)} MWh</span>
              </div>
            )}
            {b.sell_mwh > 0.5 && (
              <div className="row">
                <span>Sell</span>
                <span>{int(b.sell_mwh)} MWh</span>
              </div>
            )}
            <div className="row">
              <span>Battery after</span>
              <span>{int(b.soc_end_mwh)} MWh</span>
            </div>
          </article>
        );
      })}
    </div>
  );
}

/** Last 7 days (what happened) followed by tomorrow's forecast with its band, block by block. */
function ContextChart({ plan, kind }: { plan: LivePlan; kind: "demand" | "price" }) {
  const data = useMemo(() => {
    const recent = [...plan.recent].sort((a, b) => a.date.localeCompare(b.date));
    const nb = plan.blocks.length;
    const pad = (k: number) => Array<number | null>(k).fill(null);
    const labels: string[] = [];
    const dayOf: string[] = [];
    recent.forEach((d) =>
      plan.blocks.forEach((b) => {
        labels.push(`${fmtDayMonth(d.date)} ${b.label}`);
        dayOf.push(d.date);
      }),
    );
    plan.blocks.forEach((b) => {
      labels.push(`Tomorrow ${b.label}`);
      dayOf.push(plan.delivery_date);
    });
    const past = recent.flatMap((d) => {
      const v = kind === "demand" ? d.demand_mw : d.price;
      return Array.from({ length: nb }, (_, i) => v[i] ?? null);
    });
    const r = recent.length * nb;
    const fc = plan.blocks.map((b) => (kind === "demand" ? b.demand_fc_mw : b.price_fc));
    const lo = plan.blocks.map((b) => (kind === "demand" ? b.demand_q10_mw : b.price_q10));
    const hi = plan.blocks.map((b) => (kind === "demand" ? b.demand_q90_mw : b.price_q90));
    const naive = plan.blocks.map((b) => (kind === "demand" ? b.demand_naive_mw : b.price_naive));
    return {
      labels,
      ticks: labels.map((_, i) => i).filter((i) => i % nb === 0),
      dayOf,
      actual: [...past, ...pad(nb)],
      fc: [...pad(r), ...fc],
      naive: [...pad(r), ...naive],
      lo: [...pad(r), ...lo],
      hi: [...pad(r), ...hi],
    };
  }, [plan, kind]);

  const color = kind === "demand" ? "var(--demand)" : "var(--price)";
  const hasData = [...data.actual, ...data.fc].some((v) => v != null);
  return (
    <div>
      <h3>{kind === "demand" ? "Demand, MW" : "Price, EUR/MWh"}</h3>
      {hasData ? (
        <LineChart
          labels={data.labels}
          ariaLabel={kind === "demand" ? "Demand of the last seven days and tomorrow's forecast" : "Price of the last seven days and tomorrow's forecast"}
          series={[
            { key: "actual", name: "What happened", values: data.actual, color: "var(--ink)", width: 1.5 },
            { key: "naive", name: "Same day last week", values: data.naive, color: "var(--ink-3)", width: 1.25, dash: "4 3" },
            { key: "fc", name: "Forecast", values: data.fc, color, width: 2.5 },
          ]}
          band={{ lo: data.lo, hi: data.hi, color: kind === "demand" ? "var(--saving-tint)" : "var(--price-tint)" }}
          xTicks={data.ticks}
          xTickFormat={(_, i) => (data.dayOf[i] === plan.delivery_date ? "Tmrw" : fmtDayMonth(data.dayOf[i]))}
          directLabels={false}
          height={240}
          marker={false}
        />
      ) : (
        <p className="note">No values to show.</p>
      )}
      <ChartLegend
        items={[
          { name: "What happened", color: "var(--ink)", kind: "thin" },
          { name: "Forecast", color },
          { name: "Likely range", color: kind === "demand" ? "var(--saving-tint)" : "var(--price-tint)", kind: "fill" },
          { name: "Same day last week", color: "var(--ink-3)", kind: "thin" },
        ]}
      />
    </div>
  );
}

function HourTable({ plan }: { plan: LivePlan }) {
  const download = () => {
    const lines = [
      ["delivery_date", "hour_local", "hour_utc", "bid_for", "volume_mwh", "limit_price_eur_mwh"],
      ...plan.bids.map((b) => [
        plan.delivery_date,
        b.hour,
        b.utc,
        b.bid_type === "charge" ? "battery" : "city",
        b.volume_mwh.toFixed(3),
        b.limit_price_eur_mwh == null ? "" : b.limit_price_eur_mwh.toFixed(2),
      ]),
    ];
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.map((r) => r.join(",")).join("\n") + "\n"], { type: "text/csv" }));
    a.download = `bids_live_${plan.delivery_date}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  return (
    <>
      <p className="explain">
        Energy for the city has no price limit: the city must be supplied, whatever the price. Energy for the battery is only bought if the price stays at or
        below the limit.
      </p>
      <div className="daybar" style={{ marginTop: "1rem", marginBottom: 0 }}>
        <button type="button" className="btn quiet" onClick={download} disabled={!plan.bids.length}>
          Download bids (CSV)
        </button>
      </div>
      <div className="table-scroll">
        <table className="data">
          <thead>
            <tr>
              <th>Hour</th>
              <th className="r">Need, MW</th>
              <th className="r">Price forecast</th>
              <th className="r">City bid, MWh</th>
              <th className="r">Battery bid, MWh</th>
              <th className="r">Battery limit, EUR/MWh</th>
              <th className="r">Battery use, MWh</th>
              <th className="r">Battery level, MWh</th>
            </tr>
          </thead>
          <tbody>
            {plan.hours.map((h) => (
              <tr key={h.utc}>
                <td className="num">{h.hour}</td>
                <td className="r">{int(h.demand_fc_mw)}</td>
                <td className="r">{dec1(h.price_fc)}</td>
                <td className="r">{dec1(h.demand_bid_mwh)}</td>
                <td className="r">{h.charge_bid_mwh > 0.05 ? dec1(h.charge_bid_mwh) : "–"}</td>
                <td className="r">{h.charge_bid_mwh > 0.05 ? (h.charge_limit_eur_mwh == null ? "no limit" : dec2(h.charge_limit_eur_mwh)) : "–"}</td>
                <td className="r">{h.planned_discharge_mwh > 0.05 ? dec1(h.planned_discharge_mwh) : "–"}</td>
                <td className="r">{dec1(h.soc_mwh)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ---------- track record ----------

function errors(e: LiveLogEntry) {
  const d = e.blocks.filter((b) => b.demand_actual_mw != null).map((b) => Math.abs(b.demand_fc_mw - (b.demand_actual_mw as number)));
  const p = e.blocks.filter((b) => b.price_actual != null).map((b) => Math.abs(b.price_fc - (b.price_actual as number)));
  return { demand: mean(d), price: mean(p), nDemand: d.length, nPrice: p.length };
}

function TrackRecord({ entries, error }: { entries: LiveLogEntry[] | undefined; error: string | null }) {
  if (error) return <p className="status error">The track record could not be loaded: {error}</p>;
  if (!entries) return <p className="status">Loading…</p>;
  if (!entries.length) return <p className="note">No live plans yet. The first one appears here after the first plan.</p>;
  const rows = [...entries].sort((a, b) => b.delivery_date.localeCompare(a.delivery_date) || b.made_at_utc.localeCompare(a.made_at_utc));
  return (
    <div className="table-scroll" style={{ maxWidth: "56rem" }}>
      <table className="data">
        <thead>
          <tr>
            <th>Delivery day</th>
            <th>Made</th>
            <th className="r">To buy, MWh</th>
            <th className="r">Expected cost</th>
            <th className="r">Demand error, MW</th>
            <th className="r">Price error, EUR/MWh</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => {
            const er = errors(e);
            const n = e.blocks.length;
            const part = (k: number) => (k < n ? <span className="sub"> ({k} of {n} blocks)</span> : null);
            return (
              <tr key={`${e.delivery_date}-${e.made_at_utc}`}>
                <td>{fmtLongDate(e.delivery_date)}</td>
                <td className="num">{atDayTime(e.made_at_utc)}</td>
                <td className="r">{int(e.summary.energy_to_buy_mwh)}</td>
                <td className="r">{chf(e.summary.expected_cost_chf)}</td>
                {er.demand == null && er.price == null ? (
                  <td className="r note" colSpan={2}>
                    waiting for actuals
                  </td>
                ) : (
                  <>
                    <td className="r">
                      {er.demand == null ? "waiting" : int(er.demand)}
                      {er.demand != null && part(er.nDemand)}
                    </td>
                    <td className="r">
                      {er.price == null ? "waiting" : dec1(er.price)}
                      {er.price != null && part(er.nPrice)}
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="note">Error = mean absolute difference between forecast and actual over the blocks already known.</p>
    </div>
  );
}

// ---------- no service ----------

function Offline() {
  return (
    <>
      <h1 className="statement">Plan tomorrow from today’s data.</h1>
      <div className="offline">
        <p>
          <strong>The planning service is not running.</strong> This page downloads today’s data and runs the forecast models, which needs Python. Start it in
          the project folder, and this page connects by itself within 15 seconds. The other pages work without it.
        </p>
        <StartCommands />
      </div>
    </>
  );
}

