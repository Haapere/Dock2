"""Validierung: Parameter-Optimierung und Walk-Forward-Analyse.

Die Walk-Forward-Analyse prüft, ob eine Strategie auch "in der Zukunft"
funktionieren dürfte: Parameter werden nur auf vergangenen Daten (Trainings-
fenster) optimiert und anschließend auf dem unmittelbar folgenden, ungesehenen
Zeitraum (Testfenster) angewendet. Das verkettete Out-of-Sample-Ergebnis ist
eine deutlich ehrlichere Schätzung als ein In-Sample-Backtest.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from strategylab import metrics
from strategylab.backtest import Backtester
from strategylab.strategy import get_strategy


def parse_grid(raw_items: list[str]) -> dict[str, list[Any]]:
    """Parst CLI-Grid-Angaben wie ['fast=10|20|30', 'slow=50|100']."""
    grid: dict[str, list[Any]] = {}
    for item in raw_items:
        if "=" not in item:
            raise ValueError(f"Ungültige Grid-Angabe: '{item}' (erwartet key=v1|v2|v3)")
        key, values = item.split("=", 1)
        parsed = []
        for v in values.split("|"):
            v = v.strip()
            try:
                parsed.append(int(v))
            except ValueError:
                try:
                    parsed.append(float(v))
                except ValueError:
                    parsed.append(v)
        grid[key.strip()] = parsed
    return grid


def grid_combinations(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    keys = sorted(grid)
    return [dict(zip(keys, combo)) for combo in itertools.product(*(grid[k] for k in keys))]


@dataclass
class OptimizationResult:
    strategy_name: str
    ranking: pd.DataFrame  # eine Zeile je Parameterkombination
    best_params: dict[str, Any]

    def summary_text(self, top: int = 10) -> str:
        lines = [
            f"Optimierung: {self.strategy_name}, {len(self.ranking)} Kombinationen",
            f"Beste Parameter (nach Sharpe): {self.best_params}",
            "",
            self.ranking.head(top).to_string(index=False),
        ]
        return "\n".join(lines)


def optimize(
    strategy_name: str,
    df: pd.DataFrame,
    grid: dict[str, list[Any]],
    backtester: Backtester | None = None,
    metric: str = "sharpe",
) -> OptimizationResult:
    """Rastersuche über Parameterkombinationen, sortiert nach `metric`.

    Achtung: Ein auf der Gesamthistorie optimiertes Ergebnis ist in-sample
    und überschätzt die Zukunftsleistung — zur Validierung walk_forward nutzen.
    """
    backtester = backtester or Backtester()
    rows = []
    for params in grid_combinations(grid):
        try:
            result = backtester.run(get_strategy(strategy_name, **params), df)
        except ValueError:
            continue  # ungültige Kombination (z.B. fast >= slow) überspringen
        rows.append(
            {
                **params,
                "sharpe": round(result.stats["sharpe"], 3),
                "cagr": round(result.stats["cagr"], 4),
                "max_drawdown": round(result.stats["max_drawdown"], 4),
                "num_trades": result.stats["num_trades"],
            }
        )
    if not rows:
        raise ValueError("Keine gültige Parameterkombination im Grid")

    ranking = pd.DataFrame(rows).sort_values(metric, ascending=False).reset_index(drop=True)
    param_keys = sorted(grid)
    best_params = {k: ranking.iloc[0][k] for k in param_keys}
    best_params = {k: (int(v) if isinstance(v, float) and float(v).is_integer() else v) for k, v in best_params.items()}
    return OptimizationResult(strategy_name=strategy_name, ranking=ranking, best_params=best_params)


@dataclass
class WalkForwardResult:
    strategy_name: str
    windows: pd.DataFrame  # eine Zeile je Fenster
    oos_equity: pd.Series  # verkettete Out-of-Sample-Equity
    oos_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    oos_stats: dict = field(default_factory=dict)

    def summary_text(self) -> str:
        s = self.oos_stats
        positive = int((self.windows["oos_return"] > 0).sum())
        lines = [
            f"Walk-Forward-Analyse: {self.strategy_name}, {len(self.windows)} Fenster",
            "",
            self.windows.to_string(index=False),
            "",
            "Verkettetes Out-of-Sample-Ergebnis:",
            f"  Gesamtrendite:  {s['total_return']:+.2%}",
            f"  CAGR:           {s['cagr']:+.2%}",
            f"  Sharpe:         {s['sharpe']:.2f}",
            f"  Max. Drawdown:  {s['max_drawdown']:.2%}",
            f"  Fenster mit positiver Rendite: {positive}/{len(self.windows)}",
            "",
            "Interpretation: Ist das OOS-Ergebnis deutlich schwächer als der",
            "In-Sample-Backtest, ist die Strategie vermutlich überangepasst",
            "und für den Live-Einsatz ungeeignet.",
        ]
        return "\n".join(lines)


def walk_forward(
    strategy_name: str,
    df: pd.DataFrame,
    grid: dict[str, list[Any]],
    train_size: int = 500,
    test_size: int = 125,
    backtester: Backtester | None = None,
    metric: str = "sharpe",
) -> WalkForwardResult:
    """Rollierende Optimierung + Out-of-Sample-Test.

    In jedem Schritt: auf `train_size` Tagen optimieren, die besten Parameter
    auf den folgenden `test_size` Tagen anwenden. Die Signale des Testfensters
    werden mit Vorlauf (Trainingsdaten als Warmup) berechnet, damit Indikatoren
    am Fensteranfang definiert sind.
    """
    backtester = backtester or Backtester()
    if len(df) < train_size + test_size:
        raise ValueError(
            f"Zu wenig Daten: {len(df)} Tage, benötigt mindestens {train_size + test_size}"
        )

    window_rows = []
    oos_return_chunks: list[pd.Series] = []

    start = 0
    while start + train_size + test_size <= len(df):
        train = df.iloc[start : start + train_size]
        # Testfenster inkl. Trainings-Warmup, ausgewertet wird nur der Testteil.
        test_with_warmup = df.iloc[start : start + train_size + test_size]
        test_index = df.index[start + train_size : start + train_size + test_size]

        opt = optimize(strategy_name, train, grid, backtester=backtester, metric=metric)
        best = opt.best_params

        full_result = backtester.run(get_strategy(strategy_name, **best), test_with_warmup)
        oos_returns = full_result.returns.loc[test_index]
        oos_return_chunks.append(oos_returns)

        oos_equity_window = (1.0 + oos_returns).cumprod()
        window_rows.append(
            {
                "train_start": train.index[0].date(),
                "test_start": test_index[0].date(),
                "test_end": test_index[-1].date(),
                **best,
                "is_sharpe": float(opt.ranking.iloc[0]["sharpe"]),
                "oos_return": round(float(oos_equity_window.iloc[-1] - 1.0), 4),
                "oos_sharpe": round(metrics.sharpe_ratio(oos_returns), 2),
            }
        )
        start += test_size

    all_oos = pd.concat(oos_return_chunks)
    oos_equity = backtester.initial_capital * (1.0 + all_oos).cumprod()
    positions_dummy = pd.Series(1.0, index=all_oos.index)
    oos_stats = metrics.summary(oos_equity, all_oos, positions_dummy, pd.DataFrame(columns=["return", "holding_days"]))

    return WalkForwardResult(
        strategy_name=strategy_name,
        windows=pd.DataFrame(window_rows),
        oos_equity=oos_equity,
        oos_returns=all_oos,
        oos_stats=oos_stats,
    )
