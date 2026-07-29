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
