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
  if (!snap || snap.total_value_cad <= 0) {
    return (
      <Empty>
        No live portfolio synced yet. Run <code className="text-sky-300">boardroom balances</code> on your
        PC (or wait for the next checkpoint) to pull your real Kraken coins + cash and IBKR holdings.
      </Empty>
    );
  }

  const cw = Math.round(snap.crypto_weight * 100);
  const sw = Math.round(snap.stocks_weight * 100);

  return (
    <div className="space-y-4">
      {/* Merged summary */}
      <div className="glass hud p-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="label">Total equity · both venues</div>
            <div className="num mt-1 text-4xl font-bold text-white glow-cyan">{cad(snap.total_value_cad)}</div>
          </div>
          <div className="text-right text-xs text-slate-400">
            <div className="num">
              <span className="text-sky-300">crypto {cad(snap.crypto.total_value_cad ?? 0)}</span>
              <span className="mx-2 text-slate-600">·</span>
              <span className="text-violet-300">stocks {cad(snap.stocks.total_value_cad ?? 0)}</span>
            </div>
            <div className="mt-1">{snap.generated_at ? `synced ${ago(snap.generated_at)}` : ""}</div>
          </div>
        </div>
        {/* split bar */}
        <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-white/5">
          <div className="bg-sky-400/70" style={{ width: `${cw}%` }} title={`crypto ${cw}%`} />
          <div className="bg-violet-400/70" style={{ width: `${sw}%` }} title={`stocks ${sw}%`} />
        </div>
        <div className="mt-1 flex justify-between text-[10px] uppercase tracking-widest text-slate-500">
          <span>crypto {cw}%</span>
          <span>stocks {sw}%</span>
        </div>
        {/* movers */}
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div>
            <div className="label mb-1.5">Gaining today</div>
            <MoverChips movers={snap.top_gainers} tone="good" />
          </div>
          <div>
            <div className="label mb-1.5">Losing today</div>
            <MoverChips movers={snap.top_losers} tone="bad" />
          </div>
        </div>
      </div>

      {/* Per-venue books */}
      <div className="grid gap-3 lg:grid-cols-2">
        <VenueCard
          title="Crypto portfolio (Kraken)"
          tag="auto-traded"
          tagTone="good"
          book={snap.crypto}
          showPnl={false}
          emptyHint="No coins held — all in cash / the staking floor."
        />
        <VenueCard
          title="Stock portfolio (IBKR)"
          tag="advisory"
          tagTone="violet"
          book={snap.stocks}
          showPnl={true}
          emptyHint="No stock holdings synced (authenticate the IBKR gateway to see them)."
        />
      </div>
      <p className="pl-1 text-xs text-slate-500">
        “Today” is each holding’s intraday price change. Stock unrealized P&amp;L is vs your cost basis
        (from IBKR). Crypto P&amp;L vs cost isn’t shown — Kraken doesn’t expose a simple cost basis — so
        crypto shows value + today’s move.
      </p>
    </div>
  );
}
