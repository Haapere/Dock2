"""Buy & Hold als Benchmark-Strategie."""

from __future__ import annotations

import pandas as pd

from strategylab.strategy import Strategy, register_strategy


@register_strategy
class BuyAndHold(Strategy):
    """Ist ab dem ersten Tag durchgehend long. Dient als Vergleichsmaßstab."""

    name = "buy_hold"
    params: dict = {}

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=df.index)
