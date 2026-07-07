"""StrategyLab - Entwickeln, Backtesten und Forward-Testen von Trading-Strategien."""

from strategylab.backtest import Backtester, BacktestResult
from strategylab.strategy import Strategy, register_strategy, get_strategy, list_strategies

__version__ = "0.1.0"

__all__ = [
    "Backtester",
    "BacktestResult",
    "Strategy",
    "register_strategy",
    "get_strategy",
    "list_strategies",
]
