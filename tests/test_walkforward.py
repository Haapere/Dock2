import pandas as pd
import pytest

from strategylab.data import generate_synthetic
from strategylab.walkforward import grid_combinations, optimize, parse_grid, walk_forward


def test_parse_grid():
    grid = parse_grid(["fast=10|20", "slow=50|100", "mode=a|b"])
    assert grid == {"fast": [10, 20], "slow": [50, 100], "mode": ["a", "b"]}


def test_grid_combinations_count():
    combos = grid_combinations({"a": [1, 2], "b": [3, 4, 5]})
    assert len(combos) == 6
    assert {"a": 1, "b": 3} in combos


def test_optimize_returns_ranking():
    df = generate_synthetic(days=500, seed=5)
    result = optimize("sma_cross", df, {"fast": [5, 10], "slow": [30, 60]})
    assert len(result.ranking) == 4
    assert set(result.best_params) == {"fast", "slow"}
    # Ranking absteigend nach Sharpe
    sharpes = result.ranking["sharpe"].to_list()
    assert sharpes == sorted(sharpes, reverse=True)


def test_optimize_skips_invalid_combos():
    df = generate_synthetic(days=300, seed=5)
    # fast=60/slow=30 ist ungültig (fast >= slow) und muss übersprungen werden
    result = optimize("sma_cross", df, {"fast": [10, 60], "slow": [30]})
    assert len(result.ranking) == 1


def test_walk_forward_windows_and_oos_equity():
    df = generate_synthetic(days=1000, seed=11)
    result = walk_forward(
        "sma_cross", df,
        {"fast": [10, 20], "slow": [50, 100]},
        train_size=400, test_size=150,
    )
    expected_windows = (1000 - 400) // 150
    assert len(result.windows) == expected_windows
    assert len(result.oos_equity) == expected_windows * 150
    # OOS-Equity beginnt nach dem ersten Trainingsfenster
    assert result.oos_equity.index[0] == df.index[400]
    assert "sharpe" in result.oos_stats


def test_walk_forward_requires_enough_data():
    df = generate_synthetic(days=100, seed=1)
    with pytest.raises(ValueError):
        walk_forward("sma_cross", df, {"fast": [10], "slow": [50]}, train_size=400, test_size=100)
