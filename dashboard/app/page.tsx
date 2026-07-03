import Link from "next/link";
import { Empty, Pill, Section, Stat, Table } from "@/components/ui";
import { Refresher } from "@/components/Refresher";
import { SessionHistory } from "@/components/SessionHistory";
import { PortfolioOverview } from "@/components/PortfolioOverview";
import { EquityChart } from "@/components/EquityChart";
import { AskBoardroom } from "@/components/AskBoardroom";
import { RunNow } from "@/components/RunNow";
import { HealthStrip } from "@/components/HealthStrip";
import { Executed } from "@/components/Executed";
import { PositionsView } from "@/components/PositionsView";
import { ReasoningLog } from "@/components/ReasoningLog";
import { AuditLog } from "@/components/AuditLog";
import {
  calibrationMean,
  equitySeries,
  loadDashboard,
  rollupOutcomes,
  type Session,
  type StrategyReview,
} from "@/lib/data";
import { deposits } from "@/lib/deposits";
import { nextCheckpointMultiIso } from "@/lib/schedule";
import { ago, cad, divLabel, pct, when } from "@/lib/format";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function StrategistCard({ review }: { review: StrategyReview | null }) {
  if (!review) return null;
  return (
    <div className="glass hud mb-3 p-4">
      <div className="flex items-center gap-2">
        <span>🧮</span>
        <span className="label">CFO&apos;s standing view</span>
        <span className="ml-auto text-xs text-slate-500">{ago(review.created_at)}</span>
      </div>
      <div className="mt-1.5 text-sm font-semibold text-sky-300">{review.headline}</div>
      <details className="mt-1 text-sm text-slate-300">
        <summary className="cursor-pointer text-xs text-slate-500 hover:text-slate-300">
          full review
        </summary>
        <p className="mt-2 leading-relaxed">{review.narrative}</p>
        {review.recommendations?.length ? (
          <div className="mt-3 space-y-2">
            {review.recommendations.map((r, i) => (
              <div key={i} className="flex items-start gap-2 text-sm">
                <Pill tone={r.requires_human ? "warn" : "good"}>
                  {r.requires_human ? "needs you" : "auto"}
                </Pill>
                <span className="text-slate-300">{r.suggestion}</span>
              </div>
            ))}
          </div>
        ) : null}
      </details>
    </div>
  );
}

export default async function Page() {
  const d = await loadDashboard();
  const dep = deposits();

  if (!d.configured) {
    const urlSet = Boolean(process.env.SUPABASE_URL);
    const keySet = Boolean(process.env.SUPABASE_SERVICE_KEY);
    const row = (name: string, ok: boolean) => (
      <div className="flex items-center gap-2">
        <span className={ok ? "text-emerald-400" : "text-rose-400"}>{ok ? "✓ set" : "✗ MISSING"}</span>
        <code className="text-sky-300">{name}</code>
      </div>
    );
    return (
      <main className="mx-auto max-w-6xl px-5 py-10">
        <h1 className="title-grad text-3xl font-bold">Boardroom</h1>
        <div className="glass mt-6 space-y-2 p-5 text-sm">
          <div className="text-slate-400">Not connected to Supabase. Detected at runtime:</div>
          {row("SUPABASE_URL", urlSet)}
          {row("SUPABASE_SERVICE_KEY", keySet)}
          <div className="pt-2 text-xs text-slate-500">
            Add any MISSING variable in Vercel → Settings → Environment Variables with the{" "}
            <b>Production</b> scope checked, then redeploy with build cache off.
          </div>
        </div>
      </main>
    );
  }

  const roll = rollupOutcomes(d.outcomes);
  const perf = d.performance?.payload ?? null;

  // Equity: real synced Kraken cash when available, else baseline + realized P&L.
  // Crypto-only — equities are sunset, so IBKR cash no longer counts here.
  const krakenSynced = d.kraken_cash_cad !== null;
  const balancesSynced = d.balances_at !== null && krakenSynced;
  const equity = balancesSynced ? (d.kraken_cash_cad as number) : dep.total + roll.pnl;

  const latest = d.decisions[0] ?? null;
  const checkpointTimes = process.env.CHECKPOINT_TIMES || process.env.CHECKPOINT_UTC || "13:30,19:00";
  const hb = d.audit.find((a) => a.event === "scheduler_heartbeat");
  const hbNext = (hb?.payload as any)?.next_run_at as string | undefined;
  const envArmed = (process.env.LIVE_TRADING || "").toLowerCase() === "true";
  const tradedLive = Boolean(latest?.live) || d.fills.some((f) => f.is_live);
  const armedLive =
    tradedLive || d.live_armed || Boolean((hb?.payload as any)?.live) || envArmed;
  const targetIso =
    hbNext && new Date(hbNext).getTime() > Date.now()
      ? hbNext
      : nextCheckpointMultiIso(checkpointTimes);

  const lastRun = d.runs[0] ?? null;
  const latestRecon = d.runs.find((r) => r.recon)?.recon ?? null;
  const latestSession: Session | null =
    latest && latest.ranked && typeof latest.ranked === "object" && !Array.isArray(latest.ranked)
      ? (latest.ranked as Session)
      : null;
  const series = equitySeries(d.outcomes, dep.total);
  const attribution = perf?.attribution ?? roll.attribution;
  const asOf = new Date().toLocaleTimeString("en-CA", { hour: "2-digit", minute: "2-digit" });

  return (
    <main className="mx-auto max-w-6xl px-5 py-8">
      {/* Header */}
      <header className="flex flex-wrap items-center gap-4">
        <div>
          <h1 className="title-grad text-3xl font-bold tracking-tight">BOARDROOM</h1>
          <p className="mt-1 text-xs uppercase tracking-[0.25em] text-slate-500">
            autonomous crypto capital allocator
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2 text-[11px] text-slate-500">
          <Link
            href="/docs"
            className="rounded-full border border-white/15 px-2.5 py-1 text-slate-300 hover:border-sky-400/40 hover:text-sky-300"
          >
            📖 Docs
          </Link>
          <span>as of {asOf}</span>
          <span className="text-slate-600">·</span>
          <Refresher />
        </div>
      </header>

      {d.error ? (
        <div className="glass mt-4 border border-rose-400/30 p-3 text-sm text-rose-300">
          Query error: {d.error}
        </div>
      ) : null}

      {/* Health strip — is the machine alive, armed, and telling the truth? */}
      <HealthStrip
        tradedLive={tradedLive}
        armedLive={armedLive}
        equity={equity}
        equitySyncedAt={balancesSynced ? d.balances_at : null}
        targetIso={targetIso}
        checkpointTimes={checkpointTimes}
        lastRun={lastRun}
        schedulerSeenAt={hb?.created_at ?? null}
        pollerSeenAt={d.poller_seen_at}
        pendingRequests={d.pending_requests}
      />

      <div className="mt-3">
        <RunNow />
      </div>

      {/* 1 — EXECUTED: confirmed fills only */}
      <Section
        title="1 · Executed"
        desc="Confirmed fills only — the exchange returned these. Live money by default; simulated (paper) fills behind the toggle."
      >
        <Executed fills={d.fills} latestRecon={latestRecon} />
      </Section>

      {/* 2 — POSITIONS: what we hold and the exit plan for each */}
      <Section
        title="2 · Positions"
        desc="What the system is managing right now — cost basis, current value, and the exit plan (stop / target / horizon) fixed at entry."
      >
        <PositionsView positions={d.open_positions} portfolio={d.portfolio} />
        <div className="mt-3">
          <PortfolioOverview snap={d.portfolio} />
        </div>
      </Section>

      {/* 3 — REASONING: one card per checkpoint, crashes included */}
      <Section
        title="3 · Reasoning log"
        desc="Every checkpoint: what was scanned, every idea with the reason it was funded, vetoed, or passed over, and the CEO's verdict. Crashed runs show in red."
      >
        <StrategistCard review={d.strategist} />
        <ReasoningLog decisions={d.decisions} runs={d.runs} fills={d.fills} audit={d.audit} />
      </Section>

      {/* ---- one click away ------------------------------------------------- */}

      <Section
        collapsible
        defaultOpen={false}
        title="Performance"
        desc="Realized results only — fills in once positions close."
      >
        {d.outcomes.length === 0 ? (
          <Empty>
            No closed trades yet. The equity curve, ROI vs the floor, attribution, and outcome
            scoring all start with the first position the system closes.
          </Empty>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat
                label="Realized P&L"
                value={cad(roll.pnl)}
                tone={roll.pnl >= 0 ? "good" : "bad"}
              />
              <Stat label="Hit rate" value={pct(roll.hitRate, 0)} sub={`${roll.n} resolved`} tone="cyan" />
              <Stat
                label="Net ROI"
                value={perf?.net_roi != null ? pct(perf.net_roi) : "—"}
                tone={perf?.net_roi != null ? (perf.net_roi >= 0 ? "good" : "bad") : "default"}
              />
              <Stat
                label="vs Floor"
                value={perf?.excess_vs_floor != null ? pct(perf.excess_vs_floor) : "—"}
                tone={
                  perf?.excess_vs_floor != null
                    ? perf.excess_vs_floor >= 0
                      ? "good"
                      : "bad"
                    : "default"
                }
              />
            </div>
            <EquityChart points={series} start={dep.total} />
            {Object.keys(attribution).length > 0 ? (
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                {Object.entries(attribution).map(([div, v]) => (
                  <Stat
                    key={div}
                    label={divLabel(div)}
                    value={cad(v as number)}
                    tone={(v as number) >= 0 ? "good" : "bad"}
                  />
                ))}
              </div>
            ) : null}
            <Table head={["When", "Team", "Predicted", "Actual", "P&L", "Process / luck"]}>
              {d.outcomes.slice(0, 25).map((o) => (
                <tr key={o.id} className="hover:bg-white/[0.02]">
                  <td className="px-4 py-3 text-slate-400">{ago(o.resolved_at)}</td>
                  <td className="px-4 py-3 capitalize">{divLabel(o.division)}</td>
                  <td className="num px-4 py-3">{pct(o.predicted_return)}</td>
                  <td className={`num px-4 py-3 ${o.realized_return >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {pct(o.realized_return)}
                  </td>
                  <td className={`num px-4 py-3 ${o.pnl_cad >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {cad(o.pnl_cad)}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">{o.process_luck ?? "—"}</td>
                </tr>
              ))}
            </Table>
          </div>
        )}
      </Section>

      <Section
        collapsible
        defaultOpen={false}
        title="The teams"
        desc="Track record is demonstrated accuracy, not stated confidence. Risk budget 0 = benched."
      >
        {d.divisions.length === 0 ? (
          <Empty>No teams registered yet.</Empty>
        ) : (
          <Table head={["Team", "Status", "Track record", "Risk budget", "Trades", "Beat the floor by"]}>
            {d.divisions.map((x) => {
              const mean = calibrationMean(x);
              const status = x.retired ? "benched" : x.shadow ? "watching" : "active";
              const tone = x.retired ? "bad" : x.shadow ? "warn" : "good";
              return (
                <tr key={x.division} className="hover:bg-white/[0.02]">
                  <td className="px-4 py-3 font-medium capitalize">{divLabel(x.division)}</td>
                  <td className="px-4 py-3"><Pill tone={tone}>{status}</Pill></td>
                  <td className="num px-4 py-3">{x.n_resolved > 0 ? pct(mean, 0) : "—"}</td>
                  <td className="num px-4 py-3">{pct(x.leash, 0)}</td>
                  <td className="num px-4 py-3">{x.n_resolved}</td>
                  <td className={`num px-4 py-3 ${x.net_vs_floor_cad >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {cad(x.net_vs_floor_cad)}
                  </td>
                </tr>
              );
            })}
          </Table>
        )}
      </Section>

      <Section
        collapsible
        defaultOpen={false}
        title="Tracked universe"
        desc="Every symbol scanned each checkpoint."
      >
        {latestSession?.universe && Object.keys(latestSession.universe).length > 0 ? (
          <div className="grid gap-3 md:grid-cols-3">
            {Object.entries(latestSession.universe).map(([div, u]) => (
              <div key={div} className="glass hud p-4">
                <div className="flex items-center justify-between">
                  <span className="label capitalize">{divLabel(div)}</span>
                  <Pill tone="cyan">
                    {u.symbols.length} · {u.venue}
                  </Pill>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {u.symbols.map((s) => (
                    <span
                      key={s}
                      className="num rounded-md border border-white/10 bg-white/[0.03] px-2 py-1 text-xs text-slate-200"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Empty>Universe appears after the next checkpoint runs.</Empty>
        )}
      </Section>

      <Section
        collapsible
        defaultOpen={false}
        title="Session history"
        desc="Compact list of past checkpoints (full reasoning is in section 3)."
      >
        <SessionHistory decisions={d.decisions} />
      </Section>

      <Section title="Ask the Boardroom" desc="Talk to the CEO or CFO about its decisions — grounded in the real data, read-only.">
        <AskBoardroom />
      </Section>

      <Section
        collapsible
        defaultOpen={false}
        count={d.audit.length}
        title="Event log"
        desc="Cross-cutting events in plain language — executions, vetoes, breakers, errors."
      >
        <AuditLog rows={d.audit} />
      </Section>

      {d.weekly ? (
        <Section collapsible defaultOpen={false} title="Weekly readout" desc={`Generated ${when(d.weekly.created_at)}`}>
          <pre className="glass whitespace-pre-wrap p-4 font-mono text-xs leading-relaxed text-slate-200">
            {d.weekly.report}
          </pre>
        </Section>
      ) : null}

      <footer className="mt-12 border-t border-white/10 pt-4 text-xs text-slate-500">
        Boardroom · the LLM reasons, code calculates · data from Supabase ·{" "}
        <span className="text-sky-300">read-only</span>
        {d.reserve_cad > 0 ? (
          <span className="ml-2 text-violet-300">🔒 reserve {cad(d.reserve_cad)}</span>
        ) : null}
      </footer>
    </main>
  );
}
