"use client";

import * as React from "react";
import { Pill } from "@/components/ui";
import type { FillRow, RunRow } from "@/lib/data";
import { ago, cad, price, qty, when } from "@/lib/format";

// Section 1 — WHAT IT'S DONE. Confirmed fills only: the broker returned this.
// Not intentions, not recommendations. Live trades by default; paper (dry-run
// simulation) fills behind a toggle so they never masquerade as real money.

const EXIT_LABEL: Record<string, string> = {
  stop_loss: "stop-loss",
  take_profit: "take-profit",
  horizon: "horizon reached",
};

function FillLine({ f }: { f: FillRow }) {
  const buy = f.side === "buy";
  const hasQty = f.qty !== null && f.qty > 0 && f.price !== null && f.price > 0;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-white/5 py-2.5 last:border-0">
      <span className={`num text-sm font-semibold ${buy ? "text-emerald-400" : "text-rose-300"}`}>
        {buy ? "BUY" : "SELL"}
      </span>
      <span className="num text-sm text-slate-100">
        {hasQty ? `${qty(f.qty)} ${f.symbol} @ ${price(f.price)}` : f.symbol}
      </span>
      <span className="num text-sm text-slate-300">{cad(f.notional_cad)}</span>
      <Pill tone={f.is_live ? "bad" : "default"}>{f.is_live ? "LIVE" : "paper"}</Pill>
      <span className="text-xs uppercase tracking-wider text-slate-500">{f.venue}</span>
      {f.exit_reason ? <Pill tone="warn">{EXIT_LABEL[f.exit_reason] ?? f.exit_reason}</Pill> : null}
      {f.fee_cad ? <span className="text-xs text-slate-500">fee {cad(f.fee_cad)}</span> : null}
      <span className="ml-auto text-xs text-slate-500" title={when(f.created_at)}>
        {ago(f.created_at)}
      </span>
    </div>
  );
}

export function Executed({ fills, latestRecon }: { fills: FillRow[]; latestRecon: RunRow["recon"] }) {
  const [showPaper, setShowPaper] = React.useState(false);
  const live = fills.filter((f) => f.is_live);
  const paper = fills.filter((f) => !f.is_live);
  const shown = showPaper ? fills : live;
  const untracked = latestRecon?.untracked ?? [];

  return (
    <div className="space-y-3">
      {untracked.length > 0 ? (
        <div className="rounded-xl border border-rose-400/40 bg-rose-400/[0.07] p-4 text-sm text-rose-200">
          <div className="font-semibold">⚠ Untracked holdings on Kraken</div>
          <div className="mt-1 text-xs leading-relaxed">
            The venue holds{" "}
            {untracked
              .map(
                (u) =>
                  `${qty(u.qty)} ${u.asset}${u.market_value_cad ? ` (≈${cad(u.market_value_cad)})` : ""}`,
              )
              .join(", ")}{" "}
            with no tracked position behind {untracked.length > 1 ? "them" : "it"} — the auto-sell
            engine is not managing {untracked.length > 1 ? "these" : "this"}. Usually the residue of
            a crashed run; adopt or sell manually.
          </div>
        </div>
      ) : latestRecon ? (
        <div className="text-xs text-slate-500">
          ✓ venue holdings reconciled against tracked positions{" "}
          {latestRecon.checked_at ? ago(latestRecon.checked_at) : ""}
        </div>
      ) : null}

      <div className="glass hud p-4">
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400">
            <span className="num text-slate-200">{live.length}</span> live fill
            {live.length === 1 ? "" : "s"}
            {paper.length ? (
              <span className="text-slate-500"> · {paper.length} paper</span>
            ) : null}
          </span>
          {paper.length > 0 ? (
            <button
              onClick={() => setShowPaper((v) => !v)}
              className={`ml-auto rounded-full border px-3 py-1 text-xs transition ${
                showPaper
                  ? "border-sky-400/50 bg-sky-400/10 text-sky-200"
                  : "border-white/10 text-slate-400 hover:border-white/25 hover:text-slate-200"
              }`}
            >
              {showPaper ? "hide paper trades" : "show paper trades"}
            </button>
          ) : null}
        </div>

        {shown.length ? (
          <div className="mt-2">
            {shown.map((f) => (
              <FillLine key={f.id} f={f} />
            ))}
          </div>
        ) : (
          <div className="mt-3 text-sm text-slate-400">
            No {showPaper ? "" : "live "}fills recorded yet. Every confirmed buy and sell lands here
            the moment the exchange returns it.
            {fills.length === 0
              ? " (Trades made before this table existed are only on the venue's own history.)"
              : null}
          </div>
        )}
      </div>
    </div>
  );
}
