"""Eingebaute Beispielstrategien. Der Import registriert sie in der Registry."""

from strategylab.strategies.sma_crossover import SmaCrossover
from strategylab.strategies.rsi_meanreversion import RsiMeanReversion
from strategylab.strategies.momentum import Momentum
from strategylab.strategies.bollinger_breakout import BollingerBreakout
from strategylab.strategies.buy_and_hold import BuyAndHold

__all__ = [
    "SmaCrossover",
    "RsiMeanReversion",
    "Momentum",
    "BollingerBreakout",
    "BuyAndHold",
]
