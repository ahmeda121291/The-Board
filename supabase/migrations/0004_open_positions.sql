-- Open positions awaiting resolution — the working set the resolution loop reads
-- each checkpoint to mark funded decisions to market and feed the adaptive engine.
-- A row exists only while a position is open; the resolution loop deletes it once
-- the position resolves (the resolved record lives in `boardroom.outcomes`).

create table if not exists boardroom.open_positions (
    decision_id           uuid primary key references boardroom.decisions (decision_id),
    division              text not null,
    venue                 text not null,
    symbol                text not null,
    size_cad              double precision not null,
    predicted_return      double precision not null,
    predicted_confidence  double precision not null,
    cost_cad              double precision not null,
    stop_fraction         double precision not null,
    band_low              double precision not null,
    band_high             double precision not null,
    horizon_days          double precision not null,
    opened_at             timestamptz not null,
    live                  boolean not null default false
);

-- RLS on, no policies: anon/public denied; the service key bypasses RLS.
alter table boardroom.open_positions enable row level security;
