import { NextRequest, NextResponse } from "next/server";
import { serverClient } from "@/lib/supabase";

export const dynamic = "force-dynamic";

// "Ask the Boardroom" — talk to the CEO or CFO about the system's decisions.
// Read-only and grounded: it loads the real logged state from Supabase and asks
// the model to answer ONLY from it. It explains decisions; it cannot make or
// change them (a chat box can never trigger a trade).

type Persona = "ceo" | "cfo";

const SYSTEMS: Record<Persona, string> = {
  ceo:
    "You are the CEO of an autonomous capital allocator called Boardroom. You decide where ~$200 CAD " +
    "goes each day across a Yield floor, a Directional (equities) division, and an Event (crypto) division — " +
    "usually nothing. Answer the user's question about your decisions, grounded ONLY in the CONTEXT (real " +
    "logged data). Never invent numbers. If the context lacks the answer, say so. You explain; you do not " +
    "make or change trades here. Be concise, concrete, and honest — most days holding the floor is correct.",
  cfo:
    "You are the CFO / Chief Strategist of Boardroom, an autonomous capital allocator. You study performance, " +
    "calibration, and risk. Answer the user's question grounded ONLY in the CONTEXT (real logged data). Never " +
    "invent numbers. Flag that structural changes need human sign-off. Be concise and strategic.",
};

async function loadContext() {
  const sb = serverClient();
  if (!sb) return null;
  const [decision, divisions, strategist, outcomes, sys] = await Promise.all([
    sb.from("decisions").select("*").order("created_at", { ascending: false }).limit(1),
    sb.from("division_state").select("*").order("division"),
    sb.from("strategist_reviews").select("*").order("created_at", { ascending: false }).limit(1),
    sb.from("outcomes").select("division,realized_return,win,pnl_cad,resolved_at").order("resolved_at", { ascending: false }).limit(15),
    sb.from("system_state").select("*").eq("id", 1).limit(1),
  ]);
  return {
    latest_decision: (decision.data ?? [])[0] ?? null,
    divisions: divisions.data ?? [],
    latest_strategist_review: (strategist.data ?? [])[0] ?? null,
    recent_outcomes: outcomes.data ?? [],
    reserve: ((sys.data ?? [])[0] as any)?.reserve_cad ?? 0,
  };
}

export async function POST(req: NextRequest) {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) {
    return NextResponse.json(
      { error: "Chat is offline — add ANTHROPIC_API_KEY to the Vercel project env." },
      { status: 503 },
    );
  }

  let body: { question?: string; persona?: Persona };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Bad request" }, { status: 400 });
  }
  const question = (body.question ?? "").toString().slice(0, 1000).trim();
  const persona: Persona = body.persona === "cfo" ? "cfo" : "ceo";
  if (!question) return NextResponse.json({ error: "Ask a question." }, { status: 400 });

  const context = await loadContext();
  if (!context) {
    return NextResponse.json({ error: "Not connected to Supabase." }, { status: 503 });
  }

  const model = process.env.BOARDROOM_LLM_MODEL || "claude-opus-4-8";
  const user = `CONTEXT (real logged state of the system):\n${JSON.stringify(context)}\n\nQUESTION: ${question}`;

  try {
    const resp = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model,
        max_tokens: 500,
        system: SYSTEMS[persona],
        messages: [{ role: "user", content: user }],
      }),
    });
    if (!resp.ok) {
      const detail = await resp.text();
      return NextResponse.json(
        { error: `Model error (${resp.status}): ${detail.slice(0, 200)}` },
        { status: 502 },
      );
    }
    const data = await resp.json();
    const answer = (data.content ?? [])
      .filter((b: any) => b.type === "text")
      .map((b: any) => b.text)
      .join("\n")
      .trim();
    return NextResponse.json({ answer: answer || "(no answer)" });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message ?? "Request failed" }, { status: 500 });
  }
}
