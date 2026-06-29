-- Real venue cash balances on the singleton system_state row. The local runner
-- (which holds the venue keys) pulls these each checkpoint / via `boardroom
-- balances` and the dashboard renders them, so equity reflects reality instead
-- of a hardcoded deposit baseline.

alter table boardroom.system_state add column if not exists kraken_cash_cad double precision;
alter table boardroom.system_state add column if not exists ibkr_cash_cad   double precision;
alter table boardroom.system_state add column if not exists equity_cad      double precision;
alter table boardroom.system_state add column if not exists balances_at     timestamptz;
