-- Boardroom state & metrics schema.
-- Lives in a dedicated `boardroom` schema so it never collides with anything in
-- `public`. The service key reads/writes this; it has NO trading power.

create schema if not exists boardroom;

-- Live adaptive state per division (calibration posterior, leash, retirement).
create table if not exists boardroom.division_state (
    division          text primary key,
    alpha             double precision not null default 1.0,
    beta              double precision not null default 1.0,
    leash             double precision not null default 1.0,
    retired           boolean not null default false,
    shadow            boolean not null default false,
    n_resolved        integer not null default 0,
    net_vs_floor_cad  double precision not null default 0.0,
    updated_at        timestamptz not null default now()
);

-- Every pitch a division produces (computed fields + narrative + provenance).
create table if not exists boardroom.pitches (
    pitch_id           uuid primary key,
    division           text not null,
    venue              text not null,
    symbol             text not null,
    created_at         timestamptz not null default now(),
    capital_required   double precision not null,
    expected_return    double precision not null,
    confidence         double precision not null,
    time_horizon_days  double precision not null,
    max_loss           double precision not null,
    expected_cost      double precision not null,
    opportunity        text,
    why_now            text,
    snapshot           jsonb not null,   -- data-snapshot incl. content_hash
    signals            jsonb not null    -- computed features + model version
);
create index if not exists pitches_division_idx on boardroom.pitches (division, created_at desc);

-- Every CEO decision (one kind: fund / fund_none / hold), with the full ranking.
create table if not exists boardroom.decisions (
    decision_id   uuid primary key,
    created_at    timestamptz not null default now(),
    kind          text not null,
    division      text,
    pitch_id      uuid references boardroom.pitches (pitch_id),
    size_cad      double precision not null default 0,
    hurdle_rate   double precision not null default 0,
    rationale     text,
    ranked        jsonb not null default '[]'::jsonb,
    live          boolean not null default false
);
create index if not exists decisions_created_idx on boardroom.decisions (created_at desc);

-- Resolved outcomes — the scoreboard the learning loop reads.
create table if not exists boardroom.outcomes (
    id                    bigint generated always as identity primary key,
    decision_id           uuid references boardroom.decisions (decision_id),
    division              text not null,
    resolved_at           timestamptz not null default now(),
    predicted_return      double precision not null,
    realized_return       double precision not null,
    predicted_confidence  double precision not null,
    win                   boolean not null,
    pnl_cad               double precision not null,
    cost_cad              double precision not null,
    inside_band           boolean not null,
    process_luck          text,
    postmortem            text
);
create index if not exists outcomes_division_idx on boardroom.outcomes (division, resolved_at desc);

-- Daily performance snapshots and the weekly plain-language report.
create table if not exists boardroom.performance_snapshots (
    id          bigint generated always as identity primary key,
    created_at  timestamptz not null default now(),
    payload     jsonb not null
);

create table if not exists boardroom.weekly_reports (
    id          bigint generated always as identity primary key,
    created_at  timestamptz not null default now(),
    report      text not null,
    payload     jsonb not null default '{}'::jsonb
);

-- Cross-cutting audit log. Every interesting event writes here. Never deleted.
create table if not exists boardroom.audit_log (
    id          bigint generated always as identity primary key,
    created_at  timestamptz not null default now(),
    event       text not null,
    payload     jsonb not null default '{}'::jsonb
);

-- Seed the four divisions so the CEO has state to read on day one.
insert into boardroom.division_state (division, shadow)
values ('yield', false), ('directional', true), ('event', true), ('effort', true)
on conflict (division) do nothing;

-- Expose the schema to PostgREST so the supabase-py client can reach it, and
-- grant the API roles access. The service_role bypasses RLS (backend only).
grant usage on schema boardroom to anon, authenticated, service_role;
grant all on all tables in schema boardroom to service_role;
grant all on all sequences in schema boardroom to service_role;
alter default privileges in schema boardroom grant all on tables to service_role;
alter default privileges in schema boardroom grant all on sequences to service_role;
