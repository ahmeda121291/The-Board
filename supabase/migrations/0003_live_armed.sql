-- Durable "armed for live trading" flag on the singleton system_state row.
-- The dashboard reads this so the live/armed status reflects configuration
-- persistently — independent of recent scheduler heartbeats or redeploys.

alter table boardroom.system_state
    add column if not exists live_armed boolean not null default false;

alter table boardroom.system_state
    add column if not exists live_armed_at timestamptz;
