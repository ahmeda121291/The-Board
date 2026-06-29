import * as React from "react";
import { Pill } from "@/components/ui";
import type { Session, SessionPitch } from "@/lib/data";
import { cad, num, pct, price, qty } from "@/lib/format";

function statusTone(s: string) {
  return s === "funded" ? "good" : s === "vetoed" ? "bad" : "warn";
}

function divisionTone(status: string) {
  if (status.startsWith("pitched")) return "cyan";
  if (status.startsWith("floor")) return "good";
  if (status.startsWith("disabled")) return "default";
  return "warn"; // abstained
}

function Metric({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className={`num text-sm ${tone ?? "text-slate-200"}`}>{value}</div>
    </div>
  );
}

function PitchCard({ p }: { p: SessionPitch }) {
  // Reference (entry) price the decision was computed on. Lets us show the
  // human-readable trade plan: price now, ~units, what we think it's worth.
  const px = typeof p.features?.price === "number" ? p.features.price : null;
  const hasPlan = px !== null && px > 0;
  const target = hasPlan ? px * (1 + p.expected_return) : null;     // our fair value
  const units = hasPlan ? p.capital_required / px : null;          // approx (CAD notional; FX at broker)
  const funded = p.status === "funded";
  return (
    <div className="glass hud p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium capitalize">{p.division}</span>
        <span className="num text-slate-400">{p.symbol}</span>
        <span className="text-xs text-slate-500">{p.venue}</span>
        <span className="ml-auto">
          <Pill tone={statusTone(p.status)}>{p.status.toUpperCase()}</Pill>
        </span>
      </div>

      {/* Trade plan — price now, how many units, and what we think it's worth */}
      {hasPlan ? (
        <div className="mt-3 rounded-lg border border-sky-400/20 bg-sky-400/[0.05] p-2.5">
          <div className="label mb-1.5">
            {funded ? "Trade plan · executed" : "Trade plan · if funded"}
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric label="Price now" value={price(px)} />
            <Metric label={`≈ units for ${cad(p.capital_required)}`} value={qty(units)} />
            <Metric label="Our fair value" value={price(target)} tone="text-emerald-300" />
            <Metric
              label="Upside to target"
              value={pct(p.expected_return)}
              tone={p.expected_return >= 0 ? "text-emerald-400" : "text-rose-400"}
            />
          </div>
          <div className="mt-1.5 text-[11px] text-slate-500">
            “Our fair value” = price now × (1 + expected return) over the {num(p.horizon_days, 0)}-day
            horizon. Units are approximate — orders are sized in CAD and the broker converts FX & rounds.
          </div>
        </div>
      ) : null}

      {/* computed numbers — code, not the LLM */}
      <div className="mt-3 grid grid-cols-3 gap-3 sm:grid-cols-6">
        <Metric label="Exp. return" value={pct(p.expected_return)} tone={p.expected_return >= 0 ? "text-emerald-400" : "text-rose-400"} />
        <Metric label="Win prob" value={pct(p.confidence, 0)} />
        <Metric label="Size" value={cad(p.capital_required)} />
        <Metric label="Max loss" value={cad(p.max_loss)} tone="text-rose-300" />
        <Metric label="Est. cost" value={cad(p.expected_cost)} tone="text-amber-300" />
        <Metric label="Horizon" value={`${num(p.horizon_days, 0)}d`} />
      </div>

      {/* narrative — the LLM's words */}
      {(p.opportunity || p.why_now) && (
        <div className="mt-3 space-y-1 border-l-2 border-sky-400/30 pl-3 text-sm">
          {p.opportunity ? <p className="text-slate-200">{p.opportunity}</p> : null}
          {p.why_now ? <p className="text-slate-400"><span className="text-slate-500">Why now:</span> {p.why_now}</p> : null}
        </div>
      )}

      {/* catalyst news — momentum's qualitative confirmation */}
      {p.news && p.news.length > 0 ? (
        <div className="mt-3 rounded-lg border border-violet-400/20 bg-violet-400/[0.04] p-2.5 text-xs">
          <div className="flex items-center gap-1.5">
            <span>📰</span>
            <span className="label">Catalyst news</span>
            {typeof p.features?.news_intensity === "number" ? (
              <span className="num text-violet-300">intensity {p.features.news_intensity.toFixed(2)}</span>
            ) : null}
          </div>
          <ul className="mt-1.5 space-y-1">
            {p.news.slice(0, 3).map((h, i) => (
              <li key={i} className="text-slate-300">• {h}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* risk manager */}
      <div className="mt-3 text-xs">
        <span className="label">Risk manager</span>
        {p.risk_approved === false ? (
          <div className="mt-1 text-rose-300">
            ✗ vetoed — {p.risk_objections.join("; ")}
          </div>
        ) : (
          <div className="mt-1 text-emerald-300">✓ cleared the hard checks</div>
        )}
        {p.risk_concern ? <div className="mt-0.5 text-slate-500">“{p.risk_concern}”</div> : null}
      </div>

      {/* CEO verdict */}
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-white/10 pt-3 text-xs">
        <span className="label">CEO</span>
        {p.ceo_score !== null ? <span className="num text-slate-300">score {num(p.ceo_score, 3)}</span> : null}
        {p.ceo_trust !== null ? <span className="num text-slate-300">trust {num(p.ceo_trust, 2)}</span> : null}
        {p.ceo_size_cad ? <span className="num text-slate-300">size {cad(p.ceo_size_cad)}</span> : null}
        <span className={`ml-auto ${p.status === "funded" ? "text-emerald-300" : "text-amber-300"}`}>{p.reason}</span>
      </div>
    </div>
  );
}

export function SessionView({ session }: { session: Session | null }) {
  if (!session || (!session.pitches?.length && !session.divisions?.length)) {
    return (
      <div className="glass p-4 text-sm text-slate-400">
        No session recorded yet — runs appear here after the first checkpoint.
      </div>
    );
  }
  const pitches = session.pitches ?? [];
  return (
    <div className="space-y-4">
      {/* division roll-call */}
      {session.divisions?.length ? (
        <div className="glass p-4">
          <div className="label mb-2">Division roll-call</div>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            {session.divisions.map((d) => (
              <div key={d.division} className="flex items-center gap-2">
                <Pill tone={divisionTone(d.status)}>{d.division}</Pill>
                <span className="text-xs text-slate-400">{d.status}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* pitches considered */}
      {pitches.length ? (
        <div className="space-y-3">
          {pitches.map((p) => (
            <PitchCard key={p.pitch_id} p={p} />
          ))}
        </div>
      ) : (
        <div className="glass p-4 text-sm text-slate-400">
          No pitches this checkpoint — every division abstained (no fresh edge cleared its
          threshold), so the CEO stayed in the floor. That’s the null default doing its job.
        </div>
      )}
    </div>
  );
}
