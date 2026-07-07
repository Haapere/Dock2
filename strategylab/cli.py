"""Kommandozeilen-Oberfläche für StrategyLab.

Beispiele:
    strategylab data generate --out data/demo.csv
    strategylab data fetch --symbol aapl.us --out data/aapl.csv
    strategylab list
    strategylab backtest --data data/demo.csv --strategy sma_cross --params fast=20,slow=50 --report report.html
    strategylab optimize --data data/demo.csv --strategy sma_cross --grid fast=10|20|30 slow=50|100|150
    strategylab walkforward --data data/demo.csv --strategy sma_cross --grid fast=10|20|30 slow=50|100
    strategylab paper init --account paper.json --strategy sma_cross --params fast=20,slow=50
    strategylab paper update --account paper.json --data data/demo.csv
    strategylab paper status --account paper.json
"""

from __future__ import annotations

import argparse
import sys
import urllib.error

from strategylab import data as data_mod
from strategylab import paper as paper_mod
from strategylab.backtest import Backtester
from strategylab.report import save_report
from strategylab.strategy import get_strategy, list_strategies, parse_params
from strategylab.walkforward import optimize, parse_grid, walk_forward


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
        "list": cmd_list,
        "backtest": cmd_backtest,
        "optimize": cmd_optimize,
        "walkforward": cmd_walkforward,
        "paper": cmd_paper,
    }
    try:
        return handlers[args.command](args)
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
