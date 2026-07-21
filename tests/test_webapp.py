"""Tests der Web-API-Handler (ohne echten Netzwerk-Server)."""

import io

import pytest

from strategylab import webapp


@pytest.fixture(autouse=True)
def reset_state():
    webapp._STATE["df"] = None
    webapp._STATE["source"] = None
    yield
    webapp._STATE["df"] = None
    webapp._STATE["source"] = None


def test_index_html_is_packaged():
    html = webapp._load_index_html()
    assert "<canvas" in html and "StrategyLab" in html


def test_strategies_endpoint_lists_params():
    data = webapp.api_strategies()
    names = [s["name"] for s in data["strategies"]]
    assert "sma_cross" in names
    sma = next(s for s in data["strategies"] if s["name"] == "sma_cross")
    pnames = {p["name"]: p["type"] for p in sma["params"]}
    assert pnames["fast"] == "int"
    assert pnames["allow_short"] == "bool"


def test_generate_then_dataset_info():
    info = webapp.api_generate({"days": 400, "seed": 1})
    assert info["loaded"] is True
    assert info["rows"] == 400
    assert len(info["preview"]["close"]) == len(info["preview"]["dates"])
    assert webapp.api_dataset()["rows"] == 400


def test_backtest_requires_data():
    with pytest.raises(ValueError, match="keine Kursdaten"):
        webapp.api_backtest({"strategy": "sma_cross", "params": {}})


def test_backtest_returns_charts_and_stats():
    webapp.api_generate({"days": 600, "seed": 2})
    out = webapp.api_backtest({"strategy": "sma_cross", "params": {"fast": 10, "slow": 30}})
    assert "total_return" in out["stats"]
    assert len(out["equity_chart"]["equity"]) == len(out["equity_chart"]["dates"])
    assert "benchmark" in out["equity_chart"]
    assert isinstance(out["trades"], list)


def test_upload_csv_via_stringio():
    csv = "Date,Close\n2024-01-01,100\n2024-01-02,101\n2024-01-03,102\n"
    info = webapp.api_upload({"filename": "x.csv", "content": csv})
    assert info["rows"] == 3
    assert webapp._STATE["df"]["Close"].iloc[-1] == 102


def test_optimize_endpoint():
    webapp.api_generate({"days": 500, "seed": 3})
    out = webapp.api_optimize(
        {"strategy": "sma_cross", "grid": {"fast": [5, 10], "slow": [30, 60]}, "metric": "sharpe"}
    )
    assert len(out["ranking"]) == 4
    assert set(out["best_params"]) == {"fast", "slow"}


def test_walkforward_endpoint():
    webapp.api_generate({"days": 900, "seed": 4})
    out = webapp.api_walkforward(
        {"strategy": "sma_cross", "grid": {"fast": [10], "slow": [50]}, "train": 400, "test": 150}
    )
    assert out["total_windows"] >= 1
    assert len(out["oos_equity_chart"]["equity"]) > 0
    assert "sharpe" in out["oos_stats"]


def test_clean_handles_inf_and_nan():
    assert webapp._clean(float("inf")) is None
    assert webapp._clean(float("nan")) is None
    assert webapp._clean(1.23456789) == pytest.approx(1.234568)


def test_downsample_keeps_last_point():
    import pandas as pd

    series = pd.Series(range(2000), index=pd.bdate_range("2020-01-01", periods=2000))
    reduced = webapp._downsample(series, n=300)
    assert len(reduced) <= 301
    assert reduced.iloc[-1] == series.iloc[-1]
