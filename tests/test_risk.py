import numpy as np
import pandas as pd
import pytest

from strategylab.backtest import Backtester
from strategylab.data import generate_synthetic
from strategylab.risk import RiskConfig, RiskManager, volatility_scale
from strategylab.strategy import Strategy, get_strategy


def frame(close, high=None, low=None, start="2022-01-01"):
    idx = pd.bdate_range(start, periods=len(close))
    close = pd.Series(close, index=idx, dtype=float)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close if high is None else pd.Series(high, index=idx, dtype=float),
            "Low": close if low is None else pd.Series(low, index=idx, dtype=float),
            "Close": close,
            "Volume": 1e6,
        }
    ).rename_axis("Date")


class AlwaysLong(Strategy):
    name = "risk_always_long"
    params: dict = {}

    def generate_signals(self, df):
        return pd.Series(1.0, index=df.index)


# ------------------------------------------------------------- Konfiguration

@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"target_vol": 0.0}, "target_vol"),
        ({"vol_window": 1}, "vol_window"),
        ({"max_leverage": 0.0}, "max_leverage"),
        ({"stop_atr_multiple": -1.0}, "stop_atr_multiple"),
        ({"max_drawdown_stop": 1.5}, "max_drawdown_stop"),
        ({"cooldown_days": -1}, "cooldown_days"),
        ({"rebalance_band": -0.1}, "rebalance_band"),
    ],
)
def test_invalid_config_is_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        RiskConfig(**kwargs).validate()


# ------------------------------------------------- Volatilitäts-Zielsteuerung

def test_volatility_scale_is_causal():
    """Die Positionsgröße für Tag t darf die Rendite von Tag t nicht kennen.

    Ohne diese Verschiebung würde der Bot im Backtest an genau den Tagen klein
    positioniert sein, an denen es kracht — ein perfekt getarnter Blick in die
    Zukunft, der jeden Backtest wertlos macht.
    """
    calm = np.full(60, 100.0) + np.arange(60) * 0.01
    close = np.concatenate([calm, [80.0], [80.5]])  # Absturz an Position 60
    scale = volatility_scale(frame(close)["Close"], target_vol=0.15, window=20)
    # Der Absturztag selbst darf die Größe noch nicht gedrückt haben ...
    assert scale.iloc[60] == scale.iloc[59]
    # ... erst danach reagiert die Steuerung.
    assert scale.iloc[61] < scale.iloc[60]


def test_volatility_scale_shrinks_when_volatility_rises():
    """Beide Phasen liegen bewusst über der Zielvolatilität — sonst schlägt die
    Deckelung auf max_leverage zu und der Test vergleicht zweimal 1,0."""
    rng = np.random.default_rng(0)
    quiet_returns = rng.standard_normal(200) * 0.0126   # ~20 % p.a.
    wild_returns = rng.standard_normal(200) * 0.0378    # ~60 % p.a.
    close = 100 * np.exp(np.cumsum(np.concatenate([quiet_returns, wild_returns])))
    scale = volatility_scale(frame(close)["Close"], target_vol=0.15, window=20)
    assert scale.iloc[150] > scale.iloc[350]
    assert scale.iloc[350] < 1.0  # in der wilden Phase echt herunterskaliert


def test_volatility_scale_respects_max_leverage():
    close = frame(np.full(200, 100.0) + np.arange(200) * 1e-6)["Close"]
    scale = volatility_scale(close, target_vol=0.15, window=20, max_leverage=1.0)
    assert scale.max() <= 1.0


def test_target_vol_none_keeps_full_size():
    df = generate_synthetic(days=300, seed=1)
    result = RiskManager(
        RiskConfig(target_vol=None, stop_atr_multiple=None, max_drawdown_stop=None)
    ).apply(df, pd.Series(1.0, index=df.index))
    assert (result.positions == 1.0).all()


# -------------------------------------------------------------- Stop-Loss

def test_stop_loss_triggers_and_is_recorded():
    # Steigt ruhig, dann ein klarer Einbruch unter den Stop.
    close = list(np.linspace(100, 110, 40)) + [95.0] + list(np.linspace(95, 100, 20))
    low = list(np.linspace(100, 110, 40)) + [90.0] + list(np.linspace(95, 100, 20))
    df = frame(close, low=low)
    result = RiskManager(
        RiskConfig(target_vol=None, stop_atr_multiple=2.0, max_drawdown_stop=None)
    ).apply(df, pd.Series(1.0, index=df.index))
    assert len(result.stop_events) >= 1
    assert result.stop_events.iloc[0]["side"] == "long"


def test_no_immediate_reentry_after_a_stop():
    """Nach einem Stop darf ein noch anliegendes Kaufsignal nicht sofort neu
    kaufen — sonst wäre der Stop wirkungslos."""
    close = list(np.linspace(100, 110, 40)) + [95.0] + list(np.linspace(95, 105, 40))
    low = list(np.linspace(100, 110, 40)) + [88.0] + list(np.linspace(95, 105, 40))
    df = frame(close, low=low)
    cfg = RiskConfig(target_vol=None, stop_atr_multiple=2.0, max_drawdown_stop=None)
    result = RiskManager(cfg).apply(df, pd.Series(1.0, index=df.index))

    stop_date = result.stop_events.iloc[0]["date"]
    after = result.positions.loc[stop_date:]
    # Das Signal bleibt durchgehend long, also muss die Sperre bis zum Ende halten.
    assert (after == 0.0).all()


def test_opposite_direction_is_allowed_after_a_stop():
    """Ein Richtungswechsel ist ein neues Signal. Ohne diese Ausnahme käme eine
    Long/Short-Strategie, die direkt von +1 auf -1 dreht, nie wieder in den
    Markt."""
    close = list(np.linspace(100, 110, 30)) + [95.0] + list(np.linspace(95, 90, 30))
    low = list(np.linspace(100, 110, 30)) + [88.0] + list(np.linspace(95, 90, 30))
    df = frame(close, low=low)
    target = pd.Series(1.0, index=df.index)
    target.iloc[35:] = -1.0  # nach dem Stop dreht die Strategie auf short
    cfg = RiskConfig(target_vol=None, stop_atr_multiple=2.0, max_drawdown_stop=None)
    result = RiskManager(cfg).apply(df, target)
    assert (result.positions.iloc[35:] < 0).any()


def test_stop_disabled_keeps_the_position():
    close = list(np.linspace(100, 110, 30)) + [80.0] * 10
    df = frame(close, low=close)
    cfg = RiskConfig(target_vol=None, stop_atr_multiple=None, max_drawdown_stop=None)
    result = RiskManager(cfg).apply(df, pd.Series(1.0, index=df.index))
    assert result.stop_events.empty
    assert (result.positions == 1.0).all()


# --------------------------------------------------------- Notabschaltung

def test_drawdown_shutdown_triggers():
    close = list(np.linspace(100, 100, 5)) + list(np.linspace(100, 60, 60))
    df = frame(close)
    cfg = RiskConfig(target_vol=None, stop_atr_multiple=None, max_drawdown_stop=0.20)
    result = RiskManager(cfg).apply(df, pd.Series(1.0, index=df.index))
    assert len(result.shutdown_events) >= 1
    assert result.shutdown_events.iloc[0]["drawdown"] <= -0.20


def test_shutdown_resets_the_high_water_mark():
    """Ohne Reset der Hochwassermarke bliebe der Drawdown für immer unter der
    Schwelle: Die Notabschaltung würde bei jeder neuen Position sofort wieder
    auslösen und der Bot käme nie mehr in den Markt."""
    down = list(np.linspace(100, 70, 40))
    recover = list(np.linspace(70, 130, 200))
    df = frame(down + recover)
    cfg = RiskConfig(
        target_vol=None, stop_atr_multiple=None, max_drawdown_stop=0.20, cooldown_days=5
    )
    result = RiskManager(cfg).apply(df, pd.Series(1.0, index=df.index))
    assert len(result.shutdown_events) >= 1
    # Nach Sperrzeit und Erholung muss wieder gehandelt werden.
    assert (result.positions.iloc[-100:] != 0).any()
    # Und es darf nicht in Dauerabschaltung laufen.
    assert len(result.shutdown_events) <= 3


def test_cooldown_keeps_the_bot_flat():
    close = list(np.linspace(100, 70, 40)) + list(np.linspace(70, 90, 60))
    df = frame(close)
    cfg = RiskConfig(
        target_vol=None, stop_atr_multiple=None, max_drawdown_stop=0.20, cooldown_days=15
    )
    result = RiskManager(cfg).apply(df, pd.Series(1.0, index=df.index))
    shutdown_idx = result.positions.index.get_loc(result.shutdown_events.iloc[0]["date"])
    window = result.positions.iloc[shutdown_idx : shutdown_idx + 15]
    assert (window == 0.0).all()


# ------------------------------------------------------- Rebalancing-Band

def test_rebalance_band_reduces_turnover():
    """Ohne Toleranzband schichtet die Vol-Steuerung täglich um und verbrennt
    Gebühren auf reinem Rauschen."""
    df = generate_synthetic(days=800, seed=2)
    target = pd.Series(1.0, index=df.index)
    no_band = RiskManager(
        RiskConfig(rebalance_band=0.0, stop_atr_multiple=None, max_drawdown_stop=None)
    ).apply(df, target)
    with_band = RiskManager(
        RiskConfig(rebalance_band=0.10, stop_atr_multiple=None, max_drawdown_stop=None)
    ).apply(df, target)

    turnover_without = no_band.positions.diff().abs().sum()
    turnover_with = with_band.positions.diff().abs().sum()
    assert turnover_with < turnover_without * 0.6


def test_min_position_suppresses_dust():
    df = generate_synthetic(days=400, seed=3, annual_vol=1.5)
    result = RiskManager(
        RiskConfig(target_vol=0.05, min_position=0.30, stop_atr_multiple=None,
                   max_drawdown_stop=None)
    ).apply(df, pd.Series(1.0, index=df.index))
    active = result.positions[result.positions != 0]
    assert (active.abs() >= 0.30).all()


# ---------------------------------------------------- Backtester-Integration

def test_backtester_without_risk_is_unchanged():
    df = generate_synthetic(days=500, seed=4)
    strategy = get_strategy("sma_cross", fast=10, slow=30)
    assert Backtester().run(strategy, df).risk is None


def test_backtester_with_risk_reduces_volatility():
    df = generate_synthetic(days=1500, seed=5)
    strategy = get_strategy("sma_cross", fast=20, slow=100)
    plain = Backtester().run(strategy, df)
    managed = Backtester(risk=RiskConfig(target_vol=0.08)).run(strategy, df)
    assert managed.stats["annual_volatility"] < plain.stats["annual_volatility"]
    assert managed.risk is not None
    assert abs(managed.stats["max_drawdown"]) <= abs(plain.stats["max_drawdown"])


def test_positions_never_exceed_max_leverage():
    df = generate_synthetic(days=800, seed=6)
    result = Backtester(risk=RiskConfig(target_vol=0.60, max_leverage=1.0)).run(
        get_strategy("sma_cross", fast=10, slow=40), df
    )
    assert result.positions.abs().max() <= 1.0 + 1e-9


def test_trades_are_counted_by_direction_not_by_resizing():
    """Bei aktiver Vol-Steuerung ändert sich die Positionsgröße fast täglich.
    Würde jede Anpassung als Trade zählen, wäre die Trade-Statistik wertlos
    (hunderte 'Trades' mit Haltedauer 1 Tag)."""
    df = generate_synthetic(days=1500, seed=7)
    strategy = get_strategy("sma_cross", fast=20, slow=100)
    plain = Backtester().run(strategy, df)
    managed = Backtester(risk=RiskConfig(target_vol=0.15)).run(strategy, df)
    assert managed.stats["num_trades"] <= plain.stats["num_trades"] + 5
    assert managed.stats["avg_holding_days"] > 10


def test_risk_summary_reports_interventions():
    df = generate_synthetic(days=1200, seed=8)
    result = Backtester(risk=RiskConfig()).run(get_strategy("sma_cross", fast=20, slow=80), df)
    text = result.risk.summary_text()
    assert "Marktexposition" in text
    assert "Stop-Loss ausgelöst" in text
