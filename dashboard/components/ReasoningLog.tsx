"use client";

import * as React from "react";
import { Pill } from "@/components/ui";
import { SessionView } from "@/components/Session";
import type { Decision, RunRow, Session } from "@/lib/data";
import { ago, cad, divLabel, when } from "@/lib/format";

// Section 3 — WHAT IT CONSIDERED. One card per checkpoint: what was scanned,
// every pitch with the reason it was funded / vetoed / passed over, and the
// CEO's verdict in plain language. Crashed runs appear inline in red — a
// checkpoint that died is part of the story, not a gap in it.

const TRIGGER_LABEL: Record<string, string> = {
  scheduled: "scheduled",
  run_now: "Run-now click",
  wide: "wide scan",
  decide: "manual decide",
  manual: "manual",
};

function kindTone(kind: string) {
  if (kind === "fund") return "good";
  if (kind === "hold") return "warn";
  return "default";
}

type Item =
  | { type: "decision"; at: string; decision: Decision; run: RunRow | null }
  | { type: "crash"; at: string; run: RunRow };

export function ReasoningLog({ decisions, runs }: { decisions: Decision[]; runs: RunRow[] }) {
  const runByDecision = new Map<string, RunRow>();
  for (const r of runs) if (r.decision_id) runByDecision.set(r.decision_id, r);

  const items: Item[] = [
    ...decisions.map((d) => ({
      type: "decision" as const,
      at: d.created_at,
      decision: d,
      run: runByDecision.get(d.decision_id) ?? null,
    })),
    ...runs
      .filter((r) => r.status === "crashed")
      .map((r) => ({ type: "crash" as const, at: r.started_at, run: r })),
  ]
    .sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime())
    .slice(0, 10);

  if (items.length === 0) {
    return (
      <div className="glass p-4 text-sm text-slate-400">
        No checkpoints yet — the reasoning trail fills in after the first run.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item, i) => {
        if (item.type === "crash") {
          return (
            <div
              key={item.run.run_id}
              className="rounded-xl border border-rose-400/40 bg-rose-400/[0.06] p-4"
            >
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Pill tone="bad">⚠ RUN CRASHED</Pill>
                <span className="text-xs text-slate-400">
                  {TRIGGER_LABEL[item.run.trigger] ?? item.run.trigger} · {when(item.at)} (
                  {ago(item.at)})
                </span>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-rose-200">
                This checkpoint died before finishing.{" "}
                {item.run.error ? `Error: ${item.run.error}` : "No error text was captured."} Any
                fill it made before crashing is in the Executed section; the traceback is in the
                PC's logs.
              </p>
            </div>
          );
        }

        const d = item.decision;
        const session: Session | null =
          d.ranked && typeof d.ranked === "object" && !Array.isArray(d.ranked)
            ? (d.ranked as Session)
            : null;
        const nPitches = session?.pitches?.length ?? 0;
        const trigger = item.run ? TRIGGER_LABEL[item.run.trigger] ?? item.run.trigger : null;

        return (
          <details key={d.decision_id} className="group glass hud" open={i === 0}>
            <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 p-4 select-none">
              <Pill tone={kindTone(d.kind)}>{d.kind.toUpperCase()}</Pill>
              {d.division ? (
                <span className="text-sm capitalize text-slate-200">{divLabel(d.division)}</span>
              ) : null}
              {d.size_cad > 0 ? <span className="num text-sm text-white">{cad(d.size_cad)}</span> : null}
              <Pill tone={d.live ? "bad" : "default"}>{d.live ? "LIVE" : "dry-run"}</Pill>
              <span className="text-xs text-slate-500">
                {trigger ? `${trigger} · ` : ""}
                {nPitches ? `${nPitches} idea${nPitches === 1 ? "" : "s"} weighed · ` : ""}
                {when(d.created_at)}
              </span>
              <span className="ml-auto text-[10px] uppercase tracking-widest text-slate-500 group-open:hidden">
                expand ▾
              </span>
              <span className="ml-auto hidden text-[10px] uppercase tracking-widest text-slate-500 group-open:inline">
                collapse ▴
              </span>
            </summary>
            <div className="border-t border-white/10 p-4">
              <p className="text-[15px] leading-relaxed text-slate-100">
                {d.rationale || "(no rationale recorded)"}
              </p>
              <div className="mt-3">
                <SessionView session={session} />
              </div>
            </div>
          </details>
        );
      })}
    </div>
  );
}
