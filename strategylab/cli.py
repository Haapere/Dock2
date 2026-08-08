"""Kommandozeilen-Oberfläche für StrategyLab.

Beispiele:
    strategylab data generate --out data/demo.csv
    strategylab data fetch --symbol aapl.us --out data/aapl.csv
    strategylab list
    strategylab backtest --data data/demo.csv --strategy sma_cross --params fast=20,slow=50 --report report.html
    strategylab optimize --data data/demo.csv --strategy sma_cross --grid fast=10|20|30 slow=50|100|150
    strategylab walkforward --data data/demo.csv --strategy sma_cross --grid fast=10|20|30 slow=50|100
    strategylab screen --data data/aapl.csv data/sap.csv
    strategylab check --data data/aapl.csv --strategy sma_cross --grid fast=10|20|30 slow=50|100|150 --save checks/aapl.json
    strategylab portfolio --data data/aapl.csv data/sap.csv --strategy sma_cross --params fast=20,slow=100
    strategylab bot init --config bot.json
    strategylab bot signals --config bot.json --holdings holdings.json
    strategylab paper init --account paper.json --strategy sma_cross --params fast=20,slow=50
    strategylab paper update --account paper.json --data data/demo.csv
    strategylab paper status --account paper.json
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
from pathlib import Path

from strategylab import bot as bot_mod
from strategylab import data as data_mod
from strategylab import paper as paper_mod
from strategylab import reality as reality_mod
from strategylab import screener as screener_mod
from strategylab.backtest import Backtester
from strategylab.portfolio import PortfolioConfig, run_portfolio
from strategylab.report import save_report
from strategylab.risk import RiskConfig
from strategylab.strategy import get_strategy, list_strategies, parse_params
from strategylab.walkforward import optimize, parse_grid, walk_forward


def _add_risk_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--risk", action="store_true",
        help="Risikomanagement aktivieren (Vol-Ziel, ATR-Stop, Notabschaltung)",
    )
    parser.add_argument("--target-vol", type=float, default=0.15, help="Zielvolatilität p.a. (Default: 0.15)")
    parser.add_argument("--stop-atr", type=float, default=3.0, help="Stop-Abstand in ATR (Default: 3.0)")
    parser.add_argument("--max-dd-stop", type=float, default=0.20, help="Notabschaltung ab Drawdown (Default: 0.20)")


def _risk_config(args: argparse.Namespace) -> RiskConfig | None:
    if not getattr(args, "risk", False):
        return None
    return RiskConfig(
        target_vol=args.target_vol,
        stop_atr_multiple=args.stop_atr,
        max_drawdown_stop=args.max_dd_stop,
    )


def _parse_data_specs(specs: list[str]) -> dict[str, str]:
    """Parst Datenangaben 'symbol=pfad' oder bloße Pfade (Symbol aus Dateiname)."""
    out: dict[str, str] = {}
    for spec in specs:
        if "=" in spec:
            symbol, path = spec.split("=", 1)
            out[symbol.strip()] = path.strip()
        else:
            out[Path(spec).stem] = spec
    return out


def _load_multi(specs: list[str]) -> dict:
    return {sym: data_mod.load_csv(path) for sym, path in _parse_data_specs(specs).items()}


def _add_cost_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--capital", type=float, default=10_000.0, help="Startkapital (Default: 10000)")
    parser.add_argument("--commission", type=float, default=0.001, help="Gebühr je Umschichtung, z.B. 0.001 = 0.1%%")
    parser.add_argument("--slippage", type=float, default=0.0005, help="Slippage je Umschichtung (Default: 0.0005)")


def _backtester(args: argparse.Namespace) -> Backtester:
    return Backtester(initial_capital=args.capital, commission=args.commission, slippage=args.slippage)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="strategylab",
        description="Trading-Strategien entwickeln, backtesten und forward-testen",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # data
    p_data = sub.add_parser("data", help="Kursdaten beschaffen")
    data_sub = p_data.add_subparsers(dest="data_command", required=True)

    p_gen = data_sub.add_parser("generate", help="Synthetische Demo-Daten erzeugen")
    p_gen.add_argument("--out", required=True, help="Ziel-CSV")
    p_gen.add_argument("--days", type=int, default=1500)
    p_gen.add_argument("--seed", type=int, default=42)
    p_gen.add_argument("--start", default="2020-01-01")

    p_fetch = data_sub.add_parser("fetch", help="Tagesdaten von stooq.com laden")
    p_fetch.add_argument("--symbol", required=True, help="z.B. aapl.us, sap.de, ^spx")
    p_fetch.add_argument("--out", required=True, help="Ziel-CSV")

    # gui
    p_gui = sub.add_parser("gui", help="Grafische Web-Oberfläche im Browser öffnen")
    p_gui.add_argument("--port", type=int, default=8765, help="Port (Default: 8765)")
    p_gui.add_argument("--no-browser", action="store_true", help="Browser nicht automatisch öffnen")
    p_gui.add_argument(
        "--lan", action="store_true",
        help="Handy-Modus: auch für Geräte im selben WLAN erreichbar (Adresse wird angezeigt)",
    )
    p_gui.add_argument("--host", help="Bind-Adresse manuell setzen (überschreibt --lan)")

    # list
    sub.add_parser("list", help="Verfügbare Strategien anzeigen")

    # backtest
    p_bt = sub.add_parser("backtest", help="Strategie auf historischen Daten testen")
    p_bt.add_argument("--data", required=True, help="OHLCV-CSV-Datei")
    p_bt.add_argument("--strategy", required=True)
    p_bt.add_argument("--params", help="z.B. fast=20,slow=50")
    p_bt.add_argument("--report", help="Pfad für HTML-Report (optional)")
    _add_cost_args(p_bt)

    # optimize
    p_opt = sub.add_parser("optimize", help="Parameter-Rastersuche (in-sample!)")
    p_opt.add_argument("--data", required=True)
    p_opt.add_argument("--strategy", required=True)
    p_opt.add_argument("--grid", nargs="+", required=True, help="z.B. fast=10|20|30 slow=50|100")
    p_opt.add_argument("--metric", default="sharpe", choices=["sharpe", "cagr", "max_drawdown"])
    p_opt.add_argument("--top", type=int, default=10)
    _add_cost_args(p_opt)

    # walkforward
    p_wf = sub.add_parser("walkforward", help="Out-of-Sample-Validierung (Zukunftstauglichkeit)")
    p_wf.add_argument("--data", required=True)
    p_wf.add_argument("--strategy", required=True)
    p_wf.add_argument("--grid", nargs="+", required=True)
    p_wf.add_argument("--train", type=int, default=500, help="Trainingsfenster in Tagen")
    p_wf.add_argument("--test", type=int, default=125, help="Testfenster in Tagen")
    p_wf.add_argument("--metric", default="sharpe", choices=["sharpe", "cagr", "max_drawdown"])
    _add_cost_args(p_wf)

    # screen
    p_screen = sub.add_parser(
        "screen", help="Werte nach Handelbarkeit prüfen (Auswahlkriterien)"
    )
    p_screen.add_argument(
        "--data", nargs="+", required=True,
        help="Kursdateien, z.B. 'aapl=data/aapl.csv data/sap.csv'",
    )
    p_screen.add_argument("--until", help="Nur Daten bis zu diesem Datum nutzen (gegen Selection Bias)")
    p_screen.add_argument("--min-years", type=float, default=5.0)
    p_screen.add_argument("--min-turnover", type=float, default=5_000_000.0)
    p_screen.add_argument("--round-trip-cost", type=float, default=0.003,
                          help="Kosten eines vollen Rundlaufs (Default: 0.003 = 0.3%%)")
    p_screen.add_argument("--max-cost-hurdle", type=float, default=0.35)

    # check
    p_check = sub.add_parser(
        "check", help="Realitätsprüfung: ist der Vorteil echt oder Zufall?"
    )
    p_check.add_argument("--data", required=True)
    p_check.add_argument("--strategy", required=True)
    p_check.add_argument("--params", help="Feste Parameter, z.B. fast=20,slow=50")
    p_check.add_argument("--grid", nargs="+",
                         help="Parameterraster für die Walk-Forward-Analyse, z.B. fast=10|20 slow=50|100")
    p_check.add_argument("--train", type=int, default=500)
    p_check.add_argument("--test", type=int, default=125)
    p_check.add_argument("--permutations", type=int, default=500,
                         help="Durchläufe des Permutationstests (Default: 500)")
    p_check.add_argument("--trials", type=int,
                         help="Gesamtzahl aller je probierten Varianten (für die Deflated Sharpe Ratio). "
                              "Ehrlich ist die Zahl über das ganze Projekt, nicht nur dieses Raster.")
    p_check.add_argument("--save", help="Prüfprotokoll als JSON speichern (Freigabe für den Bot)")
    _add_cost_args(p_check)
    _add_risk_args(p_check)

    # portfolio
    p_pf = sub.add_parser("portfolio", help="Backtest über mehrere Werte (Diversifikation)")
    p_pf.add_argument("--data", nargs="+", required=True)
    p_pf.add_argument("--strategy", required=True)
    p_pf.add_argument("--params", help="z.B. fast=20,slow=100")
    p_pf.add_argument("--max-weight", type=float, default=0.25)
    p_pf.add_argument("--weighting", default="inverse_vol", choices=["inverse_vol", "equal"])
    _add_cost_args(p_pf)
    _add_risk_args(p_pf)

    # bot
    p_bot = sub.add_parser("bot", help="Bot: tägliche Zielpositionen und Orders")
    bot_sub = p_bot.add_subparsers(dest="bot_command", required=True)

    p_binit = bot_sub.add_parser("init", help="Beispielkonfiguration anlegen")
    p_binit.add_argument("--config", required=True, help="Zieldatei, z.B. bot.json")
    p_binit.add_argument("--name", default="mein_bot")

    p_bsig = bot_sub.add_parser("signals", help="Zielpositionen und Orders für heute berechnen")
    p_bsig.add_argument("--config", required=True)
    p_bsig.add_argument("--holdings", help="JSON mit Ist-Beständen {symbol: stueck}")
    p_bsig.add_argument("--orders-csv", help="Orders zusätzlich als CSV exportieren")
    p_bsig.add_argument(
        "--dry-run", action="store_true",
        help="Sicherheitssperre übergehen — nur für Trockenläufe ohne echtes Geld",
    )

    p_bhold = bot_sub.add_parser("holdings", help="Ist-Bestände auf die Zielpositionen setzen")
    p_bhold.add_argument("--config", required=True)
    p_bhold.add_argument("--holdings", required=True)

    # paper
    p_paper = sub.add_parser("paper", help="Papertrading / Forward-Test")
    paper_sub = p_paper.add_subparsers(dest="paper_command", required=True)

    p_init = paper_sub.add_parser("init", help="Neuen Forward-Test starten")
    p_init.add_argument("--account", required=True, help="Pfad der JSON-Zustandsdatei")
    p_init.add_argument("--strategy", required=True)
    p_init.add_argument("--params", help="z.B. fast=20,slow=50")
    p_init.add_argument("--start", help="Startdatum (ISO), Default: heute")
    _add_cost_args(p_init)

    p_upd = paper_sub.add_parser("update", help="Mit aktuellen Kursdaten fortschreiben")
    p_upd.add_argument("--account", required=True)
    p_upd.add_argument("--data", required=True, help="Aktualisierte OHLCV-CSV")

    p_st = paper_sub.add_parser("status", help="Aktuellen Stand anzeigen")
    p_st.add_argument("--account", required=True)

    return parser


def cmd_data(args: argparse.Namespace) -> int:
    if args.data_command == "generate":
        df = data_mod.generate_synthetic(days=args.days, seed=args.seed, start=args.start)
        data_mod.save_csv(df, args.out)
        print(f"{len(df)} Tage synthetische Daten nach {args.out} geschrieben "
              f"({df.index[0].date()} bis {df.index[-1].date()})")
    else:
        df = data_mod.fetch_stooq(args.symbol)
        data_mod.save_csv(df, args.out)
        print(f"{len(df)} Tage für {args.symbol} nach {args.out} geschrieben "
              f"({df.index[0].date()} bis {df.index[-1].date()})")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    from strategylab import webapp

    host = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")
    webapp.serve(host=host, port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    print(f"{'Name':<22} {'Default-Parameter'}")
    print("-" * 60)
    for name, cls in list_strategies():
        params = ", ".join(f"{k}={v}" for k, v in cls.params.items()) or "-"
        print(f"{name:<22} {params}")
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    df = data_mod.load_csv(args.data)
    strategy = get_strategy(args.strategy, **parse_params(args.params))
    result = _backtester(args).run(strategy, df)
    print(result.summary_text())
    if args.report:
        path = save_report(result, args.report)
        print(f"\nHTML-Report: {path}")
    return 0


def cmd_optimize(args: argparse.Namespace) -> int:
    df = data_mod.load_csv(args.data)
    grid = parse_grid(args.grid)
    result = optimize(args.strategy, df, grid, backtester=_backtester(args), metric=args.metric)
    print(result.summary_text(top=args.top))
    print("\nHinweis: In-Sample-Ergebnis. Zur Validierung 'walkforward' verwenden.")
    return 0


def cmd_walkforward(args: argparse.Namespace) -> int:
    df = data_mod.load_csv(args.data)
    grid = parse_grid(args.grid)
    result = walk_forward(
        args.strategy, df, grid,
        train_size=args.train, test_size=args.test,
        backtester=_backtester(args), metric=args.metric,
    )
    print(result.summary_text())
    return 0


def cmd_screen(args: argparse.Namespace) -> int:
    data = _load_multi(args.data)
    criteria = screener_mod.ScreenCriteria(
        min_years=args.min_years,
        min_median_turnover=args.min_turnover,
        round_trip_cost=args.round_trip_cost,
        max_cost_hurdle=args.max_cost_hurdle,
    )
    table, profiles = screener_mod.screen_universe(data, criteria, until=args.until)
    print(screener_mod.summary_text(table, profiles))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    df = data_mod.load_csv(args.data)
    grid = parse_grid(args.grid) if args.grid else None
    backtester = Backtester(
        initial_capital=args.capital, commission=args.commission,
        slippage=args.slippage, risk=_risk_config(args),
    )
    if not grid:
        print(
            "Hinweis: Ohne --grid gibt es keine Out-of-Sample-Schätzung. Das Urteil\n"
            "kann dann nie GO lauten — für eine echte Prüfung ein Parameterraster\n"
            "angeben, z.B. --grid fast=10|20|30 slow=50|100|150\n",
            file=sys.stderr,
        )
    check = reality_mod.full_check(
        args.strategy, df,
        params=parse_params(args.params) or None,
        grid=grid, backtester=backtester,
        train_size=args.train, test_size=args.test,
        n_permutations=args.permutations, n_trials=args.trials,
    )
    print(check.summary_text())
    if args.save:
        check.save(args.save)
        print(f"\nPrüfprotokoll gespeichert: {args.save}")
        if check.verdict == "NO-GO":
            print("Der Bot verweigert mit diesem Protokoll die Ausgabe von Orders.")
    return 0 if check.verdict != "NO-GO" else 2


def cmd_portfolio(args: argparse.Namespace) -> int:
    data = _load_multi(args.data)
    if len(data) < 2:
        raise ValueError("Ein Portfolio braucht mindestens zwei Werte")
    result = run_portfolio(
        data, args.strategy, params=parse_params(args.params),
        config=PortfolioConfig(max_weight=args.max_weight, weighting=args.weighting),
        backtester=Backtester(
            initial_capital=args.capital, commission=args.commission, slippage=args.slippage
        ),
        risk=_risk_config(args),
    )
    print(result.summary_text())
    return 0


def cmd_bot(args: argparse.Namespace) -> int:
    if args.bot_command == "init":
        config = bot_mod.template_config(args.name)
        config.save(args.config)
        print(
            f"Beispielkonfiguration nach {args.config} geschrieben.\n\n"
            "Nächste Schritte:\n"
            "  1. 'universe' auf die eigenen Kursdateien anpassen\n"
            "  2. 'strategylab screen' — sind die Werte überhaupt handelbar?\n"
            "  3. 'strategylab check --save <check_file>' — hält die Strategie der Prüfung stand?\n"
            "  4. 'strategylab bot signals' — erst danach gibt der Bot Orders aus"
        )
        return 0

    config = bot_mod.BotConfig.load(args.config)

    if args.bot_command == "holdings":
        targets = bot_mod.compute_targets(config)
        holdings = {r.symbol: r.zielstueck for r in targets.itertuples()}
        bot_mod.save_holdings(args.holdings, holdings)
        print(f"Ist-Bestände in {args.holdings} auf die Zielpositionen gesetzt:")
        print(targets.to_string(index=False))
        return 0

    targets, orders, approval = bot_mod.run_bot(
        config, args.holdings, require_approval=not args.dry_run
    )
    if args.dry_run and not approval.allowed:
        print(f"TROCKENLAUF — Sperre übergangen ({approval.verdict}): {approval.reason}\n",
              file=sys.stderr)
    print(bot_mod.orders_text(config, targets, orders, approval))
    if args.orders_csv:
        Path(args.orders_csv).parent.mkdir(parents=True, exist_ok=True)
        orders.to_csv(args.orders_csv, index=False)
        print(f"\nOrders exportiert: {args.orders_csv}")
    return 0


def cmd_paper(args: argparse.Namespace) -> int:
    if args.paper_command == "init":
        account = paper_mod.init_account(
            args.account,
            strategy_name=args.strategy,
            params=parse_params(args.params),
            start_date=args.start,
            initial_capital=args.capital,
            commission=args.commission,
            slippage=args.slippage,
        )
        print(f"Forward-Test angelegt: {args.account}")
        print(paper_mod.status_text(account))
    elif args.paper_command == "update":
        df = data_mod.load_csv(args.data)
        account = paper_mod.update_account(args.account, df)
        print(paper_mod.status_text(account))
    else:
        account = paper_mod.PaperAccount.load(args.account)
        print(paper_mod.status_text(account))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "data": cmd_data,
        "gui": cmd_gui,
        "list": cmd_list,
        "backtest": cmd_backtest,
        "optimize": cmd_optimize,
        "walkforward": cmd_walkforward,
        "screen": cmd_screen,
        "check": cmd_check,
        "portfolio": cmd_portfolio,
        "bot": cmd_bot,
        "paper": cmd_paper,
    }
    try:
        return handlers[args.command](args)
    except PermissionError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 3
    except urllib.error.URLError as exc:
        print(
            f"Netzwerkfehler beim Datenabruf: {exc}\n"
            "Alternativ 'strategylab data generate' für synthetische Daten nutzen "
            "oder eine eigene OHLCV-CSV-Datei bereitstellen.",
            file=sys.stderr,
        )
        return 1
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
