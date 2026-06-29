-- Scan mode for on-demand runs: 'core' (the daily ~21-symbol universe) or
-- 'wide' (the broader curated ~50-symbol set, triggered by the second button).
alter table boardroom.run_requests
    add column if not exists mode text not null default 'core';
