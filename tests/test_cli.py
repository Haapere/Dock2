import json

import pytest

from strategylab.cli import main
from strategylab.data import generate_synthetic, save_csv


@pytest.fixture
def data_csv(tmp_path):
    path = tmp_path / "data.csv"
    save_csv(generate_synthetic(days=700, seed=4), path)
    return str(path)


def test_list(capsys):
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "sma_cross" in out
    assert "buy_hold" in out


def test_data_generate(tmp_path, capsys):
    out_path = tmp_path / "gen.csv"
    assert main(["data", "generate", "--out", str(out_path), "--days", "300"]) == 0
    assert out_path.exists()
    assert "300 Tage" in capsys.readouterr().out


def test_backtest_with_report(data_csv, tmp_path, capsys):
    report = tmp_path / "report.html"
    code = main([
        "backtest", "--data", data_csv,
        "--strategy", "sma_cross", "--params", "fast=10,slow=50",
        "--report", str(report),
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "Sharpe" in out
    html = report.read_text()
    assert "<svg" in html and "Equity-Kurve" in html


def test_backtest_unknown_strategy_fails(data_csv, capsys):
    assert main(["backtest", "--data", data_csv, "--strategy", "nope"]) == 1
    assert "Fehler" in capsys.readouterr().err


def test_optimize(data_csv, capsys):
    code = main([
        "optimize", "--data", data_csv, "--strategy", "sma_cross",
        "--grid", "fast=5|10", "slow=30|60",
    ])
    assert code == 0
    assert "Beste Parameter" in capsys.readouterr().out


def test_walkforward(data_csv, capsys):
    code = main([
        "walkforward", "--data", data_csv, "--strategy", "sma_cross",
        "--grid", "fast=5|10", "slow=30|60",
        "--train", "300", "--test", "100",
    ])
    assert code == 0
    assert "Out-of-Sample" in capsys.readouterr().out


def test_paper_lifecycle(data_csv, tmp_path, capsys):
    account = tmp_path / "paper.json"
    assert main([
        "paper", "init", "--account", str(account),
        "--strategy", "sma_cross", "--params", "fast=10,slow=50",
        "--start", "2022-01-03",
    ]) == 0
    assert account.exists()

    assert main(["paper", "update", "--account", str(account), "--data", data_csv]) == 0
    state = json.loads(account.read_text())
    assert len(state["history"]) > 0

    assert main(["paper", "status", "--account", str(account)]) == 0
    assert "Aktuelle Position" in capsys.readouterr().out


# ------------------------------------------------- Werteauswahl und Prüfung

@pytest.fixture
def multi_csv(tmp_path):
    paths = []
    for i, symbol in enumerate(["aaa", "bbb", "ccc", "ddd"]):
        path = tmp_path / f"{symbol}.csv"
        save_csv(generate_synthetic(days=1300, seed=500 + i), path)
        paths.append(str(path))
    return paths


def test_screen(multi_csv, capsys):
    assert main(["screen", "--data", *multi_csv]) == 0
    out = capsys.readouterr().out
    assert "Werteauswahl" in out
    assert "kostenhuerde" in out


def test_screen_accepts_symbol_equals_path(multi_csv, capsys):
    assert main(["screen", "--data", f"meinwert={multi_csv[0]}"]) == 0
    assert "meinwert" in capsys.readouterr().out


def test_screen_until_limits_the_data(multi_csv, capsys):
    assert main(["screen", "--data", multi_csv[0], "--until", "2021-01-01"]) == 0
    assert "Werteauswahl" in capsys.readouterr().out


def test_check_without_grid_warns_and_cannot_pass(data_csv, capsys):
    code = main(["check", "--data", data_csv, "--strategy", "sma_cross",
                 "--params", "fast=20,slow=60", "--permutations", "50"])
    captured = capsys.readouterr()
    assert "keine Out-of-Sample-Schätzung" in captured.err
    assert "URTEIL: NO-GO" in captured.out
    assert code == 2


def test_check_saves_a_verdict(data_csv, tmp_path, capsys):
    check_file = tmp_path / "checks" / "c.json"
    main(["check", "--data", data_csv, "--strategy", "sma_cross",
          "--grid", "fast=10|20", "slow=60|100",
          "--train", "400", "--test", "150", "--permutations", "50",
          "--save", str(check_file)])
    record = json.loads(check_file.read_text())
    assert record["strategy"] == "sma_cross"
    assert record["verdict"] in ("GO", "VORSICHT", "NO-GO")
    assert "Prüfprotokoll gespeichert" in capsys.readouterr().out


def test_portfolio(multi_csv, capsys):
    assert main(["portfolio", "--data", *multi_csv, "--strategy", "sma_cross",
                 "--params", "fast=20,slow=80"]) == 0
    out = capsys.readouterr().out
    assert "Portfolio-Backtest" in out
    assert "Diversifikationseffekt" in out


def test_portfolio_needs_two_assets(multi_csv, capsys):
    assert main(["portfolio", "--data", multi_csv[0], "--strategy", "sma_cross"]) == 1
    assert "mindestens zwei Werte" in capsys.readouterr().err


def test_portfolio_with_risk_management(multi_csv, capsys):
    assert main(["portfolio", "--data", *multi_csv, "--strategy", "sma_cross",
                 "--params", "fast=20,slow=80", "--risk", "--target-vol", "0.10"]) == 0
    assert "Portfolio-Backtest" in capsys.readouterr().out


# ---------------------------------------------------------------------- Bot

def test_bot_init_explains_the_next_steps(tmp_path, capsys):
    config = tmp_path / "bot.json"
    assert main(["bot", "init", "--config", str(config)]) == 0
    out = capsys.readouterr().out
    assert config.exists()
    assert "screen" in out and "check" in out


def test_bot_signals_is_blocked_without_approval(multi_csv, tmp_path, capsys):
    config = tmp_path / "bot.json"
    main(["bot", "init", "--config", str(config)])
    cfg = json.loads(config.read_text())
    cfg["universe"] = {f"w{i}": p for i, p in enumerate(multi_csv)}
    cfg["check_file"] = str(tmp_path / "checks" / "c.json")
    config.write_text(json.dumps(cfg))

    assert main(["bot", "signals", "--config", str(config)]) == 3
    assert "gesperrt" in capsys.readouterr().err


def test_bot_signals_exports_orders_after_approval(multi_csv, tmp_path, capsys):
    config = tmp_path / "bot.json"
    check_file = tmp_path / "checks" / "c.json"
    check_file.parent.mkdir(parents=True, exist_ok=True)
    check_file.write_text(json.dumps(
        {"strategy": "sma_cross", "params": {}, "verdict": "GO", "criteria": []}
    ))
    main(["bot", "init", "--config", str(config)])
    cfg = json.loads(config.read_text())
    cfg["universe"] = {f"w{i}": p for i, p in enumerate(multi_csv)}
    cfg["check_file"] = str(check_file)
    config.write_text(json.dumps(cfg))

    orders_csv = tmp_path / "orders.csv"
    assert main(["bot", "signals", "--config", str(config),
                 "--orders-csv", str(orders_csv)]) == 0
    out = capsys.readouterr().out
    assert "Zielpositionen" in out
    assert "platziert nichts selbst" in out
    assert orders_csv.exists()


def test_bot_dry_run_bypasses_the_gate(multi_csv, tmp_path, capsys):
    config = tmp_path / "bot.json"
    main(["bot", "init", "--config", str(config)])
    cfg = json.loads(config.read_text())
    cfg["universe"] = {f"w{i}": p for i, p in enumerate(multi_csv)}
    cfg["check_file"] = str(tmp_path / "fehlt.json")
    config.write_text(json.dumps(cfg))

    assert main(["bot", "signals", "--config", str(config), "--dry-run"]) == 0
    captured = capsys.readouterr()
    assert "TROCKENLAUF" in captured.err
    assert "Zielpositionen" in captured.out


def test_bot_holdings_records_the_target_positions(multi_csv, tmp_path, capsys):
    config = tmp_path / "bot.json"
    main(["bot", "init", "--config", str(config)])
    cfg = json.loads(config.read_text())
    cfg["universe"] = {f"w{i}": p for i, p in enumerate(multi_csv)}
    config.write_text(json.dumps(cfg))

    holdings = tmp_path / "holdings.json"
    assert main(["bot", "holdings", "--config", str(config),
                 "--holdings", str(holdings)]) == 0
    assert "holdings" in json.loads(holdings.read_text())
