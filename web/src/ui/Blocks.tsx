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

/** The box at the top of every page: what the page shows and how to use it. */
export function PageIntro({ title, what, how }: { title: string; what: ReactNode; how?: ReactNode }) {
  return (
    <div className="intro">
      <h1 className="intro-title">{title}</h1>
      <p>
        <b>What this page shows:</b> {what}
      </p>
      {how && (
        <p>
          <b>How to use it:</b> {how}
        </p>
      )}
    </div>
  );
}

/** A numbered section heading, so each page reads as a short sequence of steps. */
export function Step({ n, title, hint }: { n: number | string; title: string; hint?: ReactNode }) {
  return (
    <div className="step">
      <h2 className="step-title">
        <span className="step-num" aria-hidden="true">
          {n}
        </span>
        {title}
      </h2>
      {hint && <p className="explain">{hint}</p>}
    </div>
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
