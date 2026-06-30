-- Portfolio snapshots: what's actually held across both venues, with per-holding
-- performance. One row per checkpoint (and per `boardroom balances` run): the
-- crypto book (coins + cash + intraday change), the stock book (holdings + cash +
-- unrealized P&L), and the merged split + top movers. The dashboard renders the
-- latest row. Read-only on the dashboard; written by the local runner.

create table if not exists boardroom.portfolio_snapshots (
    id          bigint generated always as identity primary key,
    created_at  timestamptz not null default now(),
    payload     jsonb not null default '{}'::jsonb
);
create index if not exists portfolio_snapshots_created_idx
    on boardroom.portfolio_snapshots (created_at desc);

alter table boardroom.portfolio_snapshots enable row level security;

grant all on boardroom.portfolio_snapshots to service_role;
