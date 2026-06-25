"""Boardroom command line.

    boardroom doctor              # check config & the safety rails
    boardroom decide [--synthetic] [--confirm-live]
    boardroom backtest [--synthetic]
    boardroom report ...          # print a weekly readout from stored outcomes

The CLI refuses to trade live unless BOTH the LIVE_TRADING env flag is true AND
``--confirm-live`` is passed — defense in depth around the one switch that spends
real money.
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console

from boardroom.config import get_settings

console = Console()


def _doctor() -> int:
    s = get_settings()
    console.rule("[bold]Boardroom doctor")
    console.print(f"LIVE_TRADING         : {'[red]ON[/red]' if s.live_trading else '[green]off (safe)[/green]'}")
    console.print(f"Anthropic key        : {'set' if s.anthropic_api_key else '[yellow]missing (LLM falls back to templates)[/yellow]'}")
    if s.anthropic_api_key:
        from boardroom.agents.llm import LLM

        ok, detail = LLM().ping()
        console.print(f"LLM live ping        : {'[green]' + detail + '[/green]' if ok else '[red]' + detail + '[/red]'}")
        if not ok:
            console.print("[dim]  → agents fall back to templates. Set BOARDROOM_LLM_MODEL to a model your key can access.[/dim]")
    console.print(f"Supabase configured  : {'yes' if s.supabase_configured() else '[yellow]no (in-memory repo)[/yellow]'}")
    console.print(f"Kraken creds         : {'set' if s.kraken_api_key else 'not set (Milestone 6)'}")
    console.print(f"IBKR account         : {s.ibkr_account_id or 'not set (Milestone 6)'}")
    pv = s.starting_portfolio_cad
    console.print(f"\n[bold]Hard caps — % of portfolio[/bold] [dim](resolved at {pv:.0f} CAD)[/dim]")
    console.print(f"  total deployable   : {s.total_deployable_pct:.0%}  = {s.total_deployable_pct * pv:.2f} CAD")
    console.print(f"  per-trade max      : {s.per_trade_max_pct:.0%}  = {s.per_trade_max_pct * pv:.2f} CAD")
    console.print(f"  event hard cap     : {s.event_hard_cap_pct:.0%}  = {s.event_hard_cap_pct * pv:.2f} CAD")
    console.print(f"  daily loss limit   : {s.daily_loss_limit_pct:.0%}  = {s.daily_loss_limit_pct * pv:.2f} CAD")
    console.print(f"  max drawdown       : {s.max_drawdown_pct:.0%}")
    console.print(f"  fee drag limit     : {s.fee_drag_limit_pct:.0%}")
    console.print("\n[dim]Caps scale with the portfolio (percent-based). Venue keys: trade-only, withdrawals DISABLED.[/dim]")
    return 0


def _decide(args: argparse.Namespace) -> int:
    from boardroom.factory import build_default_org

    s = get_settings()
    if args.confirm_live and not s.live_trading:
        console.print("[red]--confirm-live passed but LIVE_TRADING env flag is false. Aborting.[/red]")
        return 2
    live = bool(args.confirm_live and s.live_trading)

    org = build_default_org(data_mode="synthetic" if args.synthetic else "live")
    console.rule(f"[bold]Decision loop ({'LIVE' if live else 'dry-run'})")
    if live:
        org.repo.set_live_armed(True)  # durable: dashboard shows LIVE-armed across redeploys
    result = org.run_once()
    d = result.decision

    console.print(f"\n[bold]Pitches gathered:[/bold] {len(result.pitches)}")
    vetoed = [p for p in result.pitches if not result.challenges[p.pitch_id].approved]
    for p in vetoed:
        ch = result.challenges[p.pitch_id]
        console.print(
            f"  [red]VETOED[/red] {p.division.value:<12} {p.symbol:<8} "
            f"[dim]{'; '.join(ch.hard_objections)}[/dim]"
        )
    for r in result.ranked:
        flag = "" if not r.rejected_reason else f"  [dim]({r.rejected_reason})[/dim]"
        console.print(
            f"  {r.pitch.division.value:<12} {r.pitch.symbol:<8} "
            f"score={r.score:+.3f} trust={r.trust:.2f} size={r.trusted_size_cad:.2f}{flag}"
        )
    console.print(f"\n[bold]Hurdle (floor) rate:[/bold] {d.hurdle_rate:.5f}")
    color = {"fund": "green", "hold": "yellow", "fund_none": "yellow"}.get(d.kind.value, "white")
    head = f"[{color}]{d.kind.value.upper()}[/{color}]"
    if d.division:
        head += f"  {d.division.value}  {d.size_cad:.2f} CAD"
    console.print(f"\n[bold]CEO decision:[/bold] {head}")
    console.print(f"[italic]{d.rationale}[/italic]")
    return 0


def _backtest(args: argparse.Namespace) -> int:
    from boardroom.backtest import backtest_division
    from boardroom.models.directional import DirectionalModel
    from boardroom.schemas import Venue

    if args.synthetic:
        from boardroom.data.sources import synthetic_bars

        bars = synthetic_bars("SPY.US", Venue.IBKR, n=400, seed=3, drift=0.0006, vol=0.012)
    else:
        from boardroom.data.sources import fetch_stooq_daily

        bars = fetch_stooq_daily("spy.us")

    res = backtest_division(
        division="directional", venue=Venue.IBKR, model=DirectionalModel(), bars=bars, needs_fx=True
    )
    console.rule("[bold]Backtest gate — Directional")
    console.print(res.summary())
    console.print(
        "[green]Gate: PASS — may deploy capital.[/green]"
        if res.passes_gate
        else "[yellow]Gate: FAIL — division stays in shadow until it shows edge net of cost.[/yellow]"
    )
    return 0


def _run(args: argparse.Namespace) -> int:
    """Daily scheduler: convene the CEO once a day at CHECKPOINT_UTC, forever.

    Writes a 'scheduler_heartbeat' with the next run time so the dashboard can
    count down to it. Live execution still requires LIVE_TRADING=true AND
    --confirm-live; otherwise every run is dry-run.
    """
    import time as _time
    from datetime import datetime, timezone

    from boardroom.factory import build_default_org
    from boardroom.schedule import next_checkpoint

    s = get_settings()
    if args.confirm_live and not s.live_trading:
        console.print("[red]--confirm-live passed but LIVE_TRADING is false. Aborting.[/red]")
        return 2
    live = bool(args.confirm_live and s.live_trading)

    org = build_default_org(
        data_mode="synthetic" if args.synthetic else "live",
        prefer_live_brokers=not args.synthetic,
    )
    console.rule(f"[bold]Boardroom scheduler ({'LIVE' if live else 'dry-run'})")
    console.print(f"Daily checkpoint at [bold]{s.checkpoint_utc} UTC[/bold]. Ctrl+C to stop.\n")
    if live:
        org.repo.set_live_armed(True)  # durable: dashboard shows LIVE-armed across redeploys

    try:
        while True:
            nxt = next_checkpoint(datetime.now(timezone.utc), s.checkpoint_utc)
            org.repo.audit(
                "scheduler_heartbeat",
                {"next_run_at": nxt.isoformat(), "checkpoint_utc": s.checkpoint_utc, "live": live},
            )
            console.print(f"[dim]next checkpoint: {nxt:%Y-%m-%d %H:%M UTC}[/dim]")
            if not args.once:
                while datetime.now(timezone.utc) < nxt:
                    remaining = (nxt - datetime.now(timezone.utc)).total_seconds()
                    _time.sleep(max(1.0, min(60.0, remaining)))
            result = org.run_once()
            d = result.decision
            head = d.kind.value.upper() + (f" {d.division.value} {d.size_cad:.2f} CAD" if d.division else "")
            console.print(f"[bold]checkpoint {datetime.now(timezone.utc):%H:%M UTC}[/bold] → {head}")
            console.print(f"[italic dim]{d.rationale}[/italic dim]")
            # The CFO studies the scoreboard and writes a strategic review each run.
            try:
                from boardroom.agents.strategist import generate_and_save_review

                review = generate_and_save_review(org.repo, org.llm, s.starting_portfolio_cad)
                console.print(f"[bold cyan]CFO:[/bold cyan] {review.headline}")
            except Exception as e:  # never let the review break the loop
                console.print(f"[dim]CFO review skipped: {str(e)[:80]}[/dim]")
            if args.once:
                return 0
    except KeyboardInterrupt:
        console.print("\n[yellow]Scheduler stopped.[/yellow]")
        return 0


def _poll(args: argparse.Namespace) -> int:
    """Watch Supabase for dashboard 'Run now' requests and execute them locally.

    The web dashboard can only REQUEST a run (it inserts a pending row); the
    trading keys live here on the user's machine, so this poller is what turns a
    button click into a real checkpoint. Runs alongside the daily scheduler.
    """
    import time as _time
    from datetime import datetime, timezone

    from boardroom.factory import build_default_org

    s = get_settings()
    if args.confirm_live and not s.live_trading:
        console.print("[red]--confirm-live passed but LIVE_TRADING is false. Aborting.[/red]")
        return 2
    live = bool(args.confirm_live and s.live_trading)

    org = build_default_org(
        data_mode="synthetic" if args.synthetic else "live",
        prefer_live_brokers=not args.synthetic,
    )
    console.rule(f"[bold]Boardroom poller ({'LIVE' if live else 'dry-run'})")
    console.print(f"Watching for 'Run now' requests every {args.interval:.0f}s. Ctrl+C to stop.\n")
    if live:
        org.repo.set_live_armed(True)

    try:
        while True:
            req = org.repo.claim_next_run_request()
            if req is not None:
                rid = req.get("id")
                console.print(f"[bold]▶ run request #{rid}[/bold] ({req.get('source', '?')}) — convening")
                try:
                    result = org.run_once()
                    d = result.decision
                    head = d.kind.value.upper() + (
                        f" {d.division.value} {d.size_cad:.2f} CAD" if d.division else ""
                    )
                    summary = {
                        "kind": d.kind.value,
                        "division": d.division.value if d.division else None,
                        "size_cad": d.size_cad,
                        "live": d.live,
                        "rationale": d.rationale,
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
                    org.repo.complete_run_request(rid, "done", summary, d.decision_id)
                    console.print(f"[bold]✓ #{rid} done[/bold] → {head}")
                    try:
                        from boardroom.agents.strategist import generate_and_save_review

                        generate_and_save_review(org.repo, org.llm, s.starting_portfolio_cad)
                    except Exception:
                        pass
                except Exception as e:  # never let one bad run kill the poller
                    org.repo.complete_run_request(rid, "error", {"error": str(e)[:300]})
                    console.print(f"[red]✗ #{rid} error: {str(e)[:120]}[/red]")
                continue  # immediately check for more before sleeping
            if args.once:
                return 0
            _time.sleep(max(2.0, args.interval))
    except KeyboardInterrupt:
        console.print("\n[yellow]Poller stopped.[/yellow]")
        return 0


def _review(args: argparse.Namespace) -> int:
    """Generate the CFO/Strategist review now and save it."""
    from boardroom.agents.llm import LLM
    from boardroom.agents.strategist import generate_and_save_review
    from boardroom.persistence.repository import get_repository

    s = get_settings()
    review = generate_and_save_review(get_repository(), LLM(), s.starting_portfolio_cad)
    console.rule("[bold]CFO / Strategist review")
    console.print(f"[bold]{review.headline}[/bold]\n")
    console.print(review.narrative)
    if review.recommendations:
        console.print("\n[bold]Recommendations[/bold]")
        for r in review.recommendations:
            tag = "[yellow]needs you[/yellow]" if r.get("requires_human") else "[green]auto[/green]"
            console.print(f"  • ({tag}) {r['suggestion']}")
    return 0


def _preflight(args: argparse.Namespace) -> int:
    """Read-only go/no-go for live trading: venue connectivity + balances.

    Places NO orders and does not require LIVE_TRADING. The one command to run
    the moment credentials + network access are in place.
    """
    from boardroom.brokers import directional_execution_venue, make_brokers

    s = get_settings()
    console.rule("[bold]Boardroom preflight (read-only)")
    ok = True

    console.print(f"Anthropic key       : {'[green]set[/green]' if s.anthropic_api_key else '[yellow]missing[/yellow]'}")
    console.print(f"Supabase            : {'[green]configured[/green]' if s.supabase_configured() else '[yellow]in-memory only[/yellow]'}")
    console.print(f"Directional venue   : {directional_execution_venue(s).value}")
    console.print(f"LIVE_TRADING        : {'[red]ON[/red]' if s.live_trading else 'off (safe)'}\n")

    brokers = make_brokers(prefer_live=True)
    for venue, broker in brokers.items():
        broker.assert_no_withdrawal()
        if type(broker).__name__ == "StubBroker":
            # A stub means no real credentials for this venue -> not live-ready.
            console.print(f"  {venue.value:<10} [yellow]stub (no live creds)[/yellow]")
            ok = False
            continue
        try:
            healthy = broker.health_check()
        except Exception as e:  # noqa: BLE001
            console.print(f"  {venue.value:<10} [red]error[/red]: {str(e)[:80]}")
            ok = False
            continue
        if healthy:
            try:
                cash = broker.get_cash_cad()
            except Exception:  # noqa: BLE001
                cash = float("nan")
            console.print(f"  {venue.value:<10} [green]reachable[/green]  cash≈{cash:.2f} CAD")
        else:
            console.print(f"  {venue.value:<10} [yellow]not authenticated[/yellow]")
            ok = False

    verdict = "[green]GO[/green]" if ok else "[yellow]NOT READY[/yellow]"
    console.print(f"\nLive readiness: {verdict}")
    console.print("[dim]Run `boardroom decide --confirm-live` only after this shows GO and LIVE_TRADING=true.[/dim]")
    return 0 if ok else 1


def _report(args: argparse.Namespace) -> int:
    from boardroom.graph.performance_loop import run_performance_loop
    from boardroom.risk.caps import PortfolioState

    portfolio = PortfolioState(
        equity_cad=args.equity, peak_equity_cad=args.peak,
        realized_pnl_today_cad=0.0, cumulative_cost_cad=0.0, cumulative_gross_return_cad=0.0,
    )
    readout = run_performance_loop(
        carry_apr=args.carry, period_days=args.days, bnh_start=args.bnh_start,
        bnh_end=args.bnh_end, starting_equity_cad=args.equity, portfolio=portfolio,
    )
    console.print(readout.text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="boardroom", description="Autonomous capital allocator.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="check config and the safety rails")
    sub.add_parser("preflight", help="read-only venue connectivity + live go/no-go")
    sub.add_parser("review", help="generate the CFO/Strategist review now")

    p_run = sub.add_parser("run", help="daily scheduler — convene the CEO at CHECKPOINT_UTC, forever")
    p_run.add_argument("--synthetic", action="store_true", help="use offline synthetic data")
    p_run.add_argument("--confirm-live", action="store_true", help="execute live (requires LIVE_TRADING=true)")
    p_run.add_argument("--once", action="store_true", help="run one checkpoint now, then exit")

    p_decide = sub.add_parser("decide", help="run one daily decision loop")
    p_decide.add_argument("--synthetic", action="store_true", help="use offline synthetic data")
    p_decide.add_argument("--confirm-live", action="store_true", help="execute live (requires LIVE_TRADING=true)")

    p_poll = sub.add_parser("poll", help="watch for dashboard 'Run now' requests and execute them")
    p_poll.add_argument("--synthetic", action="store_true", help="use offline synthetic data")
    p_poll.add_argument("--confirm-live", action="store_true", help="execute live (requires LIVE_TRADING=true)")
    p_poll.add_argument("--interval", type=float, default=20.0, help="seconds between checks (default 20)")
    p_poll.add_argument("--once", action="store_true", help="check once and exit (no loop)")

    p_bt = sub.add_parser("backtest", help="run the backtest gate")
    p_bt.add_argument("--synthetic", action="store_true")

    p_rep = sub.add_parser("report", help="weekly performance readout from stored outcomes")
    p_rep.add_argument("--carry", type=float, default=0.04)
    p_rep.add_argument("--days", type=float, default=7.0)
    p_rep.add_argument("--equity", type=float, default=200.0)
    p_rep.add_argument("--peak", type=float, default=200.0)
    p_rep.add_argument("--bnh-start", type=float, default=100.0)
    p_rep.add_argument("--bnh-end", type=float, default=100.0)

    args = parser.parse_args(argv)
    if args.cmd == "doctor":
        return _doctor()
    if args.cmd == "preflight":
        return _preflight(args)
    if args.cmd == "run":
        return _run(args)
    if args.cmd == "review":
        return _review(args)
    if args.cmd == "decide":
        return _decide(args)
    if args.cmd == "poll":
        return _poll(args)
    if args.cmd == "backtest":
        return _backtest(args)
    if args.cmd == "report":
        return _report(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
