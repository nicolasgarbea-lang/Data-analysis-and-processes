import type { Meta } from "../data/types";
import { addDays, fmtLongDate } from "../lib/format";

/** Previous / next buttons around a date field, limited to the days we have plans for. */
export function DayPicker({ meta, date, onChange }: { meta: Meta; date: string; onChange: (d: string) => void }) {
  const first = meta.days[0].date;
  const last = meta.days[meta.days.length - 1].date;
  const day = meta.days.find((d) => d.date === date);
  const planned = fmtLongDate(addDays(date, -1)).split(" ")[0];
  return (
    <div className="daybar">
      <div className="stepper">
        <button type="button" onClick={() => onChange(addDays(date, -1))} disabled={date <= first} aria-label="Previous day">
          ‹
        </button>
        <input
          type="date"
          aria-label="Delivery day"
          value={date}
          min={first}
          max={last}
          onChange={(e) => {
            const v = e.target.value;
            if (v >= first && v <= last) onChange(v);
          }}
        />
        <button type="button" onClick={() => onChange(addDays(date, 1))} disabled={date >= last} aria-label="Next day">
          ›
        </button>
      </div>
      <span className="when">
        {fmtLongDate(date)}, planned on {planned} at {meta.forecast_time_local}
      </span>
      {day && <span className="tag">{day.split === "test" ? "Test month" : "Validation month"}</span>}
      {day?.is_holiday && <span className="tag">Public holiday</span>}
      {day && day.hours !== 24 && <span className="tag">{day.hours}-hour day (clock change)</span>}
    </div>
  );
}

export function defaultDate(meta: Meta) {
  return meta.days.find((d) => d.split === "test")?.date ?? meta.days[0].date;
}
