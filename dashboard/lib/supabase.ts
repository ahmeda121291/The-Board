import { createClient } from "@supabase/supabase-js";

// Server-only Supabase client, scoped to the `boardroom` schema. Uses the
// service key (full read access; the schema has RLS on, service_role bypasses).
// NEVER import this from a client component — the key must never reach the browser.
export function serverClient() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) {
    return null;
  }
  return createClient(url, key, {
    db: { schema: "boardroom" },
    auth: { persistSession: false },
  });
}

export const isConfigured = () =>
  Boolean(process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_KEY);
