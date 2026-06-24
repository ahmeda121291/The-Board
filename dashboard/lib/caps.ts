// Cap percentages for display. Defaults mirror boardroom/config.py. Optionally
// override by setting the same env vars on the dashboard's Vercel project so the
// Docs page reflects your live configuration.
export function caps() {
  const n = (k: string, d: number) => {
    const v = Number(process.env[k]);
    return Number.isFinite(v) ? v : d;
  };
  return {
    totalDeployable: n("TOTAL_DEPLOYABLE_PCT", 0.8),
    perTrade: n("PER_TRADE_MAX_PCT", 0.2),
    eventCap: n("EVENT_HARD_CAP_PCT", 0.05),
    dailyLoss: n("DAILY_LOSS_LIMIT_PCT", 0.06),
    maxDrawdown: n("MAX_DRAWDOWN_PCT", 0.15),
    feeDrag: n("FEE_DRAG_LIMIT_PCT", 0.05),
    startingPortfolio: n("STARTING_PORTFOLIO_CAD", 200),
  };
}
