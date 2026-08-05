-- Venue-refused assets (regional permission errors). Kraken can list a pair
-- yet refuse orders for this account's jurisdiction (2026-08-05: BLESSUSD
-- bounced with "EAccount:Invalid permissions: BLESS trading restricted for
-- CA:ON" and burned a funding slot). Assets that bounce this way are
-- remembered here and excluded from funding before they eat another slot.
alter table boardroom.system_state
  add column if not exists restricted_assets jsonb not null default '[]'::jsonb;
