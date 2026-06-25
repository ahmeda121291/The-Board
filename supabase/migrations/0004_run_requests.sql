-- On-demand run requests. The dashboard "Run now" button inserts a row here
-- (keys never leave the user's PC); a local poller on the PC claims pending
-- rows and runs the real checkpoint locally, then marks them done/error.
--
-- The web app can REQUEST a run but never executes one — the read-only safety
-- property of the dashboard is preserved (it writes a request, not a trade).

create table if not exists boardroom.run_requests (
    id            bigserial primary key,
    created_at    timestamptz not null default now(),
    status        text not null default 'pending',   -- pending | running | done | error
    source        text not null default 'dashboard',
    note          text,
    result        jsonb,
    decision_id   uuid,
    claimed_at    timestamptz,
    completed_at  timestamptz
);

create index if not exists run_requests_status_idx
    on boardroom.run_requests (status, created_at);

alter table boardroom.run_requests enable row level security;
