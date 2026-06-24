import * as React from "react";

const toneText: Record<string, string> = {
  default: "text-slate-100",
  good: "text-emerald-400 glow-good",
  bad: "text-rose-400 glow-bad",
  warn: "text-amber-400",
  cyan: "text-sky-300 glow-cyan",
};

export function Stat({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "default" | "good" | "bad" | "warn" | "cyan";
}) {
  return (
    <div className="glass glass-hover p-4">
      <div className="label">{label}</div>
      <div className={`num mt-1.5 text-2xl font-semibold ${toneText[tone]}`}>{value}</div>
      {sub ? <div className="mt-1 text-xs text-slate-400">{sub}</div> : null}
    </div>
  );
}

const pillTone: Record<string, string> = {
  default: "border-white/15 text-slate-300",
  good: "border-emerald-400/30 text-emerald-300 bg-emerald-400/5",
  bad: "border-rose-400/30 text-rose-300 bg-rose-400/5",
  warn: "border-amber-400/30 text-amber-300 bg-amber-400/5",
  cyan: "border-sky-400/30 text-sky-300 bg-sky-400/5",
  violet: "border-violet-400/30 text-violet-300 bg-violet-400/5",
};

export function Pill({ children, tone = "default" }: { children: React.ReactNode; tone?: string }) {
  return <span className={`pill ${pillTone[tone] ?? pillTone.default}`}>{children}</span>;
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
    <section className="mt-10">
      <div className="flex items-center gap-3">
        <span className="h-3 w-1 rounded-full bg-gradient-to-b from-sky-400 to-violet-500" />
        <h2 className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-300">{title}</h2>
      </div>
      {desc ? <p className="mt-1 pl-4 text-xs text-slate-500">{desc}</p> : null}
      <div className="mt-3">{children}</div>
    </section>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="glass p-4 text-sm text-slate-400">{children}</div>;
}

export function Table({ head, children }: { head: string[]; children: React.ReactNode }) {
  return (
    <div className="glass overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/10 text-left">
            {head.map((h) => (
              <th key={h} className="label px-4 py-3">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">{children}</tbody>
      </table>
    </div>
  );
}
