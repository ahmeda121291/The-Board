-- Outcomes carry the traded pair, so the scoreboard (and the dashboard's
-- per-trade table) can say WHICH coin performed — not just which division.
-- Legacy rows stay NULL; new resolutions populate it from the position.
alter table boardroom.outcomes add column if not exists symbol text;
