"""Mean Reversion: Einstieg bei überverkauftem RSI, Ausstieg bei Erholung."""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategylab.indicators import rsi, sma
from strategylab.strategy import Strategy, register_strategy


@register_strategy
class RsiMeanReversion(Strategy):
    """Kauft bei RSI unter `oversold`, verkauft bei RSI über `exit_level`.

    Optionaler Trendfilter: Positionen nur oberhalb des `trend_window`-SMA,
    um nicht in fallende Märkte hinein zu kaufen.
    """

    name = "rsi_reversion"
    params = {"window": 14, "oversold": 30, "exit_level": 55, "trend_window": 200}

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df["Close"]
        r = rsi(close, int(self.p["window"]))

        entry = r < float(self.p["oversold"])
        exit_ = r > float(self.p["exit_level"])

        # Zustandslogik: Position halten, bis das Exit-Signal kommt.
        position = np.zeros(len(close))
        holding = False
        entry_arr = entry.to_numpy()
        exit_arr = exit_.to_numpy()
        for i in range(len(close)):
            if holding and exit_arr[i]:
                holding = False
            elif not holding and entry_arr[i]:
                holding = True
            position[i] = 1.0 if holding else 0.0

        result = pd.Series(position, index=close.index)

        trend_window = int(self.p["trend_window"])
        if trend_window > 0:
            trend = sma(close, trend_window)
            result[close < trend] = 0.0
            result[trend.isna()] = 0.0
        return result
