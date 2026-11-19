// Number and date formatting used across the app. Swiss style: 226'499 would be local habit,
// but the report uses a comma, so the app does too.
const nf0 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const int = (v: number | null | undefined) => (v == null || !isFinite(v) ? "–" : nf0.format(Math.round(v)));
export const dec1 = (v: number | null | undefined) => (v == null || !isFinite(v) ? "–" : nf1.format(v));
export const dec2 = (v: number | null | undefined) => (v == null || !isFinite(v) ? "–" : nf2.format(v));
export const chf = (v: number | null | undefined) => (v == null || !isFinite(v) ? "–" : `CHF ${nf0.format(Math.round(v))}`);
export const chfSigned = (v: number | null | undefined) =>
  v == null || !isFinite(v) ? "–" : `${v < 0 ? "−" : "+"}CHF ${nf0.format(Math.abs(Math.round(v)))}`;
export const pct = (v: number | null | undefined, d = 0) =>
  v == null || !isFinite(v) ? "–" : `${v.toFixed(d)} %`;
export const mwh = (v: number) => `${nf0.format(Math.round(v))} MWh`;

const longDate = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
const shortDate = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
const dayMonth = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
const weekday = new Intl.DateTimeFormat("en-GB", { weekday: "long", timeZone: "UTC" });
const asDate = (iso: string) => new Date(`${iso}T00:00:00Z`);
export const fmtLongDate = (iso: string) => longDate.format(asDate(iso));
export const fmtShortDate = (iso: string) => shortDate.format(asDate(iso));
export const fmtDayMonth = (iso: string) => dayMonth.format(asDate(iso));
export const fmtWeekday = (iso: string) => weekday.format(asDate(iso));
export const addDays = (iso: string, n: number) => {
  const d = asDate(iso);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

/** "12–16 and 20–24" */
export const listAnd = (items: string[]) =>
  items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
