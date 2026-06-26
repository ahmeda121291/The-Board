"use client";

import { useCallback, useEffect, useState } from "react";

type RunRequest = {
  id: number;
  created_at: string;
  status: "pending" | "running" | "done" | "error";
  source: string;
  result: any;
  completed_at: string | null;
};

function statusLabel(r: RunRequest | null): { text: string; tone: string } {
  if (!r) return { text: "idle", tone: "text-slate-400" };
  switch (r.status) {
    case "pending":
      return { text: "queued — waiting for your PC to pick it up…", tone: "text-amber-300" };
    case "running":
      return { text: "running on your PC…", tone: "text-sky-300" };
    case "error":
      return { text: `error: ${r.result?.error ?? "unknown"}`, tone: "text-rose-300" };
    case "done": {
      const kind = r.result?.kind ? String(r.result.kind).toLowerCase() : "";
      const k = kind ? kind.toUpperCase() : "DONE";
      const div = r.result?.division ? ` ${r.result.division}` : "";
      // A HOLD / FUND_NONE places no order, so "no trade" — not "dry-run".
      // dry-run only means a simulated FUND that wasn't sent live.
      const tag = r.result?.live ? " · LIVE" : kind === "fund" ? " · dry-run" : " · no trade";
      return { text: `last run: ${k}${div}${tag}`, tone: "text-emerald-300" };
    }
  }
}

export function RunNow() {
  const [latest, setLatest] = useState<RunRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/run", { method: "GET", cache: "no-store" });
      const data = await res.json();
      setLatest(data.latest ?? null);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // While a request is active, poll faster so the user sees it progress.
  useEffect(() => {
    const active = latest?.status === "pending" || latest?.status === "running";
    if (!active) return;
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [latest?.status, refresh]);

  async function run() {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch("/api/run", { method: "POST" });
      const data = await res.json();
      if (data.alreadyActive) setMsg("A run is already queued or in progress.");
      else if (data.queued) setMsg("Requested — your PC will run it shortly.");
      else if (data.error) setMsg(data.error);
      await refresh();
    } catch {
      setMsg("Request failed.");
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  const active = latest?.status === "pending" || latest?.status === "running";
  const s = statusLabel(latest);

  return (
    <div className="glass hud flex flex-wrap items-center gap-3 p-4">
      <div className="flex items-center gap-2">
        <span className="text-lg">⚡</span>
        <span className="label">Run a checkpoint now</span>
      </div>

      {!confirming ? (
        <button
          onClick={() => setConfirming(true)}
          disabled={busy || active}
          className="rounded-xl border border-sky-400/30 bg-sky-400/10 px-4 py-2 text-sm text-sky-200 transition hover:bg-sky-400/20 disabled:opacity-40"
        >
          {active ? "Run in progress…" : "Run now"}
        </button>
      ) : (
        <div className="flex items-center gap-2">
          <span className="text-xs text-amber-300">
            Convene the boardroom now? It may place a real trade if the CEO funds.
          </span>
          <button
            onClick={run}
            disabled={busy}
            className="rounded-xl border border-emerald-400/40 bg-emerald-400/10 px-3 py-1.5 text-sm text-emerald-200 disabled:opacity-40"
          >
            {busy ? "…" : "Yes, run it"}
          </button>
          <button
            onClick={() => setConfirming(false)}
            disabled={busy}
            className="rounded-xl border border-white/15 px-3 py-1.5 text-sm text-slate-300"
          >
            Cancel
          </button>
        </div>
      )}

      <div className={`ml-auto text-xs ${s.tone}`}>{s.text}</div>
      {msg ? <div className="w-full text-xs text-slate-400">{msg}</div> : null}
      <div className="w-full text-[11px] leading-relaxed text-slate-500">
        Requests a run on your PC (where the keys are) — the dashboard never trades directly. Needs the
        local poller running (<code className="text-slate-400">boardroom poll --confirm-live</code>).
      </div>
    </div>
  );
}
