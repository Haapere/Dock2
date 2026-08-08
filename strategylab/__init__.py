"""StrategyLab - Entwickeln, Backtesten und Forward-Testen von Trading-Strategien."""

from strategylab.backtest import Backtester, BacktestResult
from strategylab.strategy import Strategy, register_strategy, get_strategy, list_strategies

__version__ = "0.2.0"


def __getattr__(name: str):
    """Nachgelagerte Importe für die Analyse-Module.

    Screener, Realitätsprüfung, Risiko, Portfolio und Bot bauen auf Backtester
    und Registry auf. Ein Import an dieser Stelle wäre ein Zirkularimport
    (risk -> backtest -> strategylab), deshalb werden sie erst beim Zugriff
    geladen. Für Nutzer verhält es sich wie ein normaler Import:
    `from strategylab import RiskConfig`.
    """
    lazy = {
        "RiskConfig": ("strategylab.risk", "RiskConfig"),
        "RiskManager": ("strategylab.risk", "RiskManager"),
        "ScreenCriteria": ("strategylab.screener", "ScreenCriteria"),
        "profile_instrument": ("strategylab.screener", "profile_instrument"),
        "screen_universe": ("strategylab.screener", "screen_universe"),
        "full_check": ("strategylab.reality", "full_check"),
        "RealityCheck": ("strategylab.reality", "RealityCheck"),
        "PortfolioConfig": ("strategylab.portfolio", "PortfolioConfig"),
        "run_portfolio": ("strategylab.portfolio", "run_portfolio"),
        "BotConfig": ("strategylab.bot", "BotConfig"),
        "run_bot": ("strategylab.bot", "run_bot"),
    }
    if name in lazy:
        module_name, attr = lazy[name]
        import importlib

        return getattr(importlib.import_module(module_name), attr)
    raise AttributeError(f"module 'strategylab' has no attribute '{name}'")


__all__ = [
    "Backtester",
    "BacktestResult",
    "Strategy",
    "register_strategy",
    "get_strategy",
    "list_strategies",
    "RiskConfig",
    "RiskManager",
    "ScreenCriteria",
    "profile_instrument",
    "screen_universe",
    "full_check",
    "RealityCheck",
    "PortfolioConfig",
    "run_portfolio",
    "BotConfig",
    "run_bot",
]
