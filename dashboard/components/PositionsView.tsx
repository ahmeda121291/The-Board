import { Pill } from "@/components/ui";
import type { OpenPositionRow, PortfolioSnapshot } from "@/lib/data";
import { ago, cad, divLabel, pct, qty, when } from "@/lib/format";

// Section 2 — CURRENT POSITIONS. The positions the system is actively managing:
// what it paid, the exit plan fixed at entry (stop / target / horizon), and —
// when the venue snapshot can price it — what it's worth right now.

const QUOTES = ["CAD", "USDT", "USDC", "USD"];

function baseAsset(symbol: string): string {
  for (const q of QUOTES) {
    if (symbol.endsWith(q) && symbol.length > q.length) return symbol.slice(0, -q.length);
  }
  return symbol;
}

function plannedExit(openedAt: string, horizonDays: number): Date {
  return new Date(new Date(openedAt).getTime() + horizonDays * 86400 * 1000);
}

export function PositionsView({
  positions,
  portfolio,
}: {
  positions: OpenPositionRow[];
  portfolio: PortfolioSnapshot | null;
}) {
  // Unit prices from the latest venue snapshot, keyed by base asset.
  const unitPrice = new Map<string, number>();
  for (const h of portfolio?.crypto?.holdings ?? []) {
    if (h.qty > 0 && h.market_value_cad) unitPrice.set(h.symbol, h.market_value_cad / h.qty);
  }

  if (positions.length === 0) {
    return (
      <div className="glass p-4 text-sm text-slate-400">
        No open positions — all capital is resting in the floor. Positions appear here the moment a
        buy fills, with their stop, target, and auto-exit date.
      </div>
    );
  }

  return (
    <div className="grid gap-3 md:grid-cols-2">
      {positions.map((p) => {
        const base = baseAsset(p.symbol);
        const unit = unitPrice.get(base);
        const value = p.qty > 0 && unit ? p.qty * unit : null;
        const unreal = value !== null ? value - p.size_cad : null;
        const exitBy = plannedExit(p.opened_at, p.horizon_days);
        const overdue = exitBy.getTime() < Date.now();
        return (
          <div key={p.decision_id} className="glass hud p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="num text-base font-semibold text-slate-100">{p.symbol}</span>
              <Pill tone="cyan">{divLabel(p.division)}</Pill>
              <span className="text-xs uppercase tracking-wider text-slate-500">{p.venue}</span>
              <Pill tone={p.live ? "bad" : "default"}>{p.live ? "LIVE" : "paper"}</Pill>
              <span className="ml-auto text-xs text-slate-500" title={when(p.opened_at)}>
                opened {ago(p.opened_at)}
              </span>
            </div>

            <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
              <div>
                <div className="label">Cost basis</div>
                <div className="num mt-0.5 text-slate-200">{cad(p.size_cad)}</div>
              </div>
              <div>
                <div className="label">Value now</div>
                <div className="num mt-0.5 text-slate-200">
                  {value !== null ? cad(value) : "—"}
                </div>
              </div>
              <div>
                <div className="label">Unrealized</div>
                <div
                  className={`num mt-0.5 ${
                    unreal === null ? "text-slate-500" : unreal >= 0 ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {unreal !== null
                    ? `${unreal >= 0 ? "+" : ""}${cad(unreal)} (${pct(unreal / p.size_cad)})`
                    : "—"}
                </div>
              </div>
            </div>

            <div className="mt-3 rounded-lg border border-white/10 bg-white/[0.02] p-2.5 text-xs text-slate-300">
              <span className="text-slate-500">Exit plan (fixed at entry): </span>
              sells on a <span className="text-rose-300">{pct(p.stop_fraction)} stop-loss</span>, a{" "}
              <span className="text-emerald-300">{pct(p.band_high)} take-profit</span>, or{" "}
              <span className={overdue ? "text-amber-300" : "text-slate-200"}>
                {overdue ? "next checkpoint (horizon reached)" : `by ${when(exitBy.toISOString())}`}
              </span>
              .
            </div>

            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
              <span>
                predicted {pct(p.predicted_return)} over {p.horizon_days.toFixed(0)}d · confidence{" "}
                {pct(p.predicted_confidence, 0)}
              </span>
              {p.qty > 0 ? (
                <span className="num">
                  {qty(p.qty)} {base}
                </span>
              ) : (
                <span className="text-amber-300/80" title="Opened before exact-qty tracking; the exit sells by CAD notional instead.">
                  qty not recorded — exit sells by notional
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
