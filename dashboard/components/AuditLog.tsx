import type { AuditRow } from "@/lib/data";
import { cad, when } from "@/lib/format";

// Cross-cutting events in sentences, not JSON. Heartbeats are filtered out —
// they're liveness plumbing (already on the health strip), not events.

function describe(a: AuditRow): { text: string; tone: "info" | "warn" | "bad" } | null {
  const p = (a.payload ?? {}) as Record<string, any>;
  switch (a.event) {
    case "scheduler_heartbeat":
      return null; // shown on the health strip, noise here
    case "risk_veto":
      return {
        text: `Risk manager vetoed a pitch — ${(p.objections ?? []).join("; ") || "hard objection"}`,
        tone: "info",
      };
    case "execute":
      return { text: `Order executed (${p.live ? "LIVE" : "dry-run"})`, tone: p.live ? "warn" : "info" };
    case "execute_error":
      return {
        text: `Order FAILED for ${p.symbol ?? "?"} (${cad(p.size_cad)}): ${p.error ?? "unknown error"}`,
        tone: "bad",
      };
    case "exit_executed":
      return {
        text: `Sold ${p.symbol ?? "?"} — realized ${((p.realized_return ?? 0) * 100).toFixed(2)}%, P&L ${cad(p.pnl_cad)}`,
        tone: "warn",
      };
    case "position_resolved":
      return {
        text: `Position closed (${p.division ?? "?"}): ${p.win ? "win" : "loss"}, P&L ${cad(p.pnl_cad)}`,
        tone: "info",
      };
    case "circuit_breaker":
      return { text: `CIRCUIT BREAKER tripped: ${(p.tripped ?? []).join("; ")}`, tone: "bad" };
    case "reconciliation_untracked":
      return {
        text: `Untracked venue holdings detected: ${(p.untracked ?? [])
          .map((u: any) => `${u.qty} ${u.asset}`)
          .join(", ")}`,
        tone: "bad",
      };
    case "division_retired":
      return { text: `Division benched for miscalibration: ${p.division}`, tone: "warn" };
    case "refit":
      return { text: "Walk-forward model re-fit ran", tone: "info" };
    case "ratchet":
      return { text: `Gains ratchet swept reserve to ${cad(p.reserve_cad)}`, tone: "info" };
    case "fill_record_error":
    case "position_record_error":
    case "recommendation_error":
    case "portfolio_snapshot_error":
    case "resolution_error":
    case "exit_error":
      return {
        text: `${a.event.replace(/_/g, " ")}: ${p.error ?? p.symbol ?? ""}`,
        tone: "bad",
      };
    default:
      return { text: `${a.event.replace(/_/g, " ")}`, tone: "info" };
  }
}

const toneClass = { info: "text-slate-400", warn: "text-amber-300", bad: "text-rose-300" };

export function AuditLog({ rows }: { rows: AuditRow[] }) {
  const items = rows
    .map((a) => ({ a, d: describe(a) }))
    .filter((x): x is { a: AuditRow; d: NonNullable<ReturnType<typeof describe>> } => x.d !== null);
  if (items.length === 0) {
    return <div className="glass p-4 text-sm text-slate-400">No events yet.</div>;
  }
  return (
    <div className="glass space-y-1.5 p-4 text-xs">
      {items.map(({ a, d }) => (
        <div key={a.id} className="flex gap-3">
          <span className="shrink-0 text-slate-600">{when(a.created_at)}</span>
          <span className={toneClass[d.tone]}>{d.text}</span>
        </div>
      ))}
    </div>
  );
}
