import { useEffect, useState } from "react";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { runMonth, useApiHealth, useCustomPlan, useDay, useMeta } from "../data/api";
import type { BatterySettings } from "../data/types";
import { DayRail, RailLegend } from "../charts/DayRail";
import { Fold } from "../ui/Blocks";
import { DayPicker, defaultDate } from "../ui/DayPicker";
import { planSentence } from "../ui/sentence";
import { StartCommands } from "../ui/StartService";
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
      <p className="lede">Move a slider and the day is planned again. Run October to see what that battery would have saved over the month.</p>

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
            <Fold title="More settings" hint="Wear cost, charge limits, cycles, selling back">
              <div className="sliders">
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
              </div>
            </Fold>
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
              <p className="explain">Plans and settles all 31 days of the test month, in a few seconds.</p>
              <p style={{ marginTop: "1rem" }}>
                <button type="button" className="btn" onClick={() => month.mutate(battery)} disabled={month.isPending}>
                  {month.isPending ? "Running October…" : "Run October"}
                </button>
              </p>
              {month.isError && <p className="status error">October could not be run: {(month.error as Error).message}</p>}
              {month.data && (
                <dl className="figures" style={{ gridTemplateColumns: "1fr", marginTop: "1.25rem" }}>
                  <div className="good">
                    <dt>saved by this battery in October</dt>
                    <dd>{chf(month.data.battery_value_chf)}</dd>
                  </div>
                  <div>
                    <dt>
                      {pct((100 * month.data.battery_value_chf) / month.data.ceiling_battery_value_chf)} of the best possible ({chf(month.data.ceiling_battery_value_chf)}), and{" "}
                      {chf(month.data.battery_value_chf / battery.capacity_mwh)} per MWh of capacity
                    </dt>
                    <dd style={{ fontSize: "var(--step-1)" }}>{dec1(month.data.cycles)} cycles</dd>
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
              <DayRail plan={base.data} />
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
              <DayRail plan={plan} />
            </div>
            <RailLegend showActual />
            {base.data && (
              <p className="note" style={{ fontSize: "var(--step-0)" }}>
                On this day this battery saved {chf(plan.summary.realised_battery_saving_chf)}.
                {changed && ` The standard ${meta.data.battery.power_mw} MW battery saved ${chf(base.data.summary.realised_battery_saving_chf)}.`}
              </p>
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
      <StartCommands />
    </div>
  );
}
