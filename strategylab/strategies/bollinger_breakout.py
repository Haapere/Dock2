"""Volatilitäts-Breakout über Bollinger-Bänder."""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategylab.indicators import bollinger
from strategylab.strategy import Strategy, register_strategy


@register_strategy
class BollingerBreakout(Strategy):
    """Kauft beim Ausbruch über das obere Band, verkauft beim Rückfall unter das Mittelband."""

    name = "bollinger_breakout"
    params = {"window": 20, "num_std": 2.0}

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df["Close"]
        bands = bollinger(close, int(self.p["window"]), float(self.p["num_std"]))

        entry = (close > bands["upper"]).to_numpy()
        exit_ = (close < bands["mid"]).to_numpy()
        valid = bands["upper"].notna().to_numpy()

        position = np.zeros(len(close))
        holding = False
        for i in range(len(close)):
            if not valid[i]:
                holding = False
            elif holding and exit_[i]:
                holding = False
            elif not holding and entry[i]:
                holding = True
            position[i] = 1.0 if holding else 0.0
        return pd.Series(position, index=close.index)
