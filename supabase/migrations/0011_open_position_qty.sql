-- Track the filled base-asset quantity on an open position, so the auto-sell
-- exit can close exactly what was bought (stop-loss / take-profit / horizon).

alter table boardroom.open_positions
    add column if not exists qty double precision not null default 0;
