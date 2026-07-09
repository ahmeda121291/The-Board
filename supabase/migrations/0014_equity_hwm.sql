-- Live-equity high-water mark (deposits + market moves), used by the drawdown
-- breaker. Separate from hwm_cad, which stays on the realized-P&L basis the
-- gains ratchet needs (a deposit must never be swept as a "gain").
alter table boardroom.system_state add column if not exists equity_hwm_cad double precision;
