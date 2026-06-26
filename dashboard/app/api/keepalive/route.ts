import { NextRequest, NextResponse } from "next/server";
import { serverClient } from "@/lib/supabase";

export const dynamic = "force-dynamic";

// Daily keep-alive. A Vercel Cron (see vercel.json) hits this once a day so the
// Supabase project never idles out and gets paused — which removes its DNS and
// breaks every local run. A trivial read is enough to count as activity.
//
// Runs on Vercel (always on), independent of whether the user's PC is awake.

export async function GET(req: NextRequest) {
  // If CRON_SECRET is configured, require it (Vercel cron sends it as a Bearer
  // token). Without the env set, allow the call so setup isn't blocked.
  const secret = process.env.CRON_SECRET;
  if (secret) {
    const auth = req.headers.get("authorization");
    if (auth !== `Bearer ${secret}`) {
      return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
    }
  }

  const sb = serverClient();
  if (!sb) return NextResponse.json({ ok: false, error: "not connected" }, { status: 503 });

  // Cheapest possible touch of the database.
  const { error } = await sb.from("system_state").select("id").limit(1);
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });

  return NextResponse.json({ ok: true, pinged: true });
}
