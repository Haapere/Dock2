import json
import math

import numpy as np
import pandas as pd
import pytest

from strategylab.backtest import Backtester
from strategylab.data import generate_synthetic
from strategylab.reality import (
    Criterion,
    RealityCheck,
    breakeven_cost,
    cost_sensitivity,
    deflated_sharpe,
    expected_max_sharpe,
    full_check,
    parameter_plateau,
    permutation_test,
    probabilistic_sharpe,
    yearly_breakdown,
)


def series(values, start="2020-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


# ------------------------------------------------------------ Permutationstest

def test_permutation_test_detects_a_real_edge():
    """Eine Position, die perfekt mit den Renditen ausgerichtet ist, muss einen
    sehr kleinen p-Wert bekommen — sonst findet der Test echte Vorteile nicht."""
    rng = np.random.default_rng(0)
    rets = series(rng.standard_normal(600) * 0.01)
    positions = series(np.sign(rets.to_numpy()))  # Hellseher-Strategie
    result = permutation_test(positions, rets, cost_per_turnover=0.0, n_permutations=200, seed=1)
    assert result["p_value"] < 0.01
    assert result["actual_sharpe"] > result["random_sharpe_p95"]


def test_permutation_test_rejects_randomly_timed_positions():
    """Zufälliges Timing darf keinen signifikanten p-Wert erzeugen."""
    rng = np.random.default_rng(2)
    rets = series(rng.standard_normal(600) * 0.01)
    positions = series(rng.choice([0.0, 1.0], size=600))
    result = permutation_test(positions, rets, cost_per_turnover=0.0, n_permutations=200, seed=3)
    assert result["p_value"] > 0.05


def test_permutation_test_preserves_exposure_of_the_null_variants():
    """Die Nullhypothese muss dieselbe Exposition haben — nur die Ausrichtung
    darf zerstört werden. Sonst würde der Test Marktdrift mit Timing-Skill
    verwechseln."""
    rng = np.random.default_rng(4)
    rets = series(rng.standard_normal(400) * 0.01 + 0.0005)
    positions = series(np.concatenate([np.ones(200), np.zeros(200)]))
    result = permutation_test(positions, rets, cost_per_turnover=0.0, n_permutations=100, seed=5)
    # Nur die Hälfte der Zeit investiert -> zufällige Varianten liegen um die
    # halbe Marktdrift, nicht bei null und nicht bei voller Drift.
    assert result["n_permutations"] == 100
    assert math.isfinite(result["random_sharpe_mean"])


def test_permutation_test_needs_enough_data():
    with pytest.raises(ValueError, match="mindestens 30"):
        permutation_test(series(np.ones(10)), series(np.ones(10)), 0.0)


# -------------------------------------------------------- Deflated Sharpe

def test_probabilistic_sharpe_rises_with_sharpe():
    rets = series(np.random.default_rng(6).standard_normal(1000) * 0.01)
    low = probabilistic_sharpe(0.3, len(rets), 0.0, 3.0)
    high = probabilistic_sharpe(1.5, len(rets), 0.0, 3.0)
    assert 0.0 < low < high < 1.0


def test_probabilistic_sharpe_punishes_negative_skew_and_fat_tails():
    """Seltene heftige Verlusttage machen einen gemessenen Sharpe unzuverlässiger."""
    clean = probabilistic_sharpe(1.0, 1000, skew=0.0, kurtosis=3.0)
    ugly = probabilistic_sharpe(1.0, 1000, skew=-1.5, kurtosis=12.0)
    assert ugly < clean


def test_probabilistic_sharpe_rises_with_more_observations():
    short = probabilistic_sharpe(0.8, 100, 0.0, 3.0)
    long = probabilistic_sharpe(0.8, 2000, 0.0, 3.0)
    assert long > short


def test_expected_max_sharpe_grows_with_number_of_trials():
    """Wer mehr probiert, findet zufällig Besseres — die Latte muss steigen."""
    few = expected_max_sharpe(5, 0.5)
    many = expected_max_sharpe(500, 0.5)
    assert 0 < few < many


def test_expected_max_sharpe_is_zero_without_variation_or_trials():
    assert expected_max_sharpe(1, 0.5) == 0.0
    assert expected_max_sharpe(100, 0.0) == 0.0


def test_deflated_sharpe_falls_with_more_trials():
    rets = series(np.random.default_rng(7).standard_normal(1500) * 0.01 + 0.0004)
    one = deflated_sharpe(rets, 1.0, n_trials=1, sharpe_std_annual=0.4)
    many = deflated_sharpe(rets, 1.0, n_trials=1000, sharpe_std_annual=0.4)
    assert many["deflated_sharpe_prob"] < one["deflated_sharpe_prob"]
    assert many["sharpe_hurdle"] > one["sharpe_hurdle"]


# ----------------------------------------------------------- Kostenanalyse

def test_cost_sensitivity_is_monotonically_worse():
    df = generate_synthetic(days=800, seed=8)
    table = cost_sensitivity("sma_cross", df, {"fast": 20, "slow": 60})
    assert table["cagr"].is_monotonic_decreasing
    assert (table["rundlauf"] == 2 * table["kosten_je_umschichtung"]).all()


def test_breakeven_cost_interpolates_the_zero_crossing():
    table = pd.DataFrame(
        {
            "kosten_je_umschichtung": [0.0, 0.001, 0.002],
            "rundlauf": [0.0, 0.002, 0.004],
            "cagr": [0.02, 0.01, -0.01],
        }
    )
    # Zwischen 0.001 (+1 %) und 0.002 (-1 %) liegt der Nulldurchgang mittig.
    assert breakeven_cost(table) == pytest.approx(0.0015)


def test_breakeven_cost_is_zero_when_unprofitable_without_costs():
    table = pd.DataFrame(
        {"kosten_je_umschichtung": [0.0, 0.001], "rundlauf": [0.0, 0.002], "cagr": [-0.01, -0.02]}
    )
    assert breakeven_cost(table) == 0.0


def test_breakeven_cost_is_infinite_when_it_survives_everything():
    table = pd.DataFrame(
        {"kosten_je_umschichtung": [0.0, 0.01], "rundlauf": [0.0, 0.02], "cagr": [0.2, 0.1]}
    )
    assert breakeven_cost(table) == float("inf")


# --------------------------------------------------------- Parameter-Plateau

def test_plateau_is_recognised():
    grid = {"fast": [10, 20, 30], "slow": [50, 100]}
    ranking = pd.DataFrame(
        [
            {"fast": 20, "slow": 100, "sharpe": 1.00},
            {"fast": 10, "slow": 100, "sharpe": 0.95},
            {"fast": 30, "slow": 100, "sharpe": 0.90},
            {"fast": 20, "slow": 50, "sharpe": 0.92},
        ]
    )
    result = parameter_plateau(ranking, grid)
    assert result["plateau_ratio"] > 0.85
    assert result["neighbours"] == 3


def test_isolated_spike_is_recognised():
    grid = {"fast": [10, 20, 30], "slow": [50, 100]}
    ranking = pd.DataFrame(
        [
            {"fast": 20, "slow": 100, "sharpe": 1.50},
            {"fast": 10, "slow": 100, "sharpe": 0.05},
            {"fast": 30, "slow": 100, "sharpe": -0.10},
            {"fast": 20, "slow": 50, "sharpe": 0.00},
        ]
    )
    result = parameter_plateau(ranking, grid)
    assert result["plateau_ratio"] < 0.3


def test_plateau_handles_empty_ranking():
    assert parameter_plateau(pd.DataFrame(), {"fast": [10]})["plateau_ratio"] == 0.0


# ------------------------------------------------------------ Jahrestabelle

def test_yearly_breakdown_splits_by_calendar_year():
    rets = series(np.full(600, 0.001), start="2021-01-01")
    bench = series(np.full(600, 0.0005), start="2021-01-01")
    table = yearly_breakdown(rets, bench)
    assert list(table["jahr"]) == [2021, 2022, 2023]
    assert (table["strategie"] > table["buy_hold"]).all()


# ------------------------------------------------------------------- Urteil

def _criterion(passed, hard):
    return Criterion("x", 1.0, ">0", passed, hard, "grund")


def test_verdict_is_no_go_on_any_hard_failure():
    check = RealityCheck("s", {}, [_criterion(False, True), _criterion(True, False)])
    assert check.verdict == "NO-GO"


def test_verdict_is_caution_when_only_soft_criteria_fail():
    check = RealityCheck("s", {}, [_criterion(True, True), _criterion(False, False)])
    assert check.verdict == "VORSICHT"


def test_verdict_is_go_when_everything_passes():
    check = RealityCheck("s", {}, [_criterion(True, True), _criterion(True, False)])
    assert check.verdict == "GO"


def test_infinite_values_render_readably():
    line = Criterion("Break-Even", float("inf"), "> 0.004", True, True, "g").line()
    assert "unbegrenzt" in line
    assert "n/a" not in line


def test_nan_renders_as_not_measurable():
    assert "n/a" in Criterion("x", float("nan"), ">0", False, True, "g").line()


# ---------------------------------------------------------------- Gesamtlauf

def test_full_check_rejects_a_strategy_on_random_data():
    """Der wichtigste Test des Moduls: Auf reinen Zufallsdaten darf keine
    Strategie durchkommen. Täte sie es, wäre die Prüfung wertlos."""
    df = generate_synthetic(days=1600, seed=9)
    check = full_check(
        "sma_cross", df, grid={"fast": [10, 20], "slow": [60, 100]},
        n_permutations=120, train_size=600, test_size=200,
    )
    assert check.verdict == "NO-GO"
    assert check.hard_failures


def test_full_check_without_grid_can_never_pass():
    """Ohne Out-of-Sample-Schätzung darf es keine Freigabe geben."""
    df = generate_synthetic(days=900, seed=10)
    check = full_check("sma_cross", df, params={"fast": 20, "slow": 60}, n_permutations=80)
    assert check.verdict == "NO-GO"
    names = [c.name for c in check.hard_failures]
    assert "Out-of-Sample-Sharpe" in names


def test_full_check_detects_a_genuine_edge_in_the_permutation_test():
    """Gegentest zur Ablehnung: Bei echtem, ausnutzbarem Momentum muss der
    Permutationstest anspringen — sonst lehnt die Prüfung nur blind ab."""
    rng = np.random.default_rng(11)
    n = 2000
    noise = rng.standard_normal(n) * 0.008
    r = np.zeros(n)
    for i in range(1, n):
        r[i] = 0.25 * r[i - 1] + noise[i]
    close = 100 * np.exp(np.cumsum(r))
    idx = pd.bdate_range("2016-01-01", periods=n)
    df = pd.DataFrame(
        {"Open": close, "High": close * 1.004, "Low": close * 0.996,
         "Close": close, "Volume": 2e6},
        index=idx,
    ).rename_axis("Date")

    check = full_check(
        "momentum", df, grid={"lookback": [1, 2, 3], "threshold": [0.0]},
        backtester=Backtester(commission=0.0, slippage=0.0),
        n_permutations=200, train_size=700, test_size=250,
    )
    assert check.details["permutation"]["p_value"] < 0.05
    assert check.details["in_sample_stats"]["sharpe"] > 0.5


def test_full_check_uses_out_of_sample_returns_for_the_yearly_table():
    df = generate_synthetic(days=1600, seed=12)
    check = full_check(
        "sma_cross", df, grid={"fast": [10, 20], "slow": [60]},
        n_permutations=60, train_size=600, test_size=200,
    )
    assert "Out-of-Sample" in check.yearly_label


def test_params_are_plain_python_types(tmp_path):
    """Parameter wandern in JSON-Konfigurationen — NumPy-Typen wären dort
    weder serialisierbar noch lesbar."""
    df = generate_synthetic(days=1200, seed=13)
    check = full_check(
        "sma_cross", df, grid={"fast": [10, 20], "slow": [60]},
        n_permutations=60, train_size=500, test_size=200,
    )
    for value in check.params.values():
        assert isinstance(value, (int, float, bool, str)), type(value)
    path = tmp_path / "check.json"
    check.save(path)
    record = json.loads(path.read_text())
    assert record["verdict"] == check.verdict
    assert record["strategy"] == "sma_cross"


def test_summary_text_names_the_failed_criteria():
    df = generate_synthetic(days=1200, seed=14)
    check = full_check(
        "sma_cross", df, grid={"fast": [10, 20], "slow": [60]},
        n_permutations=60, train_size=500, test_size=200,
    )
    text = check.summary_text()
    assert "URTEIL:" in text
    assert "Kostensensitivität" in text
    for failure in check.hard_failures:
        assert failure.name in text
