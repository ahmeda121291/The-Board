"use client";

import { useState } from "react";

type Persona = "ceo" | "cfo";
type Msg = { role: "you" | "agent"; text: string };

const SUGGESTIONS = [
  "Why did you hold today?",
  "What would make you fund Directional?",
  "How is each division calibrating?",
  "What's your biggest risk right now?",
];

export function AskBoardroom() {
  const [persona, setPersona] = useState<Persona>("ceo");
  const [q, setQ] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [loading, setLoading] = useState(false);

  async function ask(question: string) {
    const text = question.trim();
    if (!text || loading) return;
    setMsgs((m) => [...m, { role: "you", text }]);
    setQ("");
    setLoading(true);
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: text, persona }),
      });
      const data = await res.json();
      setMsgs((m) => [...m, { role: "agent", text: data.answer || data.error || "No response." }]);
    } catch {
      setMsgs((m) => [...m, { role: "agent", text: "Request failed." }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="glass hud p-5">
      <div className="flex items-center gap-2">
        <span className="text-lg">💬</span>
        <span className="label">Ask the Boardroom</span>
        <div className="ml-auto flex rounded-full border border-white/10 p-0.5 text-xs">
          {(["ceo", "cfo"] as Persona[]).map((p) => (
            <button
              key={p}
              onClick={() => setPersona(p)}
              className={`rounded-full px-3 py-1 uppercase tracking-wide transition ${
                persona === p ? "bg-sky-400/20 text-sky-300" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-3 max-h-80 space-y-3 overflow-y-auto">
        {msgs.length === 0 ? (
          <div className="text-sm text-slate-400">
            Ask the {persona.toUpperCase()} about its decisions — grounded in the real logged data.
            It explains; it can’t place trades.
          </div>
        ) : (
          msgs.map((m, i) => (
            <div key={i} className={m.role === "you" ? "text-right" : ""}>
              <div
                className={`inline-block max-w-[90%] rounded-xl px-3 py-2 text-sm ${
                  m.role === "you"
                    ? "bg-sky-400/15 text-sky-100"
                    : "border border-white/10 bg-white/[0.03] text-slate-200"
                }`}
              >
                <span className="whitespace-pre-wrap">{m.text}</span>
              </div>
            </div>
          ))
        )}
        {loading ? <div className="text-xs text-slate-500">thinking…</div> : null}
      </div>

      {msgs.length === 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => ask(s)}
              className="rounded-full border border-white/10 px-2.5 py-1 text-xs text-slate-300 hover:border-sky-400/40 hover:text-sky-300"
            >
              {s}
            </button>
          ))}
        </div>
      ) : null}

      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask(q);
        }}
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={`Ask the ${persona.toUpperCase()}…`}
          className="flex-1 rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-sky-400/40"
        />
        <button
          type="submit"
          disabled={loading || !q.trim()}
          className="rounded-xl border border-sky-400/30 bg-sky-400/10 px-4 py-2 text-sm text-sky-200 disabled:opacity-40"
        >
          Ask
        </button>
      </form>
    </div>
  );
}
