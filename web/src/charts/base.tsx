import { useEffect, useRef, useState, type ReactNode } from "react";

/** Width of a container, updated when it resizes. */
export function useWidth<T extends HTMLElement>(fallback = 800) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w && Math.abs(w - width) > 0.5) setWidth(w);
    });
    ro.observe(el);
    setWidth(el.clientWidth || fallback);
    return () => ro.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return [ref, width] as const;
}

export interface TipState {
  x: number;
  y: number;
  title: string;
  rows: [string, string][];
}

export function Tip({ tip }: { tip: TipState | null }) {
  if (!tip) return null;
  return (
    <div className="tip" style={{ left: tip.x, top: tip.y }} role="status">
      <b>{tip.title}</b>
      {tip.rows.map(([k, v]) => (
        <div className="row" key={k}>
          <span>{k}</span>
          <span>{v}</span>
        </div>
      ))}
    </div>
  );
}

/** Round, readable axis ticks between lo and hi. */
export function niceTicks(lo: number, hi: number, count = 4): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  return out;
}

export function Figure({ children, caption }: { children: ReactNode; caption?: ReactNode }) {
  return (
    <figure>
      {children}
      {caption ? <figcaption>{caption}</figcaption> : null}
    </figure>
  );
}

export const COLORS = {
  ink: "var(--ink)",
  ink2: "var(--ink-2)",
  ink3: "var(--ink-3)",
  rule: "var(--rule)",
  ruleSoft: "var(--rule-soft)",
  charge: "var(--charge)",
  use: "var(--use)",
  price: "var(--price)",
  saving: "var(--saving)",
  penalty: "var(--penalty)",
};
