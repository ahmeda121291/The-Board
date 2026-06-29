-- Persisted model coefficients per division, written by the guardrailed
-- walk-forward refit. Lets a re-fit survive restarts/redeploys; absent a row,
-- a division uses its documented prior coefficients.

create table if not exists boardroom.model_params (
    division    text primary key,
    params      jsonb not null,
    updated_at  timestamptz not null default now()
);

-- RLS on, no policies: anon/public denied; the service key bypasses RLS.
alter table boardroom.model_params enable row level security;
