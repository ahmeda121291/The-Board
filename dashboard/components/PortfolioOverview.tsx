import { Empty, Pill } from "@/components/ui";
import type { PortfolioSnapshot, PortfolioVenueBook, PortfolioHolding, PortfolioMover } from "@/lib/data";
import { cad, pct, ago } from "@/lib/format";

function ChangeBadge({ v }: { v: number | null }) {
  if (v === null || v === undefined) return <span className="text-slate-500">—</span>;
  const up = v >= 0;
  return (
    <span className={up ? "text-emerald-400" : "text-rose-400"}>
      {up ? "▲" : "▼"} {pct(Math.abs(v))}
    </span>
  );
}

function HoldingRow({ h, showPnl }: { h: PortfolioHolding; showPnl: boolean }) {
  return (
    <div className="flex items-center gap-3 py-1.5 text-sm">
      <span className="num w-16 shrink-0 font-medium text-slate-100">{h.symbol}</span>
      <span className="num w-24 shrink-0 text-slate-300">
        {h.market_value_cad === null ? <span className="text-slate-500">unpriced</span> : cad(h.market_value_cad)}
      </span>
      <span className="num w-12 shrink-0 text-xs text-slate-500">
        {h.weight === null ? "" : pct(h.weight, 0)}
      </span>
      {showPnl ? (
        <span className="num w-24 shrink-0 text-xs">
          {h.unrealized_pnl_cad === null ? (
            <span className="text-slate-500">—</span>
          ) : (
            <span className={h.unrealized_pnl_cad >= 0 ? "text-emerald-400" : "text-rose-400"}>
              {h.unrealized_pnl_cad >= 0 ? "+" : "−"}
              {cad(Math.abs(h.unrealized_pnl_cad))}
              {h.unrealized_pnl_pct !== null ? ` (${pct(h.unrealized_pnl_pct)})` : ""}
            </span>
          )}
        </span>
      ) : null}
      <span className="num ml-auto shrink-0 text-xs">
        <span className="mr-1 text-slate-500">today</span>
        <ChangeBadge v={h.day_change_pct} />
      </span>
    </div>
  );
}

function VenueCard({
  title, tag, tagTone, book, showPnl, emptyHint,
}: {
  title: string; tag: string; tagTone: string; book: PortfolioVenueBook; showPnl: boolean; emptyHint: string;
}) {
  return (
    <div className="glass hud p-4">
      <div className="flex items-center justify-between">
        <span className="label">{title}</span>
        <Pill tone={tagTone}>{tag}</Pill>
      </div>
      <div className="mt-3 flex items-end justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-slate-500">Total value</div>
          <div className="num text-2xl font-semibold text-white glow-cyan">
            {book.total_value_cad === null ? "—" : cad(book.total_value_cad)}
          </div>
        </div>
        <div className="text-right text-xs text-slate-400">
          <div>cash {book.cash_cad === null ? "—" : cad(book.cash_cad)}</div>
          {showPnl && book.unrealized_pnl_cad !== null ? (
            <div className={book.unrealized_pnl_cad >= 0 ? "text-emerald-400" : "text-rose-400"}>
              unrealized {book.unrealized_pnl_cad >= 0 ? "+" : "−"}
              {cad(Math.abs(book.unrealized_pnl_cad))}
            </div>
          ) : null}
        </div>
      </div>
      <div className="my-3 h-px bg-white/10" />
      {book.holdings.length === 0 ? (
        <p className="text-sm text-slate-500">{emptyHint}</p>
      ) : (
        <div className="divide-y divide-white/5">
          {book.holdings.map((h) => (
            <HoldingRow key={`${h.venue}-${h.symbol}`} h={h} showPnl={showPnl} />
          ))}
        </div>
      )}
    </div>
  );
}

function MoverChips({ movers, tone }: { movers: PortfolioMover[]; tone: "good" | "bad" }) {
  if (!movers.length) return <span className="text-xs text-slate-500">—</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {movers.map((m) => (
        <span
          key={`${m.venue}-${m.symbol}`}
          className={`num rounded-md border px-2 py-1 text-xs ${
            tone === "good"
              ? "border-emerald-400/30 text-emerald-300 bg-emerald-400/5"
              : "border-rose-400/30 text-rose-300 bg-rose-400/5"
          }`}
        >
          {m.symbol} {m.day_change_pct >= 0 ? "+" : ""}
          {pct(m.day_change_pct)}
        </span>
      ))}
    </div>
  );
}

export function PortfolioOverview({ snap }: { snap: PortfolioSnapshot | null }) {
  // Crypto-only: equities are sunset, so only the Kraken book renders. Any
  // stocks fields still present in older snapshots are simply ignored.
  const crypto = snap?.crypto ?? null;
  if (!snap || !crypto || (crypto.total_value_cad ?? 0) <= 0) {
    return (
      <Empty>
        No live portfolio synced yet. Run <code className="text-sky-300">boardroom balances</code> on your
        PC (or wait for the next checkpoint) to pull your real Kraken coins + cash.
      </Empty>
    );
  }

  const gainers = snap.top_gainers.filter((m) => m.venue === "kraken");
  const losers = snap.top_losers.filter((m) => m.venue === "kraken");

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="glass hud p-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="label">Total equity · Kraken</div>
            <div className="num mt-1 text-4xl font-bold text-white glow-cyan">
              {cad(crypto.total_value_cad ?? 0)}
            </div>
          </div>
          <div className="text-right text-xs text-slate-400">
            <div className="num text-sky-300">
              cash {crypto.cash_cad === null ? "—" : cad(crypto.cash_cad)}
            </div>
            <div className="mt-1">{snap.generated_at ? `synced ${ago(snap.generated_at)}` : ""}</div>
          </div>
        </div>
        {/* movers */}
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div>
            <div className="label mb-1.5">Gaining today</div>
            <MoverChips movers={gainers} tone="good" />
          </div>
          <div>
            <div className="label mb-1.5">Losing today</div>
            <MoverChips movers={losers} tone="bad" />
          </div>
        </div>
      </div>

      {/* The Kraken book */}
      <VenueCard
        title="Crypto portfolio (Kraken)"
        tag="auto-traded"
        tagTone="good"
        book={crypto}
        showPnl={false}
        emptyHint="No coins held — all in cash / the staking floor."
      />
      <p className="pl-1 text-xs text-slate-500">
        “Today” is each coin’s intraday price change. P&amp;L vs cost isn’t shown — Kraken doesn’t
        expose a simple cost basis — so each coin shows value + today’s move.
      </p>
    </div>
  );
}
