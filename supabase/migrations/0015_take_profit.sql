-- Exit-asymmetry fix (2026-07-27): the take-profit becomes an explicit,
-- reachable trigger (an R-multiple of the capped stop) instead of the predicted
-- band top (~+20-28%, hit once in 29 live trades). 0 = legacy row: the
-- resolution loop falls back to band_high so pre-existing open positions keep
-- their original exit behavior.

alter table boardroom.open_positions
    add column if not exists take_profit double precision not null default 0;
