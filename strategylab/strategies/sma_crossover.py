"""Trendfolge: Kreuzung zweier gleitender Durchschnitte."""

from __future__ import annotations

import pandas as pd

from strategylab.indicators import sma
from strategylab.strategy import Strategy, register_strategy


@register_strategy
class SmaCrossover(Strategy):
    """Long, wenn der schnelle SMA über dem langsamen liegt.

    Mit allow_short=True wird bei umgekehrter Lage short statt flat gegangen.
    """

    name = "sma_cross"
    params = {"fast": 20, "slow": 50, "allow_short": False}

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        fast = int(self.p["fast"])
        slow = int(self.p["slow"])
        if fast >= slow:
            raise ValueError(f"fast ({fast}) muss kleiner als slow ({slow}) sein")
        fast_ma = sma(df["Close"], fast)
        slow_ma = sma(df["Close"], slow)
        long = (fast_ma > slow_ma).astype(float)
        if self.p["allow_short"]:
            short = (fast_ma < slow_ma).astype(float)
            position = long - short
        else:
            position = long
        # Solange die MAs noch nicht berechenbar sind: flat
        position[fast_ma.isna() | slow_ma.isna()] = 0.0
        return position
