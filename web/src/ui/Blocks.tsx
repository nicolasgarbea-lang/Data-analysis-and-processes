import type { ReactNode } from "react";

/** Up to three key numbers in a row, each with a short plain label under it. */
export function Figures({ items }: { items: { value: string; label: ReactNode; tone?: "good" | "bad" }[] }) {
  return (
    <dl className="figures">
      {items.map((it, i) => (
        <div key={i} className={it.tone}>
          <dt>{it.label}</dt>
          <dd>{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** A closed section the reader can open for the detail. */
export function Fold({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <details className="fold">
      <summary>
        <span>
          {title}
          {hint && <small>{hint}</small>}
        </span>
      </summary>
      <div className="fold-body">{children}</div>
    </details>
  );
}
