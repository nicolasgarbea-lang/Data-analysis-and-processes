import { useEffect, useState } from "react";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { runMonth, useApiHealth, useCustomPlan, useDay, useMeta } from "../data/api";
import type { BatterySettings } from "../data/types";
import { DayRail, RailLegend } from "../charts/DayRail";
import { DayPicker, defaultDate } from "../ui/DayPicker";
import { planSentence } from "../ui/sentence";
import { chf, dec1, int, pct } from "../lib/format";

const route = getRouteApi("/battery");

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

interface SliderProps {
  label: string;
  hint?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  show: (v: number) => string;
  onChange: (v: number) => void;
}

function Slider({ label, hint, value, min, max, step, show, onChange }: SliderProps) {
  const id = label.replace(/\W+/g, "-").toLowerCase();
  return (
    <div className="slider">
      <label htmlFor={id}>
        <span>{label}</span>
        <output htmlFor={id}>{show(value)}</output>
      </label>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      {hint && <small>{hint}</small>}
    </div>
  );
}

export function Battery() {
  const meta = useMeta();
  const search = route.useSearch();
  const navigate = useNavigate();
  const date = search.date ?? (meta.data ? defaultDate(meta.data) : undefined);
  const base = useDay(date);
  const health = useApiHealth();
  const [battery, setBattery] = useState<BatterySettings | null>(null);
  useEffect(() => {
    if (meta.data && !battery) setBattery(meta.data.battery);
  }, [meta.data, battery]);
  const settled = useDebounced(battery, 250);
  const online = health.data === true;
  const custom = useCustomPlan(date, (settled ?? meta.data?.battery) as BatterySettings, online && !!settled);
  const month = useMutation({ mutationFn: runMonth });
  useEffect(() => month.reset(), [settled]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!meta.data || !date || !battery) return <p className="status">Loading…</p>;
  const set = (patch: Partial<BatterySettings>) => setBattery({ ...battery, ...patch });
  const plan = online ? custom.data : undefined;
  const changed = JSON.stringify(battery) !== JSON.stringify(meta.data.battery);
  const hours = battery.capacity_mwh / battery.power_mw;

  return (
    <>
      <h1 className="statement">Try a different battery.</h1>
      <p className="lede">
        Change the battery and the plan for the day is worked out again. Then run the whole of October to see what the new battery would have saved.
      </p>

      <section className="section two-col">
        <div>
          <h2 className="h2">The battery</h2>
          <div className="sliders">
            <Slider label="Power" hint="How fast it can charge or empty" value={battery.power_mw} min={1} max={100} step={1} show={(v) => `${v} MW`} onChange={(v) => set({ power_mw: v })} />
            <Slider
              label="Capacity"
              hint={`Full power for ${dec1(hours)} hours`}
              value={battery.capacity_mwh}
              min={2}
              max={200}
              step={2}
              show={(v) => `${v} MWh`}
              onChange={(v) => set({ capacity_mwh: v })}
            />
            <Slider
              label="Round-trip efficiency"
              hint="Share of stored energy that comes back out"
              value={battery.round_trip_efficiency}
              min={0.7}
              max={1}
              step={0.01}
              show={(v) => pct(v * 100)}
              onChange={(v) => set({ round_trip_efficiency: v })}
            />
            <Slider
              label="Wear cost"
              hint="Charged for every MWh taken out of the battery"
              value={battery.wear_cost_eur_per_mwh}
              min={0}
              max={30}
              step={0.5}
              show={(v) => `${dec1(v)} EUR per MWh`}
              onChange={(v) => set({ wear_cost_eur_per_mwh: v })}
            />
            <Slider
              label="Lowest charge level"
              value={battery.soc_min_frac}
              min={0}
              max={0.4}
              step={0.05}
              show={(v) => pct(v * 100)}
              onChange={(v) => set({ soc_min_frac: Math.min(v, battery.soc_max_frac - 0.1) })}
            />
            <Slider
              label="Highest charge level"
              value={battery.soc_max_frac}
              min={0.6}
              max={1}
              step={0.05}
              show={(v) => pct(v * 100)}
              onChange={(v) => set({ soc_max_frac: Math.max(v, battery.soc_min_frac + 0.1) })}
            />
            <Slider
              label="Full cycles per day"
              hint="One cycle is the usable capacity delivered to the grid once. That is about 5 % more than one physical cycle."
              value={battery.max_cycles_per_day}
              min={0}
              max={3}
              step={0.5}
              show={(v) => dec1(v)}
              onChange={(v) => set({ max_cycles_per_day: v })}
            />
            <label className="check">
              <input type="checkbox" checked={battery.allow_sell} onChange={(e) => set({ allow_sell: e.target.checked })} />
              <span>Allow selling stored energy back to the market</span>
            </label>
            <div>
              <button type="button" className="btn quiet" onClick={() => setBattery(meta.data!.battery)} disabled={!changed}>
                Reset to {meta.data.battery.power_mw} MW / {meta.data.battery.capacity_mwh} MWh
              </button>
            </div>
          </div>
        </div>

        <div>
          <h2 className="h2">October with this battery</h2>
          {!online ? (
            <Offline checking={health.isLoading} />
          ) : (
            <>
              <p className="explain">Plans and settles all 31 days of the test month. It takes a few seconds.</p>
              <p style={{ marginTop: "1rem" }}>
                <button type="button" className="btn" onClick={() => month.mutate(battery)} disabled={month.isPending}>
                  {month.isPending ? "Running October…" : "Run October"}
                </button>
              </p>
              {month.isError && <p className="status error">October could not be run: {(month.error as Error).message}</p>}
              {month.data && (
                <dl className="ledger">
                  <div className="good">
                    <dt>Saved by the battery</dt>
                    <dd>{chf(month.data.battery_value_chf)}</dd>
                  </div>
                  <div>
                    <dt>
                      Best possible for this battery
                      <small>hourly plan with perfect foresight</small>
                    </dt>
                    <dd>{chf(month.data.ceiling_battery_value_chf)}</dd>
                  </div>
                  <div>
                    <dt>Share of the best possible</dt>
                    <dd>{pct((100 * month.data.battery_value_chf) / month.data.ceiling_battery_value_chf)}</dd>
                  </div>
                  <div>
                    <dt>Battery saving per MWh of capacity</dt>
                    <dd>{chf(month.data.battery_value_chf / battery.capacity_mwh)}</dd>
                  </div>
                  <div>
                    <dt>Cycles in the month</dt>
                    <dd>{dec1(month.data.cycles)}</dd>
                  </div>
                  <div className="total">
                    <dt>
                      Total saved against the simple rule
                      <small>better demand forecast plus battery</small>
                    </dt>
                    <dd>{chf(month.data.saving_vs_baseline_chf)}</dd>
                  </div>
                </dl>
              )}
              <p className="note">
                The battery is assumed too small to move the market price. For a very large battery that is too kind.
              </p>
            </>
          )}
        </div>
      </section>

      <section className="section">
        <h2>One day with this battery</h2>
        <div style={{ marginTop: "1rem" }}>
          <DayPicker meta={meta.data} date={date} onChange={(d) => navigate({ to: "/battery", search: { date: d } })} />
        </div>
        {!online && base.data && (
          <>
            <p className="explain">The planning service is not running, so this is the plan with the standard battery.</p>
            <div className="rail-wrap">
              <DayRail plan={base.data} compact />
            </div>
          </>
        )}
        {online && custom.isError && <p className="status error">This battery cannot be planned: {(custom.error as Error).message}</p>}
        {plan && (
          <>
            <p className="lede" style={{ color: "var(--ink)" }}>
              {planSentence(plan)}
            </p>
            <div className="rail-wrap" style={{ opacity: custom.isFetching ? 0.6 : 1 }}>
              <DayRail plan={plan} compact />
            </div>
            <RailLegend showActual compact />
            {base.data && (
              <div className="table-scroll">
                <table className="data" style={{ maxWidth: "44rem" }}>
                  <thead>
                    <tr>
                      <th>On this day</th>
                      <th className="r">Standard battery</th>
                      <th className="r">Your battery</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Stored</td>
                      <td className="r">{int(base.data.summary.charged_mwh)} MWh</td>
                      <td className="r">{int(plan.summary.charged_mwh)} MWh</td>
                    </tr>
                    <tr>
                      <td>Expected saving from the battery</td>
                      <td className="r">{chf(base.data.summary.expected_battery_saving_chf)}</td>
                      <td className="r">{chf(plan.summary.expected_battery_saving_chf)}</td>
                    </tr>
                    <tr>
                      <td>Saving after settlement</td>
                      <td className="r">{chf(base.data.summary.realised_battery_saving_chf)}</td>
                      <td className="r">{chf(plan.summary.realised_battery_saving_chf)}</td>
                    </tr>
                    <tr>
                      <td>Total cost of the day</td>
                      <td className="r">{chf(base.data.summary.realised_cost_chf)}</td>
                      <td className="r">{chf(plan.summary.realised_cost_chf)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>
    </>
  );
}

function Offline({ checking }: { checking: boolean }) {
  if (checking) return <p className="status">Looking for the planning service…</p>;
  return (
    <div className="offline">
      <p>
        <strong>The planning service is not running.</strong> Changing the battery needs the optimiser, which runs in Python. Start it in the project folder, and
        this page connects by itself:
      </p>
      <code>.venv/bin/python -m uvicorn api.server:app --port 8000</code>
    </div>
  );
}
