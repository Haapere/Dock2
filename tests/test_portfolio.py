import numpy as np
import pandas as pd
import pytest

from strategylab.backtest import Backtester
from strategylab.data import generate_synthetic
from strategylab.portfolio import PortfolioConfig, run_portfolio
from strategylab.risk import RiskConfig


def universe(n=4, days=1200, seed=0):
    return {f"w{i}": generate_synthetic(days=days, seed=seed + i) for i in range(n)}


# ------------------------------------------------------------- Konfiguration

@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"weighting": "quatsch"}, "weighting"),
        ({"max_weight": 0.0}, "max_weight"),
        ({"max_weight": 1.5}, "max_weight"),
        ({"vol_window": 1}, "vol_window"),
        ({"max_gross_exposure": 0.0}, "max_gross_exposure"),
    ],
)
def test_invalid_config_is_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        PortfolioConfig(**kwargs).validate()


def test_empty_universe_is_rejected():
    with pytest.raises(ValueError, match="Kein Wert"):
        run_portfolio({}, "sma_cross")


# ------------------------------------------------------------------ Grenzen

def test_max_weight_is_never_exceeded():
    data = universe(5, seed=10)
    result = run_portfolio(
        data, "sma_cross", params={"fast": 20, "slow": 80},
        config=PortfolioConfig(max_weight=0.2),
    )
    assert result.allocations.abs().max().max() <= 0.2 + 1e-9


def test_gross_exposure_is_capped():
    data = universe(8, seed=20)
    result = run_portfolio(
        data, "buy_hold", config=PortfolioConfig(max_weight=0.5, max_gross_exposure=1.0)
    )
    assert result.allocations.abs().sum(axis=1).max() <= 1.0 + 1e-9


def test_max_weight_limits_total_investment_with_a_small_universe():
    """Bei drei Werten und 25 %-Deckel ist das Depot höchstens 75 % investiert.
    Die Grenze weicht auch dann nicht auf, wenn wenige Signale anliegen — genau
    dann wäre das Konzentrationsrisiko am größten."""
    data = universe(3, seed=30)
    result = run_portfolio(data, "buy_hold", config=PortfolioConfig(max_weight=0.25))
    assert result.allocations.abs().sum(axis=1).max() <= 0.75 + 1e-9


def test_equal_weighting_splits_evenly():
    data = universe(4, seed=40)
    result = run_portfolio(
        data, "buy_hold", config=PortfolioConfig(weighting="equal", max_weight=1.0)
    )
    last = result.allocations.iloc[-1].abs()
    assert last.max() == pytest.approx(last.min(), rel=1e-6)


def test_inverse_vol_gives_the_calm_asset_more_weight():
    data = {
        "ruhig": generate_synthetic(days=1200, seed=50, annual_vol=0.10),
        "wild": generate_synthetic(days=1200, seed=51, annual_vol=0.50),
    }
    result = run_portfolio(data, "buy_hold", config=PortfolioConfig(max_weight=1.0))
    late = result.allocations.iloc[-200:].abs().mean()
    assert late["ruhig"] > late["wild"]


# --------------------------------------------------------- Diversifikation

def test_uncorrelated_assets_reduce_portfolio_volatility():
    """Der Kern des Moduls: Streuung über unabhängige Werte muss die
    Schwankung messbar senken."""
    data = universe(5, days=1500, seed=60)
    result = run_portfolio(data, "buy_hold", config=PortfolioConfig(max_weight=0.2))
    d = result.diversification
    assert d["portfolio_vol"] < d["avg_single_vol"]
    assert d["vol_reduction"] > 0.3
    assert abs(d["avg_correlation"]) < 0.3


def test_identical_assets_give_no_diversification():
    """Fünfmal derselbe Wert ist ein Wert in fünf Verkleidungen — die
    Risikoreduktion muss dann praktisch null sein."""
    single = generate_synthetic(days=1200, seed=70)
    data = {f"kopie{i}": single.copy() for i in range(5)}
    result = run_portfolio(data, "buy_hold", config=PortfolioConfig(max_weight=0.2))
    d = result.diversification
    assert d["avg_correlation"] > 0.99
    assert abs(d["vol_reduction"]) < 0.05


def test_summary_warns_about_high_correlation():
    single = generate_synthetic(days=900, seed=80)
    data = {f"kopie{i}": single.copy() for i in range(3)}
    text = run_portfolio(data, "buy_hold").summary_text()
    assert "stark korreliert" in text
    assert "keine echte Streuung" in text


def test_summary_confirms_low_correlation():
    text = run_portfolio(universe(5, seed=90), "buy_hold").summary_text()
    assert "schwach korreliert" in text


# ------------------------------------------------------------------ Details

def test_per_instrument_table_covers_every_asset():
    data = universe(4, seed=100)
    result = run_portfolio(data, "sma_cross", params={"fast": 20, "slow": 80})
    assert set(result.per_instrument["symbol"]) == set(data)
    assert len(result.correlation) == 4


def test_per_symbol_params_are_applied():
    """Verschiedene Werte haben verschiedene Zeitkonstanten — werteigene
    Parameter müssen zu anderen Positionen führen als einheitliche."""
    data = universe(2, seed=110)
    same = run_portfolio(data, "sma_cross", params={"fast": 20, "slow": 80})
    differing = run_portfolio(
        data, "sma_cross",
        params={"w0": {"fast": 5, "slow": 20}, "w1": {"fast": 50, "slow": 200}},
    )
    assert not same.allocations.equals(differing.allocations)


def test_risk_config_is_applied_per_instrument():
    data = universe(4, days=1500, seed=120)
    plain = run_portfolio(data, "sma_cross", params={"fast": 20, "slow": 80})
    managed = run_portfolio(
        data, "sma_cross", params={"fast": 20, "slow": 80},
        risk=RiskConfig(target_vol=0.08),
    )
    assert managed.stats["annual_volatility"] < plain.stats["annual_volatility"]


def test_assets_with_different_date_ranges_are_aligned():
    """Werte mit unterschiedlicher Historie dürfen nicht zum Absturz führen —
    kürzere Reihen sind vor ihrem Start einfach nicht investiert."""
    data = {
        "lang": generate_synthetic(days=1200, seed=130, start="2018-01-01"),
        "kurz": generate_synthetic(days=400, seed=131, start="2021-01-01"),
    }
    result = run_portfolio(data, "buy_hold", config=PortfolioConfig(max_weight=1.0))
    early = result.allocations.loc[:"2020-12-31", "kurz"]
    assert (early == 0.0).all()
    assert result.equity.notna().all()


def test_costs_reduce_the_result():
    data = universe(4, seed=140)
    free = run_portfolio(
        data, "sma_cross", params={"fast": 10, "slow": 40},
        backtester=Backtester(commission=0.0, slippage=0.0),
    )
    pricey = run_portfolio(
        data, "sma_cross", params={"fast": 10, "slow": 40},
        backtester=Backtester(commission=0.01, slippage=0.0),
    )
    assert pricey.stats["total_return"] < free.stats["total_return"]


def test_summary_text_contains_the_key_numbers():
    text = run_portfolio(universe(3, seed=150), "sma_cross", params={"fast": 20, "slow": 80}).summary_text()
    for expected in ("Portfolio-Backtest", "Sharpe", "Diversifikationseffekt", "Korrelationsmatrix"):
        assert expected in text
