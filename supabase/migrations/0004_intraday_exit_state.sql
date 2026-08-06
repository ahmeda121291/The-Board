-- Intraday exit engine (2026-08-06): persist per-position trailing-exit state.
--
-- Why: on 2026-08-06 the book rode LIT +75% overnight to ~$969 and round-tripped
-- to a -14% stop-out while four checkpoints watched. Exits evaluated on DAILY
-- closes, so the whole move lived inside one candle; the trailing stop's
-- armed/peak state was recomputed from those closes on every walk and the
-- intraday peak never registered anywhere. Resolution now runs on intraday
-- bars, and the state below makes the ride durable across checkpoint restarts
-- and rolling bar windows.
--
--   entry_price  — the analysis-series (USD pair) price at fill time; 0 = legacy
--                  row, recovered from the series by timestamp instead.
--   peak_return  — best post-entry fractional return seen (off bar HIGHS).
--   trail_armed  — the take-profit printed and the trailing stop is live.

alter table boardroom.open_positions
  add column if not exists entry_price double precision not null default 0,
  add column if not exists peak_return double precision not null default 0,
  add column if not exists trail_armed boolean not null default false;
