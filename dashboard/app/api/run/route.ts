import { NextRequest, NextResponse } from "next/server";
import { serverClient } from "@/lib/supabase";

export const dynamic = "force-dynamic";

// "Run now" — request an on-demand checkpoint. This endpoint does NOT trade and
// cannot: the trading keys live only on the user's PC. It inserts a pending row
// into run_requests; a local poller on the PC claims it and runs the real
// checkpoint. The web app stays unable to move money.

// GET → latest request (for the button to show status).
export async function GET() {
  const sb = serverClient();
  if (!sb) return NextResponse.json({ error: "Not connected." }, { status: 503 });
  const { data, error } = await sb
    .from("run_requests")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(1);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ latest: (data ?? [])[0] ?? null });
}

// POST → enqueue a run, unless one is already pending/running.
export async function POST(req: NextRequest) {
  const sb = serverClient();
  if (!sb) return NextResponse.json({ error: "Not connected to Supabase." }, { status: 503 });

  // Don't stack requests — if one is genuinely active, return it. But a request
  // stuck in "running" past 10 min means its poller died mid-run; auto-clear it
  // so the button never jams forever.
  const { data: active } = await sb
    .from("run_requests")
    .select("*")
    .in("status", ["pending", "running"])
    .order("created_at", { ascending: false })
    .limit(1);
  const a = active?.[0];
  if (a) {
    const refMs = new Date(a.claimed_at ?? a.created_at).getTime();
    const stale = a.status === "running" && Date.now() - refMs > 10 * 60 * 1000;
    if (!stale) {
      return NextResponse.json({ queued: false, alreadyActive: true, request: a });
    }
    await sb
      .from("run_requests")
      .update({
        status: "error",
        completed_at: new Date().toISOString(),
        result: { error: "stale — no poller completed it within 10 min" },
      })
      .eq("id", a.id);
  }

  let note: string | undefined;
  try {
    const body = await req.json();
    note = typeof body?.note === "string" ? body.note.slice(0, 200) : undefined;
  } catch {
    // no body is fine
  }

  const { data, error } = await sb
    .from("run_requests")
    .insert({ source: "dashboard", status: "pending", note: note ?? null })
    .select("*")
    .limit(1);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ queued: true, request: (data ?? [])[0] ?? null });
}
