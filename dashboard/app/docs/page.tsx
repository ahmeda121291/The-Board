import Link from "next/link";
import { Pill, Section, Table } from "@/components/ui";
import { caps } from "@/lib/caps";
import { cad, pct } from "@/lib/format";

export const dynamic = "force-dynamic";

export default function DocsPage() {
  const c = caps();
  const pv = c.startingPortfolio;
  const row = (name: string, frac: number, note: string) => (
    <tr className="hover:bg-white/[0.02]">
      <td className="px-4 py-3 font-medium">{name}</td>
      <td className="num px-4 py-3 text-sky-300">{pct(frac, 0)}</td>
      <td className="num px-4 py-3 text-slate-300">{cad(frac * pv)}</td>
      <td className="px-4 py-3 text-xs text-slate-400">{note}</td>
    </tr>
  );

  return (
    <main className="mx-auto max-w-5xl px-5 py-8">
      <header className="flex items-center gap-4">
        <div>
          <h1 className="title-grad text-3xl font-bold tracking-tight">DOCS</h1>
          <p className="mt-1 text-xs uppercase tracking-[0.25em] text-slate-500">
            how the machine operates
          </p>
        </div>
        <Link
          href="/"
          className="ml-auto rounded-full border border-white/15 px-3 py-1.5 text-xs text-slate-300 hover:border-white/30 hover:bg-white/5"
        >
          ← back to dashboard
        </Link>
      </header>

      <a
        href="https://github.com/ahmeda121291/the-board/blob/main/docs/SCOPE.md"
        target="_blank"
        rel="noopener noreferrer"
        className="glass hud mt-6 flex items-center gap-3 p-4 transition hover:border-sky-400/40"
      >
        <span className="text-2xl">📜</span>
        <div>
          <div className="text-sm font-semibold text-sky-300 glow-cyan">
            The living scope ↗
          </div>
          <div className="text-xs text-slate-400">
            The canonical, continuously-updated spec — supersedes the original document and is kept
            in sync with the code on every change. This is the full picture of how everything works.
          </div>
        </div>
      </a>

      <div className="glass hud mt-6 p-5">
        <div className="text-sm font-semibold text-sky-300 glow-cyan">The grounding law</div>
        <p className="mt-2 text-sm leading-relaxed text-slate-200">
          <b>The LLM reasons; code calculates.</b> No quantitative field the system acts on is ever
          produced by an LLM’s free-form judgment. Expected return, win probability, size, max loss,
          and cost all come from deterministic, unit-tested functions on real market data. The
          language model only writes narrative and adjudicates qualitative calls.
        </p>
      </div>

      <Section title="Scanning & decision frequency" desc="Frequency matches the slowest feedback loop, not the fastest data feed.">
        <Table head={["Division", "Cadence", "Why"]}>
          <tr className="hover:bg-white/[0.02]">
            <td className="px-4 py-3 font-medium">Yield (floor)</td>
            <td className="px-4 py-3"><Pill tone="good">continuous / passive</Pill></td>
            <td className="px-4 py-3 text-slate-300">The default resting state, not a decision.</td>
          </tr>
          <tr className="hover:bg-white/[0.02]">
            <td className="px-4 py-3 font-medium">Directional (equities)</td>
            <td className="px-4 py-3"><Pill tone="cyan">review daily · hold days–weeks</Pill></td>
            <td className="px-4 py-3 text-slate-300">Look daily; expect to mostly hold or pass.</td>
          </tr>
          <tr className="hover:bg-white/[0.02]">
            <td className="px-4 py-3 font-medium">Event (crypto)</td>
            <td className="px-4 py-3"><Pill tone="warn">trigger-driven · unscheduled</Pill></td>
            <td className="px-4 py-3 text-slate-300">Pitches only when quant triggers fire — maybe zero for weeks.</td>
          </tr>
          <tr className="hover:bg-white/[0.02]">
            <td className="px-4 py-3 font-medium">Effort (disabled)</td>
            <td className="px-4 py-3"><Pill>weekly at most</Pill></td>
            <td className="px-4 py-3 text-slate-300">Feedback too slow to touch more often.</td>
          </tr>
        </Table>
        <p className="mt-3 pl-1 text-sm text-slate-400">
          The <b className="text-slate-200">CEO convenes once daily</b> as a checkpoint. The expected
          output of most checkpoints is <b className="text-amber-300">HOLD — stay in the floor.</b>{" "}
          Calendar-driven action is the enemy.
        </p>
      </Section>

      <Section title="The agents" desc="Specialists hunt; one generalist decides; a measurement layer keeps everyone honest.">
        <Table head={["Agent", "Role", "Reasoning vs math"]}>
          <tr className="hover:bg-white/[0.02]">
            <td className="px-4 py-3 font-medium">Divisions</td>
            <td className="px-4 py-3 text-slate-300">Hunt one orthogonal opportunity type; pitch or abstain.</td>
            <td className="px-4 py-3 text-xs text-slate-400">Numbers computed; narrative LLM-authored.</td>
          </tr>
          <tr className="hover:bg-white/[0.02]">
            <td className="px-4 py-3 font-medium">CEO</td>
            <td className="px-4 py-3 text-slate-300">Ranks vs the floor, weights by demonstrated calibration, sizes by conviction, or holds.</td>
            <td className="px-4 py-3 text-xs text-slate-400">Ranking/sizing deterministic; LLM writes rationale.</td>
          </tr>
          <tr className="hover:bg-white/[0.02]">
            <td className="px-4 py-3 font-medium">Risk Manager</td>
            <td className="px-4 py-3 text-slate-300">Adversarially challenges every surviving pitch.</td>
            <td className="px-4 py-3 text-xs text-slate-400">Hard vetoes are code the LLM can’t talk past.</td>
          </tr>
          <tr className="hover:bg-white/[0.02]">
            <td className="px-4 py-3 font-medium">Critic</td>
            <td className="px-4 py-3 text-slate-300">Scores each resolved decision: calibration, process-vs-luck.</td>
            <td className="px-4 py-3 text-xs text-slate-400">Calibration math deterministic; LLM writes post-mortem.</td>
          </tr>
          <tr className="hover:bg-white/[0.02]">
            <td className="px-4 py-3 font-medium">Strategist (CFO)</td>
            <td className="px-4 py-3 text-slate-300">Studies the whole scoreboard and writes a strategic review + recommendations each checkpoint.</td>
            <td className="px-4 py-3 text-xs text-slate-400">Standing + recommendations computed; LLM writes the analysis. Structural changes flagged for a human.</td>
          </tr>
        </Table>
        <p className="mt-3 pl-1 text-sm text-slate-400">
          <b className="text-slate-200">Track-record-weighted trust:</b> the CEO keeps a live Beta
          posterior per division and distrusts <i>stated</i> confidence in favour of{" "}
          <i>demonstrated</i> calibration — a division that says 70% but hits 50% gets discounted.
        </p>
      </Section>

      <Section
        title="Hard caps — percent of portfolio"
        desc={`Fractions of portfolio value, not fixed dollars, so they scale as you grow. Resolved here at ${cad(pv)}.`}
      >
        <Table head={["Cap", "Percent", `At ${cad(pv)}`, "Meaning"]}>
          {row("Total deployable", c.totalDeployable, "Max deployed out of the floor; the rest always rests.")}
          {row("Per-trade max", c.perTrade, "Largest single position.")}
          {row("Event hard cap", c.eventCap, "Lottery ceiling — the CEO can never override it.")}
          {row("Daily loss limit", c.dailyLoss, "Breach forces ALL capital to the floor.")}
          {row("Max drawdown", c.maxDrawdown, "Peak-to-trough; trips the circuit breaker.")}
          {row("Fee-drag limit", c.feeDrag, "Cumulative cost ceiling; breach de-risks.")}
        </Table>
        <p className="mt-3 pl-1 text-sm text-slate-400">
          At <b className="text-slate-200">{cad(pv)}</b> that’s deployable {cad(c.totalDeployable * pv)},
          per-trade {cad(c.perTrade * pv)}, Event {cad(c.eventCap * pv)}. At {cad(pv * 5)} every dollar
          ceiling is 5× larger automatically — same percentages. The caps are enforced in code,{" "}
          <b className="text-slate-200">outside any agent’s control</b>.
        </p>
      </Section>

      <Section
        title="Two asset classes, one checkpoint"
        desc="Each daily run scans crypto and stocks together, then the CEO ranks across them."
      >
        <Table head={["Asset class", "Venue", "Divisions"]}>
          <tr className="hover:bg-white/[0.02]">
            <td className="px-4 py-3 font-medium">Crypto</td>
            <td className="px-4 py-3 text-slate-300">Kraken</td>
            <td className="px-4 py-3"><Pill tone="good">Yield (floor)</Pill> <Pill tone="warn">Event</Pill></td>
          </tr>
          <tr className="hover:bg-white/[0.02]">
            <td className="px-4 py-3 font-medium">Stocks / ETFs</td>
            <td className="px-4 py-3 text-slate-300">Wealthsimple (via SnapTrade)</td>
            <td className="px-4 py-3"><Pill tone="cyan">Directional</Pill></td>
          </tr>
        </Table>
        <p className="mt-3 pl-1 text-sm text-slate-400">
          At every checkpoint, Directional pulls equity data, Event pulls crypto data, and Yield
          reports carry — all at once. The CEO then compares them on common terms (excess over the
          floor, per unit of risk, net of cost) and funds the single best, or holds. One run, both
          markets, ranked head-to-head.
        </p>
        <p className="mt-3 pl-1 text-sm text-slate-400">
          <b className="text-slate-200">Market hours.</b> Crypto trades 24/7, so the Event/Yield legs
          fill at any checkpoint time. Stocks only fill during the regular session (9:30am–4:00pm ET),
          so the daily run is scheduled for <b className="text-slate-200">3pm ET — 1 hour before the
          close</b>. As a backstop, a market-hours guard <b>auto-holds</b> any live equity order placed
          while the market is closed (logged as <code className="text-sky-300">equity_market_closed</code>)
          rather than queuing a blind after-hours order at an unknown gap price.
        </p>
      </Section>

      <Section title="The three loops" desc="Nested feedback at different speeds — this is the engine.">
        <div className="grid gap-3 md:grid-cols-3">
          {[
            ["① Decision loop — daily", "Each division pulls fresh real data → computes features + model outputs → pitches in the standard schema or abstains. Expected cost is a gate (a pitch that can't clear its round-trip cost is dropped). The risk manager adversarially challenges survivors. The CEO ranks what's left against the floor, weighted by demonstrated calibration, and emits exactly one of FUND / FUND_NONE / HOLD — then executes (live behind the flag) and logs the whole session."],
            ["② Performance loop — daily + weekly", "Snapshots net ROI vs the floor AND vs buy-and-hold, per-division attribution, risk-adjusted return, drawdown, and cumulative fee/FX drag. If drawdown, daily loss, or cost drag crosses a limit, it trips a circuit breaker and forces all capital back to the floor."],
            ["③ Learning loop — per resolved outcome + weekly", "The Critic scores every resolved decision: predicted vs realized, calibration, and a process-vs-luck tag (reward good process even when unlucky). Calibration updates the CEO's trust and each division's risk leash; the model re-fits within anti-overfit guardrails; persistently broken divisions are benched. New components run in shadow mode until they earn in."],
          ].map(([t, d]) => (
            <div key={t} className="glass hud p-4">
              <div className="text-sm font-semibold text-sky-300 glow-cyan">{t}</div>
              <p className="mt-2 text-xs leading-relaxed text-slate-300">{d}</p>
            </div>
          ))}
        </div>
        <p className="mt-3 pl-1 text-sm text-slate-400">
          The loops run at <b className="text-slate-200">different speeds on purpose</b>: review often
          (cheap), act rarely (consequential), and only learn from a decision once it has actually
          resolved and can be scored.
        </p>
      </Section>

      <Section
        title="Capital protection — the gains ratchet"
        desc="Compounding wants you to reinvest everything; survival wants you to protect gains."
      >
        <div className="glass hud p-5 text-sm leading-relaxed text-slate-300">
          When equity sets a new high-water mark, the ratchet sweeps <b className="text-slate-200">25% of
          the gain above it into an untouchable reserve</b>. The reserve only ever grows and is
          subtracted from the investable base the caps resolve against — so the agents{" "}
          <b className="text-slate-200">structurally cannot re-risk it</b>. Most of the compounding
          benefit, with ruin removed. The reserve shows in the dashboard hero (🔒).
        </div>
      </Section>

      <Section title="Adaptation — who tunes the strategy" desc="Two layers: automatic math, and a reflective CFO.">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="glass p-4">
            <div className="text-sm font-semibold text-sky-300">Automatic (deterministic)</div>
            <p className="mt-2 text-xs leading-relaxed text-slate-300">
              Calibration posteriors → CEO trust, per-division risk leashes, periodic model re-fits
              (within anti-overfit guardrails), and division retirement. Fast, safe, parameter-level —
              no agent rewriting itself.
            </p>
          </div>
          <div className="glass p-4">
            <div className="text-sm font-semibold text-sky-300">Reflective (the CFO)</div>
            <p className="mt-2 text-xs leading-relaxed text-slate-300">
              The Strategist agent reads performance + calibration + recurring errors and writes a
              plain-language strategic review with recommendations. Parameter tweaks are tagged{" "}
              <b className="text-slate-200">auto</b>; structural changes (new signals/divisions,
              mandate or cap changes) are tagged <b className="text-slate-200">needs you</b> — it
              recommends, you ratify.
            </p>
          </div>
        </div>
      </Section>

      <Section title="The cockpit (this dashboard)" desc="What you can watch, refreshing on its own every 45s.">
        <div className="glass p-5 text-sm text-slate-300">
          <ul className="list-disc space-y-1.5 pl-5">
            <li><b className="text-slate-200">Equity curve</b> — deposits + cumulative realized P&amp;L over time.</li>
            <li><b className="text-slate-200">Next-checkpoint countdown</b> — when the CEO next convenes (daily at CHECKPOINT_UTC).</li>
            <li><b className="text-slate-200">CEO verdict + rationale</b> and the full <b className="text-slate-200">boardroom session</b> — every pitch, the risk-manager veto, the CEO ruling, with reasons.</li>
            <li><b className="text-slate-200">Chief Strategist (CFO)</b> review + recommendations.</li>
            <li><b className="text-slate-200">Divisions table</b> — calibration, leash, shadow/retired — where trust accrues.</li>
            <li><b className="text-slate-200">Session history</b>, resolved outcomes, attribution, the reserve, and the audit log.</li>
          </ul>
        </div>
      </Section>

      <Section title="Safety rails" desc="In code, outside any agent.">
        <div className="glass p-5 text-sm text-slate-300">
          <ul className="list-disc space-y-1.5 pl-5">
            <li><code className="text-sky-300">LIVE_TRADING</code> defaults false; the CLI also requires <code className="text-sky-300">--confirm-live</code>.</li>
            <li>Venue credentials are <b>trade-only, withdrawals disabled</b> — the broker classes have no withdraw code path.</li>
            <li>Kraken and the equities venue are <b>isolated</b> accounts — a leak in one can’t touch the other.</li>
            <li>Stale / missing / insane data → the division <b>abstains</b>. No trade on garbage.</li>
            <li>A division can’t deploy real capital until a <b>backtest gate</b> shows edge net of cost.</li>
          </ul>
        </div>
      </Section>

      <footer className="mt-12 border-t border-white/10 pt-4 text-xs text-slate-500">
        Boardroom · the LLM reasons, code calculates · caps scale with the portfolio
      </footer>
    </main>
  );
}
