"""Zeitreihen-Momentum: Long bei positiver Rendite über das Lookback-Fenster."""

from __future__ import annotations

import pandas as pd

from strategylab.strategy import Strategy, register_strategy


@register_strategy
class Momentum(Strategy):
    """Long, wenn die Rendite der letzten `lookback` Tage über `threshold` liegt.

    `threshold` ist eine Dezimalrendite (0.0 = jede positive Rendite reicht).
    Mit allow_short=True wird bei Rendite unter -threshold short gegangen.
    """

    name = "momentum"
    params = {"lookback": 90, "threshold": 0.0, "allow_short": False}

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        lookback = int(self.p["lookback"])
        threshold = float(self.p["threshold"])
        momentum = df["Close"].pct_change(lookback)

        long = (momentum > threshold).astype(float)
        if self.p["allow_short"]:
            short = (momentum < -threshold).astype(float)
            position = long - short
        else:
            position = long
        position[momentum.isna()] = 0.0
        return position
