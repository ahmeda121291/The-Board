-- The Strategist (CFO) agent's reviews, and the gains-ratchet reserve / HWM.

create table if not exists boardroom.strategist_reviews (
    id              bigint generated always as identity primary key,
    created_at      timestamptz not null default now(),
    headline        text not null,
    narrative       text not null,
    recommendations jsonb not null default '[]'::jsonb,
    standing        jsonb not null default '{}'::jsonb
);
create index if not exists strategist_created_idx on boardroom.strategist_reviews (created_at desc);

-- Single-row system state: the untouchable reserve and the high-water mark.
create table if not exists boardroom.system_state (
    id           int primary key default 1,
    reserve_cad  double precision not null default 0,
    hwm_cad      double precision not null default 0,
    updated_at   timestamptz not null default now(),
    constraint system_state_singleton check (id = 1)
);
insert into boardroom.system_state (id) values (1) on conflict (id) do nothing;

alter table boardroom.strategist_reviews enable row level security;
alter table boardroom.system_state enable row level security;
