import * as React from "react";

export function Stat({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "default" | "good" | "bad" | "warn";
}) {
  const color =
    tone === "good" ? "text-good" : tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : "text-white";
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${color}`}>{value}</div>
      {sub ? <div className="mt-1 text-xs text-muted">{sub}</div> : null}
    </div>
  );
}

export function Pill({ children, tone = "default" }: { children: React.ReactNode; tone?: string }) {
  const map: Record<string, string> = {
    default: "border-edge text-muted",
    good: "border-good/40 text-good",
    bad: "border-bad/40 text-bad",
    warn: "border-warn/40 text-warn",
    accent: "border-accent/40 text-accent",
  };
  return <span className={`pill ${map[tone] ?? map.default}`}>{children}</span>;
}

export function Section({
  title,
  desc,
  children,
}: {
  title: string;
  desc?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-8">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">{title}</h2>
      {desc ? <p className="mt-1 text-xs text-muted/80">{desc}</p> : null}
      <div className="mt-3">{children}</div>
    </section>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="card text-sm text-muted">{children}</div>;
}

export function Table({ head, children }: { head: string[]; children: React.ReactNode }) {
  return (
    <div className="card overflow-x-auto p-0">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-edge text-left text-xs uppercase tracking-wide text-muted">
            {head.map((h) => (
              <th key={h} className="px-4 py-3 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-edge/60">{children}</tbody>
      </table>
    </div>
  );
}
