import numpy as np
import pandas as pd
import pytest

from strategylab import metrics


def test_total_return():
    equity = pd.Series([100.0, 110.0, 121.0])
    assert metrics.total_return(equity) == pytest.approx(0.21)


def test_cagr_one_year_doubling():
    equity = pd.Series(np.linspace(100, 200, metrics.TRADING_DAYS))
    assert metrics.cagr(equity) == pytest.approx(1.0, rel=0.01)


def test_max_drawdown():
    equity = pd.Series([100.0, 120.0, 90.0, 110.0, 130.0])
    assert metrics.max_drawdown(equity) == pytest.approx(90 / 120 - 1)


def test_max_drawdown_monotonic_is_zero():
    equity = pd.Series([100.0, 101.0, 102.0, 103.0])
    assert metrics.max_drawdown(equity) == 0.0


def test_sharpe_zero_for_constant_returns():
    returns = pd.Series([0.0] * 100)
    assert metrics.sharpe_ratio(returns) == 0.0


def test_sharpe_positive_for_positive_drift():
    rng = np.random.default_rng(1)
    returns = pd.Series(0.001 + 0.01 * rng.standard_normal(500))
    assert metrics.sharpe_ratio(returns) > 0


def test_exposure():
    positions = pd.Series([0.0, 1.0, 1.0, 0.0])
    assert metrics.exposure(positions) == pytest.approx(0.5)


def test_trade_stats_empty():
    stats = metrics.trade_stats(pd.DataFrame(columns=["return", "holding_days"]))
    assert stats["num_trades"] == 0
    assert stats["win_rate"] == 0.0


def test_trade_stats_values():
    trades = pd.DataFrame(
        {"return": [0.10, -0.05, 0.20, -0.05], "holding_days": [10, 5, 20, 5]}
    )
    stats = metrics.trade_stats(trades)
    assert stats["num_trades"] == 4
    assert stats["win_rate"] == pytest.approx(0.5)
    assert stats["profit_factor"] == pytest.approx(0.30 / 0.10)
    assert stats["avg_holding_days"] == pytest.approx(10.0)
