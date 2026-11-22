import { useEffect, useState } from "react";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { runMonth, useApiHealth, useCustomPlan, useDay, useMeta } from "../data/api";
import { DayRail, RailLegend } from "../charts/DayRail";
import { Card, PageIntro } from "../ui/Blocks";
import { BatteryControls, parkFrom, parkSettings, sameBattery, type BatteryPark } from "../ui/BatteryCard";
import { DayPicker, defaultDate } from "../ui/DayPicker";
import { planSentence } from "../ui/sentence";
import { StartCommands } from "../ui/StartService";
import { chf, dec1, pct } from "../lib/format";

const route = getRouteApi("/battery");

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function Battery() {
  const meta = useMeta();
  const search = route.useSearch();
  const navigate = useNavigate();
  const date = search.date ?? (meta.data ? defaultDate(meta.data) : undefined);
  const base = useDay(date);
  const health = useApiHealth();
  const [park, setPark] = useState<BatteryPark | null>(null);
  useEffect(() => {
    if (meta.data && !park) setPark(parkFrom(meta.data.battery));
  }, [meta.data, park]);
  const battery = park ? parkSettings(park) : null;
  const settled = useDebounced(battery, 250);
  const online = health.data === true;
  const custom = useCustomPlan(date, (settled ?? meta.data?.battery)!, online && !!settled);
  const month = useMutation({ mutationFn: runMonth });
  useEffect(() => month.reset(), [JSON.stringify(settled)]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!meta.data || !date || !park || !battery) return <p className="status">Loading…</p>;
  const plan = online ? custom.data : undefined;
  const changed = !sameBattery(battery, meta.data.battery);

  return (
    <>
      <PageIntro
        title="Battery simulator"
        what={
          <>
            what a <b>different battery</b> (or several) would have saved on the test month. Only the battery changes; the forecasts stay the same, and the
            savings are the battery’s part only.
          </>
        }
        how="set the battery on the left, press Run October, then look at one day."
      />

      <div className="dash">
        <aside className="dash-side">
          <Card n={1} title="Choose the battery">
            <BatteryControls park={park} onChange={setPark} standard={meta.data.battery} idPrefix="sim" />
          </Card>
        </aside>

        <div className="dash-main">
          <Card n={2} title="October with this battery" hint="Plans and settles all 31 days of the test month with the real prices.">
            {!online ? (
              <Offline checking={health.isLoading} />
            ) : (
              <>
                <div className="card-row">
                  <button type="button" className="btn" onClick={() => month.mutate(battery)} disabled={month.isPending}>
                    {month.isPending ? "Running October…" : "Run October"}
                  </button>
                  {!month.data && !month.isPending && <span className="card-hint">Takes a few seconds.</span>}
                </div>
                {month.isError && <p className="status error">October could not be run: {(month.error as Error).message}</p>}
                {month.data && (
                  <dl className="figures four">
                    <div className="good">
                      <dt>saved by this battery in October</dt>
                      <dd>{chf(month.data.battery_value_chf)}</dd>
                    </div>
                    <div>
                      <dt>of the best possible ({chf(month.data.ceiling_battery_value_chf)} if prices had been known)</dt>
                      <dd>{pct((100 * month.data.battery_value_chf) / month.data.ceiling_battery_value_chf)}</dd>
                    </div>
                    <div>
                      <dt>saved per MWh of capacity, to compare sizes</dt>
                      <dd>{chf(month.data.battery_value_chf / battery.capacity_mwh)}</dd>
                    </div>
                    <div>
                      <dt>full cycles in the month (max {dec1(battery.max_cycles_per_day)} a day)</dt>
                      <dd>{dec1(month.data.cycles)}</dd>
                    </div>
                  </dl>
                )}
                <p className="note">The battery is assumed too small to move the market price. For a very large battery that is too kind.</p>
              </>
            )}
          </Card>

          <Card n={3} title="One day with this battery" hint="When the battery stores (blue) and uses (orange) energy, against the price.">
            <DayPicker meta={meta.data} date={date} onChange={(d) => navigate({ to: "/battery", search: { date: d } })} />
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
                <p className="sentence">{planSentence(plan)}</p>
                <div className="rail-wrap" style={{ opacity: custom.isFetching ? 0.6 : 1 }}>
                  <DayRail plan={plan} />
                </div>
                <RailLegend showActual />
                {base.data && (
                  <p className="note">
                    On this day this battery saved <b>{chf(plan.summary.realised_battery_saving_chf)}</b>.
                    {changed && ` The standard ${meta.data.battery.power_mw} MW battery saved ${chf(base.data.summary.realised_battery_saving_chf)}.`}
                  </p>
                )}
              </>
            )}
          </Card>
        </div>
      </div>
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
