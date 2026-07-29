import numpy as np
import pandas as pd
import pytest

from strategylab import indicators


@pytest.fixture
def prices():
    return pd.Series(
        [100, 102, 101, 103, 105, 104, 106, 108, 107, 109],
        index=pd.bdate_range("2024-01-01", periods=10),
        dtype=float,
    )


def test_sma_matches_manual(prices):
    result = indicators.sma(prices, 3)
    assert np.isnan(result.iloc[0]) and np.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx((100 + 102 + 101) / 3)
    assert result.iloc[-1] == pytest.approx((108 + 107 + 109) / 3)


def test_ema_converges_to_constant():
    const = pd.Series([50.0] * 100)
    result = indicators.ema(const, 10)
    assert result.iloc[-1] == pytest.approx(50.0)


def test_rsi_bounds_and_direction():
    up = pd.Series(np.linspace(100, 200, 50))
    down = pd.Series(np.linspace(200, 100, 50))
    rsi_up = indicators.rsi(up, 14).iloc[-1]
    rsi_down = indicators.rsi(down, 14).iloc[-1]
    assert 0 <= rsi_down < 50 < rsi_up <= 100


def test_rsi_nan_during_warmup(prices):
    result = indicators.rsi(prices, 14)
    assert result.isna().all()  # nur 10 Punkte bei Fenster 14


def test_bollinger_bands_ordering():
    rng = np.random.default_rng(0)
    prices = pd.Series(100 + rng.standard_normal(100).cumsum())
    bands = indicators.bollinger(prices, 20, 2.0).dropna()
    assert (bands["upper"] >= bands["mid"]).all()
    assert (bands["mid"] >= bands["lower"]).all()


def test_macd_columns(prices):
    result = indicators.macd(prices)
    assert list(result.columns) == ["macd", "signal", "hist"]


def test_atr_positive():
    df = pd.DataFrame(
        {
            "Open": [100.0] * 30,
            "High": [102.0] * 30,
            "Low": [99.0] * 30,
            "Close": [101.0] * 30,
            "Volume": [1000.0] * 30,
        },
        index=pd.bdate_range("2024-01-01", periods=30),
    )
    result = indicators.atr(df, 14).dropna()
    assert (result > 0).all()
    assert result.iloc[-1] == pytest.approx(3.0, rel=0.1)  # High-Low = 3
