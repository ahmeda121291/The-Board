"""The portfolio advisor — writes the plain-English discrepancy note.

Given the COMPUTED diff between the user's actual IBKR holdings and the
recommended portfolio, it writes a short, human summary: what to buy, what to
sell, and why — the "buy Costco / sell SanDisk" line the dashboard shows.

Same invariant as every other agent: it only writes prose. Every dollar figure
and every buy/sell instruction is computed in ``boardroom.recommend``; the LLM
narrates, it never decides.
"""

from __future__ import annotations

from boardroom.agents.llm import LLM
from boardroom.recommend import CurrentHolding, PortfolioAction, RecommendedHolding

_SYSTEM = (
    "You are a plain-spoken portfolio advisor for ONE retail investor with a "
    "small account. You are given a COMPUTED list of buy/sell/trim/hold actions "
    "that reconcile their current stock holdings to a recommended portfolio. "
    "Write 2-4 short sentences in plain English telling them what to do and why, "
    "naming the tickers (e.g. 'Buy Costco, sell SanDisk'). No jargon, no new "
    "numbers beyond what you're given, no hedging boilerplate. These are stock "
    "recommendations they execute by hand — never financial advice disclaimers."
)


def _humanize(action: str) -> str:
    return {
        "buy": "Buy", "add": "Add to", "trim": "Trim", "sell": "Sell", "hold": "Hold",
    }.get(action, action.title())


def fallback_narrative(
    actions: list[PortfolioAction],
    recommended: list[RecommendedHolding],
    current: list[CurrentHolding],
) -> str:
    """Deterministic summary used when the LLM is unavailable."""
    if not recommended and not current:
        return "No stock recommendations right now — nothing in the scanned universe beat the cash floor after costs. Holding stock cash is fine."
    moves = [a for a in actions if a.action in ("buy", "sell", "add", "trim")]
    if not moves:
        return "Your stock holdings already match the recommended portfolio. No changes needed."
    parts: list[str] = []
    for a in moves[:6]:
        verb = _humanize(a.action)
        if a.action == "sell":
            parts.append(f"{verb} {a.symbol} (~{abs(a.delta_cad):.0f} CAD)")
        else:
            parts.append(f"{verb} {a.symbol} (~{abs(a.delta_cad):.0f} CAD)")
    lead = "Suggested changes to your IBKR stock book: " + "; ".join(parts) + "."
    extra = ""
    if len(moves) > 6:
        extra = f" Plus {len(moves) - 6} smaller adjustment(s)."
    return lead + extra + " These are recommendations — you place the orders in IBKR."


def write_discrepancy_note(
    actions: list[PortfolioAction],
    recommended: list[RecommendedHolding],
    current: list[CurrentHolding],
    llm: LLM | None = None,
) -> str:
    """Plain-English summary of the current-vs-recommended diff."""
    llm = llm or LLM()
    rec_lines = "\n".join(
        f"  {h.symbol}: target {h.target_cad:.0f} CAD ({h.target_weight:.0%})" for h in recommended
    ) or "  (none)"
    cur_lines = "\n".join(
        f"  {c.symbol}: holding {c.market_value_cad:.0f} CAD" for c in current
    ) or "  (none held)"
    act_lines = "\n".join(
        f"  {a.action.upper()} {a.symbol}: {a.current_cad:.0f} -> {a.target_cad:.0f} CAD ({a.reason})"
        for a in actions
    ) or "  (no actions)"
    user = (
        f"RECOMMENDED PORTFOLIO:\n{rec_lines}\n\n"
        f"CURRENTLY HELD (IBKR):\n{cur_lines}\n\n"
        f"COMPUTED ACTIONS:\n{act_lines}\n\n"
        "Write the 2-4 sentence summary."
    )
    text = llm.complete(system=_SYSTEM, user=user, max_tokens=300)
    return text.strip() if text else fallback_narrative(actions, recommended, current)
