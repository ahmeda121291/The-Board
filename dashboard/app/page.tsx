import Link from "next/link";
import { Empty, Pill, Section, Stat, Table } from "@/components/ui";
import { Refresher } from "@/components/Refresher";
import { Countdown } from "@/components/Countdown";
import { SessionView } from "@/components/Session";
import { SessionHistory } from "@/components/SessionHistory";
import { EquityChart } from "@/components/EquityChart";
import { AskBoardroom } from "@/components/AskBoardroom";
import { RunNow } from "@/components/RunNow";
import {
  calibrationMean,
  equitySeries,
  loadDashboard,
  rollupOutcomes,
  type Decision,
  type Session,
  type StrategyReview,
} from "@/lib/data";
import { deposits } from "@/lib/deposits";
import { nextCheckpointIso } from "@/lib/schedule";
import { ago, cad, num, pct, when } from "@/lib/format";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function kindTone(kind: string) {
  if (kind === "fund") return "good";
  if (kind === "hold") return "warn";
  return "default";
}

function BalanceCard({
  krakenCash, ibkrCash, equity, at,
}: { krakenCash: number | null; ibkrCash: number | null; equity: number | null; at: string | null }) {
  const dep = deposits();
  const synced = at !== null && equity !== null;
  const Row = ({ name, v, tone }: { name: string; v: number | null; tone: string }) => (
    <div className="flex items-center justify-between gap-6">
      <span className="flex items-center gap-1.5">
        <span className={`inline-block h-1.5 w-1.5 rounded-full ${tone}`} />
        <span className="text-[10px] uppercase tracking-widest text-slate-400">{name}</span>
      </span>
      <span className="num text-sm text-slate-200">{v === null ? "—" : cad(v)}</span>
    </div>
  );
  return (
    <div className="glass hud p-3 min-w-[210px]">
      <div className="label mb-2">{synced ? "Live balances" : "Funding baseline"}</div>
      <div className="space-y-1.5">
        <Row name="Kraken · crypto" v={synced ? krakenCash : dep.kraken} tone="bg-sky-400" />
        <Row name="IBKR · stocks" v={synced ? ibkrCash : dep.ibkr} tone="bg-violet-400" />
        <div className="my-1 h-px bg-white/10" />
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-widest text-slate-400">
            {synced ? "Total cash" : "Start balance"}
          </span>
          <span className="num text-sm font-semibold text-sky-300 glow-cyan">
            {cad(synced ? (equity as number) : dep.total)}
          </span>
        </div>
      </div>
      <div className="mt-2 text-[10px] text-slate-500">
        {synced ? `synced ${ago(at as string)}` : "estimate — run `boardroom balances` to sync real cash"}
      </div>
    </div>
  );
}

function DecisionRationale({ decisions }: { decisions: Decision[] }) {
  const latest = decisions[0];
  if (!latest) return <Empty>No decisions yet — the CEO hasn’t convened. Run a decision loop.</Empty>;
  return (
    <div className="glass hud p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={kindTone(latest.kind)}>{latest.kind.toUpperCase()}</Pill>
        {latest.division ? <Pill tone="cyan">{latest.division}</Pill> : null}
        {latest.size_cad > 0 ? <span className="num text-sm text-white">{cad(latest.size_cad)}</span> : null}
        <Pill tone={latest.live ? "bad" : "default"}>{latest.live ? "LIVE" : "dry-run"}</Pill>
        <span className="ml-auto text-xs text-slate-500">{ago(latest.created_at)}</span>
      </div>
      <p className="mt-3 text-[15px] leading-relaxed text-slate-100">
        {latest.rationale || "(no rationale recorded)"}
      </p>
      <div className="mt-3 text-xs text-slate-500">
        Hurdle (floor) rate this horizon: <span className="num">{num(latest.hurdle_rate, 5)}</span>
      </div>
    </div>
  );
}

function StrategistPanel({ review }: { review: StrategyReview | null }) {
  if (!review) {
    return (
      <Empty>
        No CFO review yet — it’s written each checkpoint (or run <code className="text-sky-300">boardroom review</code>).
      </Empty>
    );
  }
  return (
    <div className="glass hud p-5">
      <div className="flex items-center gap-2">
        <span className="text-lg">🧮</span>
        <span className="label">Chief Strategist (CFO)</span>
        <span className="ml-auto text-xs text-slate-500">{ago(review.created_at)}</span>
      </div>
      <div className="mt-2 text-sm font-semibold text-sky-300 glow-cyan">{review.headline}</div>
      <p className="mt-2 text-sm leading-relaxed text-slate-200">{review.narrative}</p>
      {review.recommendations?.length ? (
        <div className="mt-4 space-y-2">
          <div className="label">Recommendations</div>
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

  const perf = d.performance?.payload ?? null;
  const roll = rollupOutcomes(d.outcomes);
  const netRoi = perf?.net_roi ?? null;
  const exFloor = perf?.excess_vs_floor ?? null;
  const exBnh = perf?.excess_vs_bnh ?? null;
  const costDrag = perf?.cost_drag_pct ?? (roll.n ? roll.cost / Math.max(1, Math.abs(roll.pnl)) : null);
  const breaker: string[] = perf?.breaker ?? [];
  const attribution = perf?.attribution ?? roll.attribution;

  // Prefer real synced venue cash; fall back to the funding baseline + realized P&L.
  const balancesSynced = d.equity_cad !== null && d.balances_at !== null;
  const equity = balancesSynced ? (d.equity_cad as number) : dep.total + roll.pnl;
  const roiOnDeposit = dep.total > 0 ? (equity - dep.total) / dep.total : 0;

  const liveCount = d.divisions.filter((x) => !x.retired && !x.shadow).length;
  const shadowCount = d.divisions.filter((x) => x.shadow && !x.retired).length;
  const retiredCount = d.divisions.filter((x) => x.retired).length;
  const latest = d.decisions[0] ?? null;
  const isFresh = d.decisions.length === 0 && d.pitches.length === 0 && d.outcomes.length === 0;
  const asOf = new Date().toLocaleTimeString("en-CA", { hour: "2-digit", minute: "2-digit" });

  const checkpointUtc = process.env.CHECKPOINT_UTC || "19:00";
  const hb = d.audit.find((a) => a.event === "scheduler_heartbeat");
  const hbNext = (hb?.payload as any)?.next_run_at as string | undefined;
  const hbLive = (hb?.payload as any)?.live === true;
  const envArmed = (process.env.LIVE_TRADING || "").toLowerCase() === "true";
  // Tri-state live status:
  //   tradedLive — a real trade has actually executed and been logged
  //   armedLive  — configured for live, but no live trade yet
  // The durable signal is d.live_armed (persisted in system_state, set whenever a
  // live-confirmed run convenes) so the badge survives redeploys and never falls
  // back to "dry-run" just because a recent heartbeat aged out of the log.
  const tradedLive = Boolean(latest?.live);
  const armedLive = tradedLive || d.live_armed || hbLive || envArmed;
  const targetIso =
    hbNext && new Date(hbNext).getTime() > Date.now() ? hbNext : nextCheckpointIso(checkpointUtc);
  const schedulerActive = hb ? Date.now() - new Date(hb.created_at).getTime() < 26 * 3600 * 1000 : false;
  const latestSession: Session | null =
    latest && latest.ranked && typeof latest.ranked === "object" && !Array.isArray(latest.ranked)
      ? (latest.ranked as Session)
      : null;
  const series = equitySeries(d.outcomes, dep.total);

  return (
    <main className="mx-auto max-w-6xl px-5 py-8">
      {/* Header */}
      <header className="flex flex-wrap items-start gap-4">
        <div>
          <h1 className="title-grad text-3xl font-bold tracking-tight">BOARDROOM</h1>
          <p className="mt-1 text-xs uppercase tracking-[0.25em] text-slate-500">
            autonomous capital allocator
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <span
              className="flex items-center gap-2 rounded-full border px-2.5 py-1"
              style={{
                borderColor: tradedLive
                  ? "rgba(244,63,94,0.4)"
                  : armedLive
                  ? "rgba(16,185,129,0.4)"
                  : "rgba(255,255,255,0.1)",
              }}
              title={
                tradedLive
                  ? "A live trade has executed and been logged."
                  : armedLive
                  ? `Configured & scheduled for live trading. No live trade yet — next checkpoint ${checkpointUtc} UTC.`
                  : "No live trade logged and live mode not detected."
              }
            >
              <span className={tradedLive || armedLive ? "dot dot-live" : "dot"} />
              {tradedLive ? "LIVE TRADING" : armedLive ? "LIVE · ARMED" : "dry-run · safe"}
            </span>
            {breaker.length > 0 ? <Pill tone="bad">⚠ CIRCUIT BREAKER</Pill> : <Pill tone="good">breakers clear</Pill>}
            <Pill tone="cyan">{liveCount} live</Pill>
            <Pill tone="warn">{shadowCount} shadow</Pill>
            {retiredCount > 0 ? <Pill tone="bad">{retiredCount} benched</Pill> : null}
          </div>
        </div>
        <div className="ml-auto flex flex-col items-end gap-2">
          <BalanceCard
            krakenCash={d.kraken_cash_cad}
            ibkrCash={d.ibkr_cash_cad}
            equity={d.equity_cad}
            at={d.balances_at}
          />
          <div className="flex items-center gap-2 text-[11px] text-slate-500">
            <Link href="/docs" className="rounded-full border border-white/15 px-2.5 py-1 text-slate-300 hover:border-sky-400/40 hover:text-sky-300">
              📖 Docs
            </Link>
            <span>as of {asOf}</span>
            <span className="text-slate-600">·</span>
            <Refresher />
          </div>
        </div>
      </header>

      {d.error ? (
        <div className="glass mt-4 border border-rose-400/30 p-3 text-sm text-rose-300">Query error: {d.error}</div>
      ) : null}

      {/* Next checkpoint countdown */}
      <div className="glass hud mt-5 flex flex-wrap items-center gap-x-8 gap-y-3 p-4">
        <div>
          <div className="label">Next daily checkpoint</div>
          <div className="mt-1 text-4xl font-bold">
            <Countdown targetIso={targetIso} />
          </div>
        </div>
        <div className="text-xs leading-relaxed text-slate-400">
          <div>
            convenes <span className="text-slate-200">{checkpointUtc} UTC</span> daily
          </div>
          <div>
            last checkpoint:{" "}
            <span className="text-slate-200">{latest ? ago(latest.created_at) : "never"}</span>
          </div>
        </div>
        <div className="ml-auto">
          {schedulerActive ? (
            <Pill tone="good">● scheduler active</Pill>
          ) : (
            <Pill tone="warn">scheduler idle — run `boardroom run`</Pill>
          )}
        </div>
      </div>

      {/* On-demand run — request a checkpoint now (executed on your PC) */}
      <div className="mt-3">
        <RunNow />
      </div>

      {/* Hero — portfolio value */}
      <div className="glass hud mt-6 flex flex-wrap items-end justify-between gap-6 p-6">
        <div>
          <div className="label">{balancesSynced ? "Total equity · live venue cash" : "Estimated equity · baseline + realized P&amp;L"}</div>
          <div className="num mt-1 text-5xl font-bold text-white glow-cyan">{cad(equity)}</div>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
            <span className="text-slate-400">start {cad(dep.total)}</span>
            <span className={roll.pnl >= 0 ? "text-emerald-400" : "text-rose-400"}>
              {roll.pnl >= 0 ? "▲" : "▼"} {cad(Math.abs(roll.pnl))} realized
            </span>
            <span className={roiOnDeposit >= 0 ? "text-emerald-400" : "text-rose-400"}>
              {pct(roiOnDeposit)}
            </span>
            {d.reserve_cad > 0 ? (
              <span className="text-violet-300">🔒 reserve {cad(d.reserve_cad)}</span>
            ) : null}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Net ROI" value={netRoi === null ? "—" : pct(netRoi)} tone={netRoi === null ? "default" : netRoi >= 0 ? "good" : "bad"} />
          <Stat label="vs Floor" value={exFloor === null ? "—" : pct(exFloor)} tone={exFloor === null ? "default" : exFloor >= 0 ? "good" : "bad"} />
          <Stat label="vs Buy&Hold" value={exBnh === null ? "—" : pct(exBnh)} tone={exBnh === null ? "default" : exBnh >= 0 ? "good" : "bad"} />
          <Stat label="Hit rate" value={roll.n ? pct(roll.hitRate, 0) : "—"} sub={`${roll.n} resolved`} tone="cyan" />
        </div>
      </div>

      {/* Equity curve + the CFO's standing review */}
      <div className="mt-5 grid gap-3 lg:grid-cols-2">
        <EquityChart points={series} start={dep.total} />
        <StrategistPanel review={d.strategist} />
      </div>

      {/* Onboarding when fresh */}
      {isFresh ? (
        <div className="glass hud mt-6 p-5">
          <div className="text-sm font-semibold text-sky-300 glow-cyan">The hub is wired and waiting.</div>
          <p className="mt-2 text-sm text-slate-300">
            Supabase is connected; the system hasn’t logged a decision yet. Run a checkpoint on your
            machine and this fills in automatically:
          </p>
          <pre className="mt-3 rounded-xl border border-white/10 bg-black/40 p-3 font-mono text-xs text-slate-200">
boardroom decide              # dry-run: pitches + the CEO’s call, no real money
boardroom decide --confirm-live   # live (LIVE_TRADING=true + funded)</pre>
        </div>
      ) : null}

      {/* Ask the Boardroom — talk to the CEO / CFO */}
      <Section title="Ask the Boardroom" desc="Talk to the CEO or CFO about its decisions — grounded in the real data, read-only.">
        <AskBoardroom />
      </Section>

      {/* CEO */}
      <Section title="The CEO" desc="Latest verdict and rationale. Most days the right answer is HOLD.">
        <DecisionRationale decisions={d.decisions} />
      </Section>

      {/* Latest boardroom session — the full story */}
      <Section
        title="Latest boardroom session"
        desc="What each division did, what was pitched, what the risk manager vetoed, and how the CEO ruled — with reasons."
      >
        <SessionView session={latestSession} />
      </Section>

      {/* Session history — scroll back through past checkpoints */}
      <Section title="Session history" desc="The last several checkpoints at a glance.">
        <SessionHistory decisions={d.decisions} />
      </Section>

      {/* Tracked universe — what gets scanned every run */}
      <Section title="Tracked universe" desc="Every symbol the divisions scan each checkpoint. The CEO ranks across all and funds the single best.">
        {latestSession?.universe && Object.keys(latestSession.universe).length > 0 ? (
          <div className="grid gap-3 md:grid-cols-3">
            {Object.entries(latestSession.universe).map(([div, u]) => (
              <div key={div} className="glass hud p-4">
                <div className="flex items-center justify-between">
                  <span className="label capitalize">{div}</span>
                  <Pill tone="cyan">{u.symbols.length} · {u.venue}</Pill>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {u.symbols.map((s) => (
                    <span key={s} className="num rounded-md border border-white/10 bg-white/[0.03] px-2 py-1 text-xs text-slate-200">
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

      {/* Divisions */}
      <Section
        title="The teams"
        desc="Each team hunts a different kind of opportunity. “Track record” is how often it’s actually been right — earned, not claimed. “Risk budget” is how much we let it bet (0 = benched until it proves itself)."
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
                  <td className="px-4 py-3 font-medium capitalize">{x.division}</td>
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

      {/* Attribution */}
      <Section title="Where return came from" desc="Per-division attribution of realized P&L.">
        {Object.keys(attribution).length === 0 ? (
          <Empty>No attribution yet — comes once decisions resolve.</Empty>
        ) : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {Object.entries(attribution).map(([div, v]) => (
              <Stat key={div} label={div} value={cad(v as number)} tone={(v as number) >= 0 ? "good" : "bad"} />
            ))}
            <Stat label="cost drag" value={costDrag === null ? "—" : pct(costDrag)} tone="warn" />
          </div>
        )}
      </Section>

      {/* Decisions */}
      <Section title="Decision log" desc="Every checkpoint and what the CEO decided — buy something, or hold the cash floor.">
        {d.decisions.length === 0 ? (
          <Empty>No decisions logged yet.</Empty>
        ) : (
          <Table head={["When", "Decision", "Team", "Size", "Floor to beat", "Mode"]}>
            {d.decisions.map((x) => (
              <tr key={x.decision_id} className="hover:bg-white/[0.02]">
                <td className="px-4 py-3 text-slate-400">{when(x.created_at)}</td>
                <td className="px-4 py-3"><Pill tone={kindTone(x.kind)}>{x.kind}</Pill></td>
                <td className="px-4 py-3 capitalize">{x.division ?? "—"}</td>
                <td className="num px-4 py-3">{x.size_cad > 0 ? cad(x.size_cad) : "—"}</td>
                <td className="num px-4 py-3 text-slate-400">{num(x.hurdle_rate, 5)}</td>
                <td className="px-4 py-3"><Pill tone={x.live ? "bad" : "default"}>{x.live ? "live" : "dry"}</Pill></td>
              </tr>
            ))}
          </Table>
        )}
      </Section>

      {/* Pitches */}
      <Section title="Recent ideas" desc="Every idea a team pitched recently, newest first — whether or not it got funded.">
        {d.pitches.length === 0 ? (
          <Empty>No ideas yet.</Empty>
        ) : (
          <Table head={["When", "Team", "Symbol", "Exp. return", "Win prob", "Size", "Max loss"]}>
            {d.pitches.map((p) => (
              <tr key={p.pitch_id} className="hover:bg-white/[0.02]">
                <td className="px-4 py-3 text-slate-400">{ago(p.created_at)}</td>
                <td className="px-4 py-3 capitalize">{p.division}</td>
                <td className="num px-4 py-3">{p.symbol}</td>
                <td className={`num px-4 py-3 ${p.expected_return >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {pct(p.expected_return)}
                </td>
                <td className="num px-4 py-3">{pct(p.confidence, 0)}</td>
                <td className="num px-4 py-3">{cad(p.capital_required)}</td>
                <td className="num px-4 py-3 text-slate-400">{cad(p.max_loss)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Section>

      {/* Outcomes */}
      <Section title="How past bets turned out" desc="Once a trade closes: what we predicted vs what actually happened, and whether it was good process or just luck.">
        {d.outcomes.length === 0 ? (
          <Empty>Nothing resolved yet.</Empty>
        ) : (
          <Table head={["When", "Team", "Predicted", "Actual", "P&L", "Process / luck"]}>
            {d.outcomes.slice(0, 25).map((o) => (
              <tr key={o.id} className="hover:bg-white/[0.02]">
                <td className="px-4 py-3 text-slate-400">{ago(o.resolved_at)}</td>
                <td className="px-4 py-3 capitalize">{o.division}</td>
                <td className="num px-4 py-3">{pct(o.predicted_return)}</td>
                <td className={`num px-4 py-3 ${o.realized_return >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {pct(o.realized_return)}
                </td>
                <td className={`num px-4 py-3 ${o.pnl_cad >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{cad(o.pnl_cad)}</td>
                <td className="px-4 py-3 text-xs text-slate-500">{o.process_luck ?? "—"}</td>
              </tr>
            ))}
          </Table>
        )}
      </Section>

      {/* Weekly */}
      {d.weekly ? (
        <Section title="Weekly readout" desc={`Generated ${when(d.weekly.created_at)}`}>
          <pre className="glass whitespace-pre-wrap p-4 font-mono text-xs leading-relaxed text-slate-200">
            {d.weekly.report}
          </pre>
        </Section>
      ) : null}

      {/* Audit */}
      <Section title="Audit log" desc="Cross-cutting events — executions, vetoes, breakers, retirements.">
        {d.audit.length === 0 ? (
          <Empty>No events yet.</Empty>
        ) : (
          <div className="glass space-y-1 p-4 font-mono text-xs">
            {d.audit.map((a) => (
              <div key={a.id} className="flex gap-3">
                <span className="text-slate-500">{when(a.created_at)}</span>
                <span className="text-sky-300">{a.event}</span>
                <span className="truncate text-slate-500">{JSON.stringify(a.payload)}</span>
              </div>
            ))}
          </div>
        )}
      </Section>

      <footer className="mt-12 border-t border-white/10 pt-4 text-xs text-slate-500">
        Boardroom · the LLM reasons, code calculates · data from Supabase ·{" "}
        <span className="text-sky-300">read-only</span>
      </footer>
    </main>
  );
}
