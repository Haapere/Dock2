import numpy as np
import pandas as pd
import pytest

from strategylab.backtest import Backtester
from strategylab.data import generate_synthetic
from strategylab.strategy import Strategy, get_strategy


def make_df(prices, start="2024-01-01"):
    idx = pd.bdate_range(start, periods=len(prices))
    prices = pd.Series(prices, index=idx, dtype=float)
    return pd.DataFrame(
        {"Open": prices, "High": prices, "Low": prices, "Close": prices, "Volume": 0.0}
    )


class AlwaysLong(Strategy):
    name = "always_long_test"
    params: dict = {}

    def generate_signals(self, df):
        return pd.Series(1.0, index=df.index)


class NeverInvested(Strategy):
    name = "never_test"
    params: dict = {}

    def generate_signals(self, df):
        return pd.Series(0.0, index=df.index)


def test_flat_strategy_keeps_capital():
    df = make_df([100, 110, 120, 130, 140])
    result = Backtester(initial_capital=10_000).run(NeverInvested(), df)
    assert result.equity.iloc[-1] == pytest.approx(10_000)
    assert result.stats["num_trades"] == 0


def test_always_long_tracks_market_minus_costs():
    df = make_df([100, 110, 121, 133.1])
    bt = Backtester(initial_capital=10_000, commission=0.0, slippage=0.0)
    result = bt.run(AlwaysLong(), df)
    # Signal von Tag 1 wird zum Schlusskurs von Tag 1 (=100) ausgeführt,
    # Renditen laufen ab Tag 2 auf -> volle Marktrendite.
    expected = 10_000 * (133.1 / 100)
    assert result.equity.iloc[-1] == pytest.approx(expected)


def test_no_lookahead_bias():
    """Signal am Tag t darf die Rendite von Tag t nicht mehr mitnehmen."""
    df = make_df([100, 100, 200, 200])  # Sprung am Tag 3 (Index 2)

    class BuysOnJumpDay(Strategy):
        name = "jump_test"
        params: dict = {}

        def generate_signals(self, df):
            # Signal erst an dem Tag, an dem der Sprung passiert
            sig = pd.Series(0.0, index=df.index)
            sig.iloc[2:] = 1.0
            return sig

    bt = Backtester(commission=0.0, slippage=0.0)
    result = bt.run(BuysOnJumpDay(), df)
    # Der 100%-Sprung liegt vor dem Einstieg -> keine Rendite daraus
    assert result.stats["total_return"] == pytest.approx(0.0)


def test_costs_reduce_returns():
    df = generate_synthetic(days=400, seed=7)
    strategy_cheap = get_strategy("sma_cross", fast=5, slow=20)
    strategy_costly = get_strategy("sma_cross", fast=5, slow=20)
    r_free = Backtester(commission=0.0, slippage=0.0).run(strategy_cheap, df)
    r_costly = Backtester(commission=0.01, slippage=0.005).run(strategy_costly, df)
    assert r_costly.equity.iloc[-1] < r_free.equity.iloc[-1]
    assert r_costly.stats["total_costs_pct"] > 0


def test_trades_extracted():
    df = make_df([100, 101, 102, 103, 104, 105, 106, 107])

    class OneTrade(Strategy):
        name = "one_trade_test"
        params: dict = {}

        def generate_signals(self, df):
            sig = pd.Series(0.0, index=df.index)
            sig.iloc[1:4] = 1.0
            return sig

    result = Backtester(commission=0.0, slippage=0.0).run(OneTrade(), df)
    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["side"] == "long"
    assert not trade["open"]
    # Einstieg Close Tag 1 (101), Ausstieg Close Tag 4 (104)
    assert trade["return"] == pytest.approx(104 / 101 - 1)


def test_builtin_strategies_run_without_error():
    df = generate_synthetic(days=600, seed=3)
    for name in ("sma_cross", "rsi_reversion", "momentum", "bollinger_breakout", "buy_hold"):
        result = Backtester().run(get_strategy(name), df)
        assert len(result.equity) == len(df)
        assert result.equity.notna().all()
        assert set(np.unique(result.positions)) <= {-1.0, 0.0, 1.0}


def test_invalid_strategy_params_rejected():
    with pytest.raises(ValueError):
        get_strategy("sma_cross", nonsense=1)
    with pytest.raises(KeyError):
        get_strategy("does_not_exist")
