import { Empty, Pill } from "@/components/ui";
import type { RecommendationPayload, RecAction } from "@/lib/data";
import { cad, pct, price, ago } from "@/lib/format";

const actionTone: Record<string, string> = {
  buy: "good",
  add: "cyan",
  trim: "warn",
  sell: "bad",
  hold: "default",
};
const actionVerb: Record<string, string> = {
  buy: "Buy",
  add: "Add",
  trim: "Trim",
  sell: "Sell",
  hold: "Hold",
};

function ActionRow({ a }: { a: RecAction }) {
  const positive = a.delta_cad >= 0;
  return (
    <div className="flex items-center gap-3 py-2">
      <span className="w-16 shrink-0">
        <Pill tone={actionTone[a.action] ?? "default"}>{actionVerb[a.action] ?? a.action}</Pill>
      </span>
      <span className="num w-16 shrink-0 font-medium text-slate-100">{a.symbol}</span>
      <span className="num shrink-0 text-sm text-slate-300">
        {a.action === "hold" ? (
          <span className="text-slate-500">on target</span>
        ) : (
          <span className={positive ? "text-emerald-400" : "text-rose-400"}>
            {positive ? "+" : "−"}
            {cad(Math.abs(a.delta_cad))}
          </span>
        )}
      </span>
      <span className="truncate text-xs text-slate-500">{a.reason}</span>
    </div>
  );
}

export function Portfolio({ rec }: { rec: RecommendationPayload | null }) {
  if (!rec) {
    return (
      <Empty>
        No stock recommendation yet — it’s published each checkpoint (twice daily). Stocks are
        advisory: the system tells you what to buy/sell in IBKR but never trades them itself.
      </Empty>
    );
  }

  const moves = rec.actions.filter((a) => a.action !== "hold");
  const held = rec.current ?? [];
  const recs = rec.holdings ?? [];

  return (
    <div className="space-y-4">
      {/* The plain-English advisory note */}
      <div className="glass hud p-5">
        <div className="flex items-center gap-2">
          <span className="text-lg">🧭</span>
          <span className="label">What to do in your IBKR account</span>
          <span className="ml-auto text-xs text-slate-500">
            {rec.generated_at ? ago(rec.generated_at) : ""}
          </span>
        </div>
        <p className="mt-2 text-[15px] leading-relaxed text-slate-100">{rec.narrative}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <Pill tone="violet">advisory · you place the orders</Pill>
          <span>scanned {rec.universe_size} stocks</span>
          <span className="text-slate-600">·</span>
          <span>stock book ≈ {cad(rec.stock_equity_cad)}</span>
          <span className="text-slate-600">·</span>
          <span>{pct(rec.cash_weight, 0)} cash</span>
        </div>
      </div>

      {/* The actionable diff */}
      {moves.length > 0 ? (
        <div className="glass hud p-4">
          <div className="label mb-1">Suggested changes</div>
          <div className="divide-y divide-white/5">
            {rec.actions.map((a) => (
              <ActionRow key={`${a.action}-${a.symbol}`} a={a} />
            ))}
          </div>
        </div>
      ) : (
        <div className="glass p-4 text-sm text-slate-300">
          ✓ Your holdings already match the recommended portfolio — nothing to do.
        </div>
      )}

      {/* Side by side: what you hold vs what's recommended */}
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="glass hud p-4">
          <div className="label mb-3">Current portfolio in IBKR</div>
          {held.length === 0 ? (
            <p className="text-sm text-slate-500">
              No stock holdings synced. (Holdings appear once the IBKR gateway is authenticated and a
              checkpoint runs.)
            </p>
          ) : (
            <div className="space-y-2">
              {held.map((h) => (
                <div key={h.symbol} className="flex items-center justify-between text-sm">
                  <span className="num font-medium text-slate-100">{h.symbol}</span>
                  <span className="num text-slate-300">
                    {cad(h.market_value_cad)}
                    <span className="ml-2 text-xs text-slate-500">@ {price(h.avg_cost)}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="glass hud p-4">
          <div className="label mb-3">Recommended portfolio</div>
          {recs.length === 0 ? (
            <p className="text-sm text-slate-500">
              Nothing in the scanned universe beat the cash floor after costs — holding stock cash is
              the recommendation.
            </p>
          ) : (
            <div className="space-y-2">
              {recs.map((h) => (
                <div key={h.symbol} className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    <span className="num font-medium text-slate-100">{h.symbol}</span>
                    <span className="text-xs text-slate-500">{pct(h.target_weight, 0)}</span>
                  </span>
                  <span className="num text-slate-300">
                    {cad(h.target_cad)}
                    <span className="ml-2 text-xs text-emerald-400/80">exp {pct(h.expected_return)}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
