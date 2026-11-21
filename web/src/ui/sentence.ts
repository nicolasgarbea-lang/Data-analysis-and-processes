import { int, listAnd } from "../lib/format";

/** Only what the sentence reads, so a replayed day (DayPlan) and a live plan (LivePlan) both fit. */
export interface SentencePlan {
  blocks: { label: string; charge_mwh: number; discharge_mwh: number }[];
  summary: { energy_to_buy_mwh: number };
}

/** The plan in one sentence, e.g. "Store 36 MWh at 12–16 and 20–24. Use it at 08–12 and 16–20." */
export function planSentence(plan: SentencePlan): string {
  const store = plan.blocks.filter((b) => b.charge_mwh > 0.5);
  const use = plan.blocks.filter((b) => b.discharge_mwh > 0.5);
  const buy = `Buy ${int(plan.summary.energy_to_buy_mwh)} MWh.`;
  if (!store.length && !use.length) return `${buy} The battery rests.`;
  const s = store.length ? `Store ${int(store.reduce((a, b) => a + b.charge_mwh, 0))} MWh at ${listAnd(store.map((b) => b.label))}.` : "";
  const u = use.length ? `Use ${int(use.reduce((a, b) => a + b.discharge_mwh, 0))} MWh at ${listAnd(use.map((b) => b.label))}.` : "";
  return [buy, s, u].filter(Boolean).join(" ");
}
