import type { BatterySettings } from "../data/types";
import { dec1, int, pct } from "../lib/format";

/** A battery park: `units` identical batteries. Power and capacity are per unit; the other settings are shared. */
export interface BatteryPark {
  units: number;
  unit: BatterySettings;
}

export const parkFrom = (b: BatterySettings): BatteryPark => ({ units: 1, unit: { ...b } });

/** What the optimiser sees: the units act as one big battery (same efficiency, limits and wear). */
export function parkSettings(p: BatteryPark): BatterySettings {
  return { ...p.unit, power_mw: p.unit.power_mw * p.units, capacity_mwh: p.unit.capacity_mwh * p.units };
}

export const sameBattery = (a: BatterySettings, b: BatterySettings) => JSON.stringify(a) === JSON.stringify(b);

interface SliderProps {
  id: string;
  label: string;
  hint?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  show: (v: number) => string;
  onChange: (v: number) => void;
}

export function Slider({ id, label, hint, value, min, max, step, show, onChange }: SliderProps) {
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

/** The battery controls used on every page that plans with a battery. */
export function BatteryControls({ park, onChange, standard, idPrefix }: { park: BatteryPark; onChange: (p: BatteryPark) => void; standard: BatterySettings; idPrefix: string }) {
  const u = park.unit;
  const setUnit = (patch: Partial<BatterySettings>) => onChange({ ...park, unit: { ...u, ...patch } });
  const total = parkSettings(park);
  const changed = !sameBattery(total, standard);
  const id = (s: string) => `${idPrefix}-${s}`;
  return (
    <>
      <p className="park-total">
        <b>
          {int(total.power_mw)} MW / {int(total.capacity_mwh)} MWh
        </b>{" "}
        in total{park.units > 1 ? ` (${park.units} × ${int(u.power_mw)} MW / ${int(u.capacity_mwh)} MWh)` : ""}, usable {int(total.capacity_mwh * (u.soc_max_frac - u.soc_min_frac))} MWh
      </p>
      <div className="sliders">
        <Slider
          id={id("units")}
          label="Number of batteries"
          hint="Identical batteries, planned together as one"
          value={park.units}
          min={1}
          max={10}
          step={1}
          show={(v) => `${v}`}
          onChange={(v) => onChange({ ...park, units: v })}
        />
        <Slider id={id("power")} label="Power, each" hint="How fast it charges or empties" value={u.power_mw} min={1} max={100} step={1} show={(v) => `${v} MW`} onChange={(v) => setUnit({ power_mw: v })} />
        <Slider
          id={id("capacity")}
          label="Capacity, each"
          hint={`Full power for ${dec1(u.capacity_mwh / u.power_mw)} hours`}
          value={u.capacity_mwh}
          min={2}
          max={200}
          step={2}
          show={(v) => `${v} MWh`}
          onChange={(v) => setUnit({ capacity_mwh: v })}
        />
        <Slider
          id={id("eff")}
          label="Round-trip efficiency"
          hint="Share of stored energy that comes back out"
          value={u.round_trip_efficiency}
          min={0.7}
          max={1}
          step={0.01}
          show={(v) => pct(v * 100)}
          onChange={(v) => setUnit({ round_trip_efficiency: v })}
        />
        <details className="mini-fold">
          <summary>More settings: wear, charge limits, cycles, selling</summary>
          <div className="sliders">
            <Slider
              id={id("wear")}
              label="Wear cost"
              hint="Charged for every MWh taken out"
              value={u.wear_cost_eur_per_mwh}
              min={0}
              max={30}
              step={0.5}
              show={(v) => `${dec1(v)} EUR/MWh`}
              onChange={(v) => setUnit({ wear_cost_eur_per_mwh: v })}
            />
            <Slider
              id={id("socmin")}
              label="Lowest charge level"
              value={u.soc_min_frac}
              min={0}
              max={0.4}
              step={0.05}
              show={(v) => pct(v * 100)}
              onChange={(v) => setUnit({ soc_min_frac: Math.min(v, u.soc_max_frac - 0.1) })}
            />
            <Slider
              id={id("socmax")}
              label="Highest charge level"
              value={u.soc_max_frac}
              min={0.6}
              max={1}
              step={0.05}
              show={(v) => pct(v * 100)}
              onChange={(v) => setUnit({ soc_max_frac: Math.max(v, u.soc_min_frac + 0.1) })}
            />
            <Slider
              id={id("cycles")}
              label="Full cycles per day"
              hint="One cycle = the usable capacity delivered once (about 5 % more than one physical cycle)"
              value={u.max_cycles_per_day}
              min={0}
              max={3}
              step={0.5}
              show={(v) => dec1(v)}
              onChange={(v) => setUnit({ max_cycles_per_day: v })}
            />
            <label className="check">
              <input type="checkbox" checked={u.allow_sell} onChange={(e) => setUnit({ allow_sell: e.target.checked })} />
              <span>Allow selling stored energy back to the market</span>
            </label>
          </div>
        </details>
        <div>
          <button type="button" className="btn quiet small" onClick={() => onChange(parkFrom(standard))} disabled={!changed}>
            Reset to {int(standard.power_mw)} MW / {int(standard.capacity_mwh)} MWh
          </button>
        </div>
      </div>
    </>
  );
}
