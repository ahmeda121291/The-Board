-- Execution truth + run health — the two tables the dashboard rework rides on.
--
-- fills: every order the broker actually returned a fill for (live or paper),
-- written SYNCHRONOUSLY the moment the broker responds — before any other
-- persistence — so a mid-run crash can never lose the record of money moving.
--
-- runs: one row per checkpoint with started/finished/crashed status, the
-- breaker evaluation, and the venue reconciliation result — so a crashed run
-- shows up as a crash on the dashboard instead of silence.

create table if not exists boardroom.fills (
    id           bigint generated always as identity primary key,
    created_at   timestamptz not null default now(),
    run_id       uuid,
    decision_id  uuid,
    venue        text not null,
    symbol       text not null,
    side         text not null,               -- buy | sell
    qty          double precision,
    price        double precision,
    notional_cad double precision not null,
    fee_cad      double precision,
    is_live      boolean not null default false,
    order_ref    text,                        -- broker txid when available
    exit_reason  text                         -- stop_loss | take_profit | horizon (sells)
);
create index if not exists fills_created_idx on boardroom.fills (created_at desc);
alter table boardroom.fills enable row level security;

create table if not exists boardroom.runs (
    run_id             uuid primary key,
    started_at         timestamptz not null default now(),
    finished_at        timestamptz,
    trigger            text not null,          -- scheduled | run_now | wide | decide | manual
    status             text not null default 'running',  -- running | ok | crashed
    live               boolean not null default false,
    decision_id        uuid,
    decision_kind      text,
    error              text,
    breakers           jsonb not null default '[]'::jsonb,
    breakers_evaluated boolean not null default false,
    recon              jsonb                   -- {checked_at, untracked:[{asset,qty}], ...}
);
create index if not exists runs_started_idx on boardroom.runs (started_at desc);
alter table boardroom.runs enable row level security;

-- Poller liveness for the dashboard health strip (updated every poll cycle).
alter table boardroom.system_state
    add column if not exists poller_seen_at timestamptz;
