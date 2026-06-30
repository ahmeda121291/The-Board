-- Equities recommendation engine output (advisory; stocks are never auto-traded).
-- One row per checkpoint: the recommended target portfolio, the user's actual
-- IBKR holdings at that moment, the computed buy/sell/trim/hold actions, and the
-- advisor's plain-English narrative. The dashboard renders the latest row as
-- "Current portfolio vs Recommended portfolio".

create table if not exists boardroom.recommendations (
    id          bigint generated always as identity primary key,
    created_at  timestamptz not null default now(),
    payload     jsonb not null default '{}'::jsonb
);
create index if not exists recommendations_created_idx
    on boardroom.recommendations (created_at desc);

alter table boardroom.recommendations enable row level security;

-- service_role bypasses RLS; the dashboard reads server-side with the service key.
grant all on boardroom.recommendations to service_role;
