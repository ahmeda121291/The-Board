import { Empty, Pill, Section, Stat, Table } from "@/components/ui";
import {
  calibrationMean,
  loadDashboard,
  rollupOutcomes,
  type Decision,
} from "@/lib/data";
import { ago, cad, num, pct, when } from "@/lib/format";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function kindTone(kind: string) {
  if (kind === "fund") return "good";
  if (kind === "hold") return "warn";
  return "default";
}

function DecisionRationale({ decisions }: { decisions: Decision[] }) {
  const latest = decisions[0];
  if (!latest) return <Empty>No decisions yet — the CEO hasn’t convened. Run a decision loop.</Empty>;
  return (
    <div className="card">
      <div className="flex items-center gap-2">
        <Pill tone={kindTone(latest.kind)}>{latest.kind.toUpperCase()}</Pill>
        {latest.division ? <Pill tone="accent">{latest.division}</Pill> : null}
        {latest.size_cad > 0 ? <span className="text-sm text-white">{cad(latest.size_cad)}</span> : null}
        <Pill tone={latest.live ? "bad" : "default"}>{latest.live ? "LIVE" : "dry-run"}</Pill>
        <span className="ml-auto text-xs text-muted">{ago(latest.created_at)}</span>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-white/90">
        {latest.rationale || "(no rationale recorded)"}
      </p>
      <div className="mt-3 text-xs text-muted">
        Hurdle (floor) rate this horizon: {num(latest.hurdle_rate, 5)}
      </div>
    </div>
  );
}

export default async function Page() {
  const d = await loadDashboard();

  if (!d.configured) {
    return (
      <main className="mx-auto max-w-6xl px-5 py-10">
        <h1 className="text-2xl font-bold">Boardroom</h1>
        <div className="card mt-6 text-sm text-muted">
          Not connected to Supabase. Set <code className="text-accent">SUPABASE_URL</code> and{" "}
          <code className="text-accent">SUPABASE_SERVICE_KEY</code> in the Vercel project’s environment
          variables, then redeploy.
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

  return (
    <main className="mx-auto max-w-6xl px-5 py-8">
      {/* Header */}
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold tracking-tight">
          Boardroom <span className="text-muted">/ autonomous capital allocator</span>
        </h1>
        <div className="ml-auto flex items-center gap-2">
          {breaker.length > 0 ? (
            <Pill tone="bad">CIRCUIT BREAKER</Pill>
          ) : (
            <Pill tone="good">breakers clear</Pill>
          )}
          <span className="text-xs text-muted">updated {ago(d.performance?.created_at)}</span>
        </div>
      </header>

      {d.error ? (
        <div className="card mt-4 border-bad/40 text-sm text-bad">Query error: {d.error}</div>
      ) : null}

      {/* Top stats */}
      <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Net ROI"
          value={netRoi === null ? "—" : pct(netRoi)}
          tone={netRoi === null ? "default" : netRoi >= 0 ? "good" : "bad"}
          sub="net of fees, slippage, FX"
        />
        <Stat
          label="vs Floor (carry)"
          value={exFloor === null ? "—" : pct(exFloor)}
          tone={exFloor === null ? "default" : exFloor >= 0 ? "good" : "bad"}
          sub="excess over doing nothing"
        />
        <Stat
          label="vs Buy & Hold"
          value={exBnh === null ? "—" : pct(exBnh)}
          tone={exBnh === null ? "default" : exBnh >= 0 ? "good" : "bad"}
          sub="the brutal benchmark"
        />
        <Stat
          label="Realized P&L"
          value={cad(roll.pnl)}
          tone={roll.pnl >= 0 ? "good" : "bad"}
          sub={`${roll.n} resolved · hit ${pct(roll.hitRate, 0)}`}
        />
      </div>

      {/* CEO decision */}
      <Section title="The CEO" desc="Latest verdict and rationale. Most days the right answer is HOLD.">
        <DecisionRationale decisions={d.decisions} />
      </Section>

      {/* Divisions */}
      <Section
        title="Divisions"
        desc="Trust = demonstrated calibration (Beta posterior mean), not stated confidence. Leash scales with it."
      >
        {d.divisions.length === 0 ? (
          <Empty>No divisions registered yet.</Empty>
        ) : (
          <Table head={["Division", "Status", "Calibration", "Leash", "Resolved", "Net vs floor"]}>
            {d.divisions.map((x) => {
              const mean = calibrationMean(x);
              const status = x.retired ? "retired" : x.shadow ? "shadow" : "live";
              const tone = x.retired ? "bad" : x.shadow ? "warn" : "good";
              return (
                <tr key={x.division}>
                  <td className="px-4 py-3 font-medium capitalize">{x.division}</td>
                  <td className="px-4 py-3">
                    <Pill tone={tone}>{status}</Pill>
                  </td>
                  <td className="px-4 py-3">
                    {pct(mean, 0)} <span className="text-muted">α{num(x.alpha, 1)}/β{num(x.beta, 1)}</span>
                  </td>
                  <td className="px-4 py-3">{num(x.leash, 2)}</td>
                  <td className="px-4 py-3">{x.n_resolved}</td>
                  <td className={`px-4 py-3 ${x.net_vs_floor_cad >= 0 ? "text-good" : "text-bad"}`}>
                    {cad(x.net_vs_floor_cad)}
                  </td>
                </tr>
              );
            })}
          </Table>
        )}
      </Section>

      {/* Portfolio makeup (attribution) */}
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

      {/* Decisions log */}
      <Section title="Decision log" desc="Every checkpoint: FUND / HOLD / FUND_NONE.">
        {d.decisions.length === 0 ? (
          <Empty>No decisions logged yet.</Empty>
        ) : (
          <Table head={["When", "Decision", "Division", "Size", "Hurdle", "Mode"]}>
            {d.decisions.map((x) => (
              <tr key={x.decision_id}>
                <td className="px-4 py-3 text-muted">{when(x.created_at)}</td>
                <td className="px-4 py-3">
                  <Pill tone={kindTone(x.kind)}>{x.kind}</Pill>
                </td>
                <td className="px-4 py-3 capitalize">{x.division ?? "—"}</td>
                <td className="px-4 py-3">{x.size_cad > 0 ? cad(x.size_cad) : "—"}</td>
                <td className="px-4 py-3 text-muted">{num(x.hurdle_rate, 5)}</td>
                <td className="px-4 py-3">
                  <Pill tone={x.live ? "bad" : "default"}>{x.live ? "live" : "dry"}</Pill>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Section>

      {/* Recent pitches */}
      <Section title="Recent pitches" desc="Computed numbers (code), narrative (LLM). Quant fields are never LLM guesses.">
        {d.pitches.length === 0 ? (
          <Empty>No pitches yet.</Empty>
        ) : (
          <Table head={["When", "Division", "Symbol", "Exp. return", "Win prob", "Size", "Max loss"]}>
            {d.pitches.map((p) => (
              <tr key={p.pitch_id}>
                <td className="px-4 py-3 text-muted">{ago(p.created_at)}</td>
                <td className="px-4 py-3 capitalize">{p.division}</td>
                <td className="px-4 py-3 font-mono">{p.symbol}</td>
                <td className={`px-4 py-3 ${p.expected_return >= 0 ? "text-good" : "text-bad"}`}>
                  {pct(p.expected_return)}
                </td>
                <td className="px-4 py-3">{pct(p.confidence, 0)}</td>
                <td className="px-4 py-3">{cad(p.capital_required)}</td>
                <td className="px-4 py-3 text-muted">{cad(p.max_loss)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Section>

      {/* Resolved outcomes */}
      <Section title="Resolved outcomes" desc="Predicted vs realized, and the process-vs-luck tag.">
        {d.outcomes.length === 0 ? (
          <Empty>Nothing resolved yet.</Empty>
        ) : (
          <Table head={["When", "Division", "Predicted", "Realized", "P&L", "Process×Luck"]}>
            {d.outcomes.slice(0, 25).map((o) => (
              <tr key={o.id}>
                <td className="px-4 py-3 text-muted">{ago(o.resolved_at)}</td>
                <td className="px-4 py-3 capitalize">{o.division}</td>
                <td className="px-4 py-3">{pct(o.predicted_return)}</td>
                <td className={`px-4 py-3 ${o.realized_return >= 0 ? "text-good" : "text-bad"}`}>
                  {pct(o.realized_return)}
                </td>
                <td className={`px-4 py-3 ${o.pnl_cad >= 0 ? "text-good" : "text-bad"}`}>{cad(o.pnl_cad)}</td>
                <td className="px-4 py-3 text-xs text-muted">{o.process_luck ?? "—"}</td>
              </tr>
            ))}
          </Table>
        )}
      </Section>

      {/* Weekly report */}
      {d.weekly ? (
        <Section title="Weekly readout" desc={`Generated ${when(d.weekly.created_at)}`}>
          <pre className="card whitespace-pre-wrap font-mono text-xs leading-relaxed text-white/90">
            {d.weekly.report}
          </pre>
        </Section>
      ) : null}

      {/* Audit */}
      <Section title="Audit log" desc="Cross-cutting events — executions, vetoes, breakers, retirements.">
        {d.audit.length === 0 ? (
          <Empty>No events yet.</Empty>
        ) : (
          <div className="card space-y-1 font-mono text-xs">
            {d.audit.map((a) => (
              <div key={a.id} className="flex gap-3">
                <span className="text-muted">{when(a.created_at)}</span>
                <span className="text-accent">{a.event}</span>
                <span className="truncate text-muted">{JSON.stringify(a.payload)}</span>
              </div>
            ))}
          </div>
        )}
      </Section>

      <footer className="mt-10 border-t border-edge pt-4 text-xs text-muted">
        Boardroom · the LLM reasons, code calculates · data from Supabase ·{" "}
        <span className="text-accent">read-only</span>
      </footer>
    </main>
  );
}
