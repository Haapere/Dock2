import math

import numpy as np
import pandas as pd
import pytest

from strategylab.data import generate_synthetic
from strategylab.screener import (
    ScreenCriteria,
    efficiency_ratio,
    er_vs_random_walk,
    profile_instrument,
    screen_universe,
    summary_text,
)


def ohlcv(close, volume=2_000_000.0, start="2015-01-01"):
    """Baut OHLCV-Daten, deren Tagesspanne zur tatsächlichen Bewegung passt.

    Eine pauschale Spanne (etwa immer ±1 %) wäre hier ein Fehler: Der Screener
    misst die Kostenhürde über die ATR, und mit fester Spanne hätte eine ruhige
    Reihe dieselbe ATR wie eine wilde. Die Kostenhürde würde nichts mehr
    unterscheiden und der Test wäre wertlos.
    """
    idx = pd.bdate_range(start, periods=len(close))
    close = pd.Series(close, index=idx, dtype=float)
    open_ = close.shift(1).fillna(close.iloc[0])
    span = close * (close.pct_change().abs().fillna(0.0) + 0.001)
    body = pd.concat([open_, close], axis=1)
    return pd.DataFrame(
        {
            "Open": open_,
            "High": body.max(axis=1) + span * 0.5,
            "Low": body.min(axis=1) - span * 0.5,
            "Close": close,
            "Volume": float(volume),
        }
    ).rename_axis("Date")


def random_walk(n=2000, sigma=0.012, seed=0, start_price=100.0):
    r = np.random.default_rng(seed).standard_normal(n) * sigma
    return start_price * np.exp(np.cumsum(r))


# ------------------------------------------------- Efficiency Ratio Kalibrierung

def test_efficiency_ratio_of_random_walk_matches_theory():
    """Ein Zufallspfad muss eine ER von etwa 1/sqrt(window) haben.

    Das ist die Grundlage der Normierung — stimmt sie nicht, sind alle
    Charaktereinstufungen falsch kalibriert.
    """
    window = 100
    ratios = [
        efficiency_ratio(pd.Series(random_walk(2500, seed=s)), window) for s in range(15)
    ]
    assert 0.6 / math.sqrt(window) < np.mean(ratios) < 1.4 / math.sqrt(window)


def test_er_ratio_separates_trend_from_mean_reversion():
    trend = pd.Series(
        100 * np.exp(np.cumsum(0.0008 + np.random.default_rng(1).standard_normal(2000) * 0.004))
    )
    x = np.zeros(2000)
    noise = np.random.default_rng(2).standard_normal(2000) * 0.01
    for i in range(1, 2000):
        x[i] = 0.85 * x[i - 1] + noise[i]
    reverting = pd.Series(100 * np.exp(x))

    assert er_vs_random_walk(trend) > 1.5
    assert er_vs_random_walk(reverting) < 0.6
    assert 0.5 < er_vs_random_walk(pd.Series(random_walk(2000, seed=3))) < 1.5


def test_er_ratio_of_random_walk_lands_in_neutral_band_on_average():
    """Der Charakter eines Zufallspfads darf im Mittel nicht als Trend oder
    Rückkehr durchgehen — sonst erzeugt der Screener Scheinbefunde."""
    characters = []
    for seed in range(12):
        profile = profile_instrument("rw", ohlcv(random_walk(2000, seed=seed)))
        characters.append(profile.character)
    assert characters.count("gemischt") >= 6


# ------------------------------------------------------- Ausschlusskriterien

def test_liquid_volatile_instrument_passes():
    profile = profile_instrument("gut", ohlcv(random_walk(2000, sigma=0.013, seed=5)))
    assert profile.passed, profile.failures
    assert profile.score > 0
    assert profile.suggested_strategies


def test_short_history_fails():
    profile = profile_instrument("kurz", ohlcv(random_walk(300, seed=6)))
    assert not profile.passed
    assert any("Historie zu kurz" in f for f in profile.failures)
    assert profile.score == 0.0


def test_low_volatility_fails_on_cost_hurdle():
    """Ein zu ruhiger Wert ist nicht handelbar: Die Kosten je Rundlauf fressen
    einen zu großen Teil der typischen Tagesbewegung."""
    profile = profile_instrument("ruhig", ohlcv(random_walk(2000, sigma=0.002, seed=7)))
    assert not profile.passed
    assert any("Zu ruhig" in f for f in profile.failures)
    assert any("Kostenhürde" in f for f in profile.failures)
    assert profile.metrics["cost_hurdle"] > 0.35


def test_penny_stock_fails():
    profile = profile_instrument("penny", ohlcv(random_walk(2000, seed=8, start_price=2.0)))
    assert not profile.passed
    assert any("Kurs zu niedrig" in f for f in profile.failures)


def test_illiquid_fails():
    profile = profile_instrument("illiquide", ohlcv(random_walk(2000, seed=9), volume=100.0))
    assert not profile.passed
    assert any("illiquide" in f for f in profile.failures)


def test_stale_prices_fail():
    """Viele Tage ohne Kursänderung deuten auf lückenhafte oder illiquide Daten."""
    moving = random_walk(1000, seed=10)
    stale = np.repeat(moving, 2)  # jeder Kurs steht zwei Tage -> 50 % Nulltage
    profile = profile_instrument("stale", ohlcv(stale))
    assert profile.metrics["stale_ratio"] > 0.15
    assert any("Datenqualität" in f for f in profile.failures)


def test_higher_costs_tighten_the_screen():
    """Wer teurer handelt, darf weniger Werte handeln."""
    df = ohlcv(random_walk(2000, sigma=0.008, seed=11))
    cheap = profile_instrument("x", df, ScreenCriteria(round_trip_cost=0.001))
    pricey = profile_instrument("x", df, ScreenCriteria(round_trip_cost=0.02))
    assert cheap.passed
    assert not pricey.passed
    assert pricey.metrics["cost_hurdle"] > cheap.metrics["cost_hurdle"]


# ------------------------------------------------------------- Selection Bias

def test_until_truncates_data():
    """Die Auswahl darf nur Daten sehen, die zum Auswahlzeitpunkt vorlagen."""
    df = ohlcv(random_walk(2000, seed=12))
    cutoff = df.index[1000]
    limited = profile_instrument("x", df, until=cutoff)
    full = profile_instrument("x", df)
    assert limited.metrics["days"] == 1001
    assert full.metrics["days"] == 2000
    assert limited.metrics["last_price"] != full.metrics["last_price"]


def test_too_little_data_after_cutoff_is_reported_not_crashed():
    df = ohlcv(random_walk(2000, seed=13))
    profile = profile_instrument("x", df, until=df.index[5])
    assert not profile.passed
    assert any("Zu wenig Daten" in f for f in profile.failures)


# ------------------------------------------------------------------- Universum

def test_screen_universe_sorts_passed_first():
    data = {
        "gut": ohlcv(random_walk(2000, sigma=0.013, seed=20)),
        "kurz": ohlcv(random_walk(200, seed=21)),
        "ruhig": ohlcv(random_walk(2000, sigma=0.001, seed=22)),
    }
    table, profiles = screen_universe(data)
    assert table.iloc[0]["bestanden"] == "ja"
    assert table.iloc[-1]["bestanden"] == "nein"
    assert len(profiles) == 3
    assert "Werteauswahl" in summary_text(table, profiles)


def test_summary_names_the_empty_result_plainly():
    data = {"kurz": ohlcv(random_walk(200, seed=23))}
    table, profiles = screen_universe(data)
    text = summary_text(table, profiles)
    assert "Kein Wert hat bestanden" in text


def test_synthetic_demo_data_is_tradeable():
    """Die mitgelieferten Demodaten müssen den Screener passieren, sonst kann
    niemand die Pipeline ohne Internetzugang ausprobieren."""
    df = generate_synthetic(days=2000, seed=42)
    profile = profile_instrument("demo", df)
    assert profile.passed, profile.failures
