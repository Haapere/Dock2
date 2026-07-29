"""Kennzahlen zur Bewertung von Backtest-Ergebnissen."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def total_return(equity: pd.Series) -> float:
    return float(equity.iloc[-1] / equity.iloc[0] - 1.0)


def cagr(equity: pd.Series) -> float:
    years = len(equity) / TRADING_DAYS
    if years <= 0:
        return 0.0
    end_over_start = equity.iloc[-1] / equity.iloc[0]
    if end_over_start <= 0:
        return -1.0
    return float(end_over_start ** (1.0 / years) - 1.0)


def annual_volatility(returns: pd.Series) -> float:
    return float(returns.std(ddof=1) * math.sqrt(TRADING_DAYS))


def sharpe_ratio(returns: pd.Series, risk_free_annual: float = 0.0) -> float:
    excess = returns - risk_free_annual / TRADING_DAYS
    std = excess.std(ddof=1)
    if std == 0 or np.isnan(std):
        return 0.0
    return float(excess.mean() / std * math.sqrt(TRADING_DAYS))


def sortino_ratio(returns: pd.Series, risk_free_annual: float = 0.0) -> float:
    excess = returns - risk_free_annual / TRADING_DAYS
    downside = excess[excess < 0]
    if len(downside) == 0:
        return float("inf") if excess.mean() > 0 else 0.0
    downside_std = math.sqrt(float((downside**2).mean()))
    if downside_std == 0:
        return 0.0
    return float(excess.mean() / downside_std * math.sqrt(TRADING_DAYS))


def max_drawdown(equity: pd.Series) -> float:
    """Maximaler Kursrückgang vom Hoch, als negative Zahl (z.B. -0.25)."""
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min())


def calmar_ratio(equity: pd.Series) -> float:
    dd = abs(max_drawdown(equity))
    if dd == 0:
        return 0.0
    return cagr(equity) / dd


def exposure(positions: pd.Series) -> float:
    """Anteil der Tage mit offener Position."""
    if len(positions) == 0:
        return 0.0
    return float((positions != 0).mean())


def trade_stats(trades: pd.DataFrame) -> dict:
    """Kennzahlen auf Trade-Ebene (erwartet Spalte 'return')."""
    if trades.empty:
        return {
            "num_trades": 0,
            "win_rate": 0.0,
            "avg_trade_return": 0.0,
            "profit_factor": 0.0,
            "avg_holding_days": 0.0,
        }
    rets = trades["return"]
    wins = rets[rets > 0]
    losses = rets[rets <= 0]
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    return {
        "num_trades": int(len(trades)),
        "win_rate": float((rets > 0).mean()),
        "avg_trade_return": float(rets.mean()),
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "avg_holding_days": float(trades["holding_days"].mean()),
    }


def summary(equity: pd.Series, returns: pd.Series, positions: pd.Series, trades: pd.DataFrame) -> dict:
    """Alle Kennzahlen als flaches Dictionary."""
    stats = {
        "total_return": total_return(equity),
        "cagr": cagr(equity),
        "annual_volatility": annual_volatility(returns),
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "max_drawdown": max_drawdown(equity),
        "calmar": calmar_ratio(equity),
        "exposure": exposure(positions),
    }
    stats.update(trade_stats(trades))
    return stats
