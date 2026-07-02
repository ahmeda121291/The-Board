import { serverClient } from "./supabase";

export type DivisionState = {
  division: string;
  alpha: number;
  beta: number;
  leash: number;
  retired: boolean;
  shadow: boolean;
  n_resolved: number;
  net_vs_floor_cad: number;
  updated_at: string;
};

export type Decision = {
  decision_id: string;
  created_at: string;
  kind: string;
  division: string | null;
  pitch_id: string | null;
  size_cad: number;
  hurdle_rate: number;
  rationale: string | null;
  ranked: any; // boardroom session: { hurdle_rate, portfolio_value_cad, pitches[], divisions[] }
  live: boolean;
};

export type SessionPitch = {
  pitch_id: string;
  division: string;
  symbol: string;
  venue: string;
  expected_return: number;
  confidence: number;
  capital_required: number;
  max_loss: number;
  expected_cost: number;
  horizon_days: number;
  opportunity: string;
  why_now: string;
  features: Record<string, number>;
  news?: string[];
  risk_approved: boolean | null;
  risk_objections: string[];
  risk_concern: string;
  ceo_score: number | null;
  ceo_trust: number | null;
  ceo_size_cad: number | null;
  status: "funded" | "vetoed" | "passed" | "shadow";
  reason: string;
};

export type Session = {
  hurdle_rate?: number;
  portfolio_value_cad?: number;
  pitches?: SessionPitch[];
  divisions?: { division: string; status: string }[];
  universe?: Record<string, { venue: string; symbols: string[] }>;
};

export type Pitch = {
  pitch_id: string;
  division: string;
  venue: string;
  symbol: string;
  created_at: string;
  capital_required: number;
  expected_return: number;
  confidence: number;
  time_horizon_days: number;
  max_loss: number;
  expected_cost: number;
  opportunity: string | null;
  why_now: string | null;
  signals: any;
};

export type Outcome = {
  id: number;
  decision_id: string;
  division: string;
  resolved_at: string;
  predicted_return: number;
  realized_return: number;
  predicted_confidence: number;
  win: boolean;
  pnl_cad: number;
  cost_cad: number;
  inside_band: boolean;
  process_luck: string | null;
  postmortem: string | null;
};

export type PerfSnapshot = { id: number; created_at: string; payload: any };
export type WeeklyReport = { id: number; created_at: string; report: string; payload: any };
export type AuditRow = { id: number; created_at: string; event: string; payload: any };
export type Recommendation = { area: string; suggestion: string; requires_human: boolean };
export type StrategyReview = {
  id: number;
  created_at: string;
  headline: string;
  narrative: string;
  recommendations: Recommendation[];
  standing: any;
};

// ---- portfolio snapshot (what's actually held; crypto-only since 2026-07,
// stocks fields remain in older rows and are ignored by the UI) ---------------
export type PortfolioHolding = {
  symbol: string;
  venue: string;
  qty: number;
  market_value_cad: number | null;
  weight: number | null;
  avg_cost: number | null;
  unrealized_pnl_cad: number | null;
  unrealized_pnl_pct: number | null;
  day_change_pct: number | null;
};
export type PortfolioVenueBook = {
  venue: string;
  cash_cad: number | null;
  holdings: PortfolioHolding[];
  holdings_value_cad: number | null;
  total_value_cad: number | null;
  unrealized_pnl_cad: number | null;
};
export type PortfolioMover = {
  symbol: string;
  venue: string;
  day_change_pct: number;
  market_value_cad: number;
};
export type PortfolioSnapshot = {
  generated_at: string;
  crypto: PortfolioVenueBook;
  stocks: PortfolioVenueBook;
  total_value_cad: number;
  crypto_weight: number;
  stocks_weight: number;
  top_gainers: PortfolioMover[];
  top_losers: PortfolioMover[];
};

// ---- fills — confirmed executions (the record of truth) ---------------------
export type FillRow = {
  id: number;
  created_at: string;
  run_id: string | null;
  decision_id: string | null;
  venue: string;
  symbol: string;
  side: "buy" | "sell";
  qty: number | null;
  price: number | null;
  notional_cad: number;
  fee_cad: number | null;
  is_live: boolean;
  order_ref: string | null;
  exit_reason: string | null; // stop_loss | take_profit | horizon (sells only)
};

// ---- runs — per-checkpoint health ------------------------------------------
export type RunRow = {
  run_id: string;
  started_at: string;
  finished_at: string | null;
  trigger: string; // scheduled | run_now | wide | decide | manual
  status: "running" | "ok" | "crashed";
  live: boolean;
  decision_id: string | null;
  decision_kind: string | null;
  error: string | null;
  breakers: string[];
  breakers_evaluated: boolean;
  recon: {
    checked_at?: string;
    untracked?: { asset: string; qty: number; market_value_cad: number | null }[];
  } | null;
};

// ---- open positions — what the system is actively managing -------------------
export type OpenPositionRow = {
  decision_id: string;
  division: string;
  venue: string;
  symbol: string;
  size_cad: number;
  predicted_return: number;
  predicted_confidence: number;
  cost_cad: number;
  stop_fraction: number;
  band_low: number;
  band_high: number;
  horizon_days: number;
  opened_at: string;
  live: boolean;
  qty: number;
};

export type PendingRequest = { id: number; created_at: string; mode: string; status: string };

export type Dashboard = {
  configured: boolean;
  error: string | null;
  divisions: DivisionState[];
  decisions: Decision[];
  pitches: Pitch[];
  outcomes: Outcome[];
  performance: PerfSnapshot | null;
  weekly: WeeklyReport | null;
  audit: AuditRow[];
  strategist: StrategyReview | null;
  reserve_cad: number;
  hwm_cad: number;
  live_armed: boolean;
  // Real venue cash, pulled by the local runner (null until first synced).
  kraken_cash_cad: number | null;
  ibkr_cash_cad: number | null;
  equity_cad: number | null;
  balances_at: string | null;
  // Latest portfolio snapshot (the Kraken book; crypto-only).
  portfolio: PortfolioSnapshot | null;
  // Confirmed executions, run health, managed positions, poller liveness.
  fills: FillRow[];
  runs: RunRow[];
  open_positions: OpenPositionRow[];
  pending_requests: PendingRequest[];
  poller_seen_at: string | null;
};

export async function loadDashboard(): Promise<Dashboard> {
  const empty: Dashboard = {
    configured: false,
    error: null,
    divisions: [],
    decisions: [],
    pitches: [],
    outcomes: [],
    performance: null,
    weekly: null,
    audit: [],
    strategist: null,
    reserve_cad: 0,
    hwm_cad: 0,
    live_armed: false,
    kraken_cash_cad: null,
    ibkr_cash_cad: null,
    equity_cad: null,
    balances_at: null,
    portfolio: null,
    fills: [],
    runs: [],
    open_positions: [],
    pending_requests: [],
    poller_seen_at: null,
  };

  const sb = serverClient();
  if (!sb) return { ...empty, configured: false };

  try {
    const [divisions, decisions, pitches, outcomes, perf, weekly, audit, strategist, sys, pf, fills, runs, openPos, pendingReqs] =
      await Promise.all([
        sb.from("division_state").select("*").order("division"),
        sb.from("decisions").select("*").order("created_at", { ascending: false }).limit(50),
        sb.from("pitches").select("*").order("created_at", { ascending: false }).limit(50),
        sb.from("outcomes").select("*").order("resolved_at", { ascending: false }).limit(200),
        sb.from("performance_snapshots").select("*").order("created_at", { ascending: false }).limit(1),
        sb.from("weekly_reports").select("*").order("created_at", { ascending: false }).limit(1),
        sb.from("audit_log").select("*").order("created_at", { ascending: false }).limit(50),
        sb.from("strategist_reviews").select("*").order("created_at", { ascending: false }).limit(1),
        sb.from("system_state").select("*").eq("id", 1).limit(1),
        sb.from("portfolio_snapshots").select("*").order("created_at", { ascending: false }).limit(1),
        sb.from("fills").select("*").order("created_at", { ascending: false }).limit(60),
        sb.from("runs").select("*").order("started_at", { ascending: false }).limit(15),
        sb.from("open_positions").select("*").order("opened_at", { ascending: false }),
        sb.from("run_requests").select("id,created_at,mode,status").in("status", ["pending", "running"]).order("created_at", { ascending: false }).limit(5),
      ]);

    const firstError =
      divisions.error || decisions.error || pitches.error || outcomes.error || perf.error || weekly.error || audit.error;
    const sysRow = ((sys.data as any[]) ?? [])[0] ?? null;

    return {
      configured: true,
      error: firstError ? firstError.message : null,
      divisions: (divisions.data as DivisionState[]) ?? [],
      decisions: (decisions.data as Decision[]) ?? [],
      pitches: (pitches.data as Pitch[]) ?? [],
      outcomes: (outcomes.data as Outcome[]) ?? [],
      performance: ((perf.data as PerfSnapshot[]) ?? [])[0] ?? null,
      weekly: ((weekly.data as WeeklyReport[]) ?? [])[0] ?? null,
      audit: (audit.data as AuditRow[]) ?? [],
      strategist: ((strategist.data as StrategyReview[]) ?? [])[0] ?? null,
      reserve_cad: sysRow?.reserve_cad ?? 0,
      hwm_cad: sysRow?.hwm_cad ?? 0,
      live_armed: Boolean(sysRow?.live_armed),
      kraken_cash_cad: sysRow?.kraken_cash_cad ?? null,
      ibkr_cash_cad: sysRow?.ibkr_cash_cad ?? null,
      equity_cad: sysRow?.equity_cad ?? null,
      balances_at: sysRow?.balances_at ?? null,
      portfolio: ((pf.data as any[]) ?? [])[0]?.payload ?? null,
      fills: (fills.data as FillRow[]) ?? [],
      runs: ((runs.data as any[]) ?? []).map((r) => ({
        ...r,
        breakers: Array.isArray(r.breakers) ? r.breakers : [],
      })) as RunRow[],
      open_positions: (openPos.data as OpenPositionRow[]) ?? [],
      pending_requests: (pendingReqs.data as PendingRequest[]) ?? [],
      poller_seen_at: sysRow?.poller_seen_at ?? null,
    };
  } catch (e: any) {
    return { ...empty, configured: true, error: e?.message ?? "Unknown error" };
  }
}

// Equity curve: start + cumulative realized P&L over resolved outcomes (ascending).
export function equitySeries(outcomes: Outcome[], start: number): { t: string; equity: number }[] {
  const asc = [...outcomes].sort(
    (a, b) => new Date(a.resolved_at).getTime() - new Date(b.resolved_at).getTime(),
  );
  let eq = start;
  const pts = asc.map((o) => {
    eq += o.pnl_cad || 0;
    return { t: o.resolved_at, equity: Math.round(eq * 100) / 100 };
  });
  return pts;
}

// ---- derived helpers (deterministic; mirror the Python measurement layer) ----
export function calibrationMean(d: DivisionState): number {
  const denom = d.alpha + d.beta;
  return denom > 0 ? d.alpha / denom : 0;
}

export function rollupOutcomes(outcomes: Outcome[]) {
  const n = outcomes.length;
  const pnl = outcomes.reduce((s, o) => s + (o.pnl_cad || 0), 0);
  const cost = outcomes.reduce((s, o) => s + (o.cost_cad || 0), 0);
  const wins = outcomes.filter((o) => o.win).length;
  const attribution: Record<string, number> = {};
  for (const o of outcomes) attribution[o.division] = (attribution[o.division] || 0) + (o.pnl_cad || 0);
  return { n, pnl, cost, hitRate: n ? wins / n : 0, attribution };
}
