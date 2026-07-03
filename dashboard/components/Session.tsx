"use client";

import * as React from "react";
import { Pill } from "@/components/ui";
import type { Session, SessionPitch } from "@/lib/data";
import { cad, num, pct, price, qty } from "@/lib/format";

// This view is for a person, not a debugger: every card leads with one plain
// sentence about what happened and why. The math is still here — tucked behind
// "Show the numbers" — so nothing is hidden, it's just not in your face.

type Bucket = "funded" | "vetoed" | "considered";

function bucketOf(p: SessionPitch): Bucket {
  if (p.status === "funded") return "funded";
  if (p.status === "vetoed") return "vetoed";
  return "considered"; // "passed" + advisory "shadow"
}

function statusTone(s: string) {
  return s === "funded" ? "good" : s === "vetoed" ? "bad" : "warn";
}

function divisionTone(status: string) {
  if (status.startsWith("pitched")) return "cyan";
  if (status.startsWith("floor")) return "good";
  if (status.startsWith("disabled")) return "default";
  return "warn";
}

// Turn a risk-manager objection into something a human understands.
function plainVeto(objections: string[]): string {
  const j = objections.join(" ").toLowerCase();
  if (j.includes("cost")) return "the expected gain didn’t cover the trading cost — not worth it.";
  if (j.includes("liquid")) return "the market’s too thin to trade our size cleanly.";
  if (j.includes("loss") || j.includes("cap") || j.includes("size")) return "it would breach a risk limit.";
  if (j.includes("stop")) return "the stop-loss wasn’t solid enough.";
  return objections[0] || "the risk manager blocked it.";
}

// Turn a raw execution error into one plain sentence.
function plainExecError(err: string | null): string {
  if (!err) return "the exchange did not confirm a fill — no money moved.";
  if (err.toLowerCase().includes("no market") || err.toLowerCase().includes("unknown asset pair"))
    return "Kraken doesn’t list a market this account can trade for this coin, so the order can’t exist — no money moved.";
  return `the order failed — no money moved. (${err})`;
}

function headline(
  p: SessionPitch,
  target: number | null,
  notFilled: boolean,
  execError: string | null,
): { icon: string; text: string } {
  if (p.status === "funded") {
    if (notFilled) {
      return {
        icon: "⚠️",
        text: `Tried to buy ${cad(p.capital_required)} of ${p.symbol}, but ${plainExecError(execError)}`,
      };
    }
    const t = target !== null ? ` We think it’s worth about ${price(target)} — ${pct(p.expected_return)} higher.` : "";
    return { icon: "✅", text: `Bought ${cad(p.capital_required)} of ${p.symbol}.${t}` };
  }
  if (p.status === "vetoed") {
    return { icon: "✖", text: `Skipped ${p.symbol} — ${plainVeto(p.risk_objections)}` };
  }
  if (p.status === "shadow") {
    return { icon: "👁", text: `Watching ${p.symbol} — a new strategy still proving itself, so no real money yet.` };
  }
  return { icon: "➖", text: `Looked at ${p.symbol}, but holding the cash floor was the better bet today.` };
}

function Metric({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className={`num text-sm ${tone ?? "text-slate-200"}`}>{value}</div>
    </div>
  );
}

function PitchCard({
  p,
  notFilled = false,
  execError = null,
}: {
  p: SessionPitch;
  notFilled?: boolean;
  execError?: string | null;
}) {
  const px = typeof p.features?.price === "number" ? p.features.price : null;
  const hasPlan = px !== null && px > 0;
  const target = hasPlan ? px * (1 + p.expected_return) : null;
  const units = hasPlan ? p.capital_required / px : null;
  const funded = p.status === "funded" && !notFilled;
  const h = headline(p, target, notFilled, execError);

  return (
    <div className="glass hud p-4">
      {/* one human sentence, first */}
      <div className="flex items-start gap-2.5">
        <span className="text-lg leading-none">{h.icon}</span>
        <div className="min-w-0 flex-1">
          <p className="text-[15px] leading-snug text-slate-100">{h.text}</p>
          <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
            <span className="capitalize">{p.division}</span>
            <span>·</span>
            <span className="num">{p.symbol}</span>
            <span>·</span>
            <span>{p.venue}</span>
          </div>
        </div>
        {p.status === "funded" && notFilled ? (
          <Pill tone="bad">NOT FILLED</Pill>
        ) : (
          <Pill tone={statusTone(p.status)}>{p.status.toUpperCase()}</Pill>
        )}
      </div>

      {/* the trade plan, only when we actually bought */}
      {funded && hasPlan ? (
        <div className="mt-3 grid grid-cols-2 gap-3 rounded-lg border border-emerald-400/20 bg-emerald-400/[0.05] p-2.5 sm:grid-cols-4">
          <Metric label="Price now" value={price(px)} />
          <Metric label={`≈ shares for ${cad(p.capital_required)}`} value={qty(units)} />
          <Metric label="Our fair value" value={price(target)} tone="text-emerald-300" />
          <Metric label="Upside to target" value={pct(p.expected_return)} tone="text-emerald-400" />
        </div>
      ) : null}

      {/* catalyst news — a real-world reason, if any */}
      {p.news && p.news.length > 0 ? (
        <div className="mt-3 rounded-lg border border-violet-400/20 bg-violet-400/[0.04] p-2.5 text-xs">
          <div className="label mb-1">📰 In the news</div>
          <ul className="space-y-1">
            {p.news.slice(0, 3).map((n, i) => (
              <li key={i} className="text-slate-300">• {n}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* everything quantitative lives here — available, not in the way */}
      <details className="mt-3 text-xs">
        <summary className="cursor-pointer text-slate-500 hover:text-slate-300">Show the numbers</summary>
        <div className="mt-2 grid grid-cols-3 gap-3 sm:grid-cols-6">
          <Metric label="Exp. return" value={pct(p.expected_return)} tone={p.expected_return >= 0 ? "text-emerald-400" : "text-rose-400"} />
          <Metric label="Win prob" value={pct(p.confidence, 0)} />
          <Metric label="Size" value={cad(p.capital_required)} />
          <Metric label="Max loss" value={cad(p.max_loss)} tone="text-rose-300" />
          <Metric label="Est. cost" value={cad(p.expected_cost)} tone="text-amber-300" />
          <Metric label="Horizon" value={`${num(p.horizon_days, 0)}d`} />
        </div>
        {p.risk_approved === false ? (
          <div className="mt-2 text-rose-300">Risk manager vetoed: {p.risk_objections.join("; ")}</div>
        ) : (
          <div className="mt-2 text-emerald-300">Risk manager: cleared the hard checks.</div>
        )}
        {p.ceo_score !== null ? (
          <div className="mt-1 text-slate-500">
            CEO score {num(p.ceo_score, 3)} · trust {num(p.ceo_trust ?? 0, 2)}
            {p.reason ? ` · ${p.reason}` : ""}
          </div>
        ) : null}
        {p.opportunity ? <div className="mt-1 text-slate-400">{p.opportunity}</div> : null}
      </details>
    </div>
  );
}

function FilterChip({
  label, count, active, onClick,
}: { label: string; count: number; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs transition ${
        active
          ? "border-sky-400/50 bg-sky-400/10 text-sky-200"
          : "border-white/10 text-slate-400 hover:border-white/25 hover:text-slate-200"
      }`}
    >
      {label} <span className="num text-slate-500">{count}</span>
    </button>
  );
}

export function SessionView({
  session,
  filled = null,
  execError = null,
  fundedPitchId = null,
}: {
  session: Session | null;
  // For FUND decisions: did the exchange confirm a fill? null = unknown/not a fund.
  filled?: boolean | null;
  execError?: string | null;
  fundedPitchId?: string | null;
}) {
  const [filter, setFilter] = React.useState<"all" | Bucket>("all");

  if (!session || (!session.pitches?.length && !session.divisions?.length)) {
    return (
      <div className="glass p-4 text-sm text-slate-400">
        No session recorded yet — runs appear here after the first checkpoint.
      </div>
    );
  }
  const pitches = session.pitches ?? [];
  const counts = {
    funded: pitches.filter((p) => bucketOf(p) === "funded").length,
    vetoed: pitches.filter((p) => bucketOf(p) === "vetoed").length,
    considered: pitches.filter((p) => bucketOf(p) === "considered").length,
  };
  const shown = filter === "all" ? pitches : pitches.filter((p) => bucketOf(p) === filter);

  return (
    <div className="space-y-4">
      {/* division roll-call */}
      {session.divisions?.length ? (
        <div className="glass p-4">
          <div className="label mb-2">Who showed up</div>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            {session.divisions.map((d) => (
              <div key={d.division} className="flex items-center gap-2">
                <Pill tone={divisionTone(d.status)}>{d.division}</Pill>
                <span className="text-xs text-slate-400">{d.status}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {pitches.length ? (
        <>
          {/* filters + plain-language legend */}
          <div className="flex flex-wrap items-center gap-2">
            <FilterChip label="All" count={pitches.length} active={filter === "all"} onClick={() => setFilter("all")} />
            <FilterChip label="✅ Bought" count={counts.funded} active={filter === "funded"} onClick={() => setFilter("funded")} />
            <FilterChip label="✖ Skipped" count={counts.vetoed} active={filter === "vetoed"} onClick={() => setFilter("vetoed")} />
            <FilterChip label="➖ Considered" count={counts.considered} active={filter === "considered"} onClick={() => setFilter("considered")} />
          </div>
          <details className="text-xs text-slate-500">
            <summary className="cursor-pointer hover:text-slate-300">What do these mean?</summary>
            <ul className="mt-2 space-y-1">
              <li><b className="text-emerald-300">Bought</b> — the CEO put real money into this idea.</li>
              <li><b className="text-rose-300">Not filled</b> — the CEO funded it but the exchange rejected the order (e.g. no CAD market); no money moved.</li>
              <li><b className="text-rose-300">Skipped</b> — the risk manager blocked it (usually the gain didn’t beat the cost, or it broke a risk limit).</li>
              <li><b className="text-amber-300">Considered</b> — a fair idea, but parking the cash in the safe “floor” (interest/yield) was the better bet today.</li>
              <li><b className="text-slate-300">Watching</b> — a new strategy still being validated; it’s logged but never funded with real money yet.</li>
            </ul>
          </details>

          {shown.length ? (
            <div className="space-y-3">
              {shown.map((p) => {
                const isTheFundedPitch =
                  p.status === "funded" && (!fundedPitchId || p.pitch_id === fundedPitchId);
                return (
                  <PitchCard
                    key={p.pitch_id}
                    p={p}
                    notFilled={isTheFundedPitch && filled === false}
                    execError={isTheFundedPitch ? execError : null}
                  />
                );
              })}
            </div>
          ) : (
            <div className="glass p-4 text-sm text-slate-400">Nothing in this category this checkpoint.</div>
          )}
        </>
      ) : (
        <div className="glass p-4 text-sm text-slate-400">
          No ideas cleared the bar this checkpoint, so the CEO stayed in the safe floor. That’s the
          default — doing nothing is usually the right call.
        </div>
      )}
    </div>
  );
}
