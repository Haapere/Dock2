"""Vektorisierte Backtesting-Engine mit Transaktionskosten und Slippage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from strategylab import metrics
from strategylab.strategy import Strategy

if TYPE_CHECKING:  # nur für Typprüfung — vermeidet Zirkularimport zur Laufzeit
    from strategylab.risk import RiskConfig, RiskResult


@dataclass
class BacktestResult:
    """Ergebnis eines Backtests inkl. Zeitreihen und Kennzahlen."""

    strategy_name: str
    params: dict
    equity: pd.Series
    returns: pd.Series
    positions: pd.Series
    trades: pd.DataFrame
    benchmark_equity: pd.Series
    stats: dict = field(default_factory=dict)
    risk: "RiskResult | None" = None
    """Protokoll der Risikoeingriffe, falls der Backtester mit `risk` läuft."""

    def summary_text(self) -> str:
        s = self.stats
        pf = s["profit_factor"]
        pf_str = "inf" if pf == float("inf") else f"{pf:.2f}"
        lines = [
            f"Strategie:          {self.strategy_name} {self.params}",
            f"Zeitraum:           {self.equity.index[0].date()} bis {self.equity.index[-1].date()} ({len(self.equity)} Tage)",
            f"Gesamtrendite:      {s['total_return']:+.2%}   (Buy&Hold: {self.stats.get('benchmark_return', 0):+.2%})",
            f"CAGR:               {s['cagr']:+.2%}",
            f"Volatilität p.a.:   {s['annual_volatility']:.2%}",
            f"Sharpe Ratio:       {s['sharpe']:.2f}",
            f"Sortino Ratio:      {s['sortino']:.2f}" if s["sortino"] != float("inf") else "Sortino Ratio:      inf",
            f"Max. Drawdown:      {s['max_drawdown']:.2%}",
            f"Calmar Ratio:       {s['calmar']:.2f}",
            f"Marktexposition:    {s['exposure']:.1%}",
            f"Trades:             {s['num_trades']}",
            f"Trefferquote:       {s['win_rate']:.1%}",
            f"Ø Trade-Rendite:    {s['avg_trade_return']:+.2%}",
            f"Profit-Faktor:      {pf_str}",
            f"Ø Haltedauer:       {s['avg_holding_days']:.1f} Tage",
        ]
        return "\n".join(lines)


class Backtester:
    """Führt eine Strategie auf OHLCV-Daten aus.

    Ausführungsmodell: Das Signal von Tag t wird zum Schlusskurs von Tag t
    ausgeführt; Renditen laufen ab Tag t+1 auf (kein Look-Ahead — die Rendite
    des Signaltags selbst wird nie mitgenommen). Kosten fallen bei jeder
    Positionsänderung an: `commission` + `slippage` als Anteil des
    gehandelten Volumens.
    """

    def __init__(
        self,
        initial_capital: float = 10_000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        risk: "RiskConfig | None" = None,
    ):
        self.initial_capital = initial_capital
        self.cost_per_turnover = commission + slippage
        self.risk = risk

    def run(self, strategy: Strategy, df: pd.DataFrame) -> BacktestResult:
        if len(df) < 2:
            raise ValueError("Backtest braucht mindestens 2 Datenpunkte")

        raw_target = strategy.generate_signals(df).astype(float)
        raw_target = raw_target.reindex(df.index).fillna(0.0)

        risk_result = None
        if self.risk is not None:
            from strategylab.risk import RiskManager

            risk_result = RiskManager(self.risk).apply(df, raw_target, self.cost_per_turnover)
            target = risk_result.positions
            limit = self.risk.max_leverage
        else:
            target = raw_target
            limit = 1.0
        target = target.clip(-limit, limit)

        # Signal von Tag t wird ab Tag t+1 gehalten -> kein Look-Ahead-Bias.
        position = target.shift(1).fillna(0.0)

        daily_returns = df["Close"].pct_change().fillna(0.0)
        turnover = position.diff().abs().fillna(position.abs())
        costs = turnover * self.cost_per_turnover

        strat_returns = position * daily_returns - costs
        equity = self.initial_capital * (1.0 + strat_returns).cumprod()

        benchmark_equity = self.initial_capital * (1.0 + daily_returns).cumprod()

        trades = self._extract_trades(position, df["Close"])

        stats = metrics.summary(equity, strat_returns, position, trades)
        stats["benchmark_return"] = metrics.total_return(benchmark_equity)
        stats["total_costs_pct"] = float(costs.sum())

        return BacktestResult(
            strategy_name=strategy.name,
            params=dict(strategy.p),
            equity=equity,
            returns=strat_returns,
            positions=position,
            trades=trades,
            benchmark_equity=benchmark_equity,
            stats=stats,
            risk=risk_result,
        )

    def _extract_trades(self, position: pd.Series, close: pd.Series) -> pd.DataFrame:
        """Zerlegt die Positionsserie in einzelne Trades (Brutto, vor Kosten).

        Ein Trade ist eine zusammenhängende Phase gleicher Richtung. Maßgeblich
        ist deshalb das Vorzeichen, nicht die Positionsgröße: Bei aktiver
        Volatilitäts-Zielsteuerung ändert sich die Größe fast täglich, und ohne
        das Vorzeichen würde jeder dieser Anpassungstage als eigener Trade
        gezählt — die Trade-Statistik wäre wertlos (hunderte "Trades" mit
        Haltedauer 1 Tag).

        Die Trade-Rendite ist die Kursbewegung in Richtung der Position, ohne
        Größenskalierung; sie misst die Qualität des Signals, nicht den
        Kapitalbeitrag.
        """
        records = []
        pos_arr = np.sign(position.to_numpy())
        dates = position.index
        prices = close.to_numpy()

        current_side = 0.0
        entry_idx = None
        for i in range(len(pos_arr)):
            side = pos_arr[i]
            if side != current_side:
                if current_side != 0.0 and entry_idx is not None:
                    records.append(self._trade_record(dates, prices, entry_idx, i, current_side))
                entry_idx = i if side != 0.0 else None
                current_side = side
        if current_side != 0.0 and entry_idx is not None:
            records.append(
                self._trade_record(dates, prices, entry_idx, len(pos_arr) - 1, current_side, open_trade=True)
            )

        columns = ["entry_date", "exit_date", "side", "entry_price", "exit_price", "return", "holding_days", "open"]
        if not records:
            return pd.DataFrame(columns=columns)
        return pd.DataFrame(records, columns=columns)

    @staticmethod
    def _trade_record(dates, prices, entry_idx, exit_idx, side, open_trade=False):
        entry_price = prices[entry_idx - 1] if entry_idx > 0 else prices[entry_idx]
        exit_price = prices[exit_idx - 1] if not open_trade and exit_idx > 0 else prices[exit_idx]
        gross = (exit_price / entry_price - 1.0) * side
        return (
            dates[entry_idx],
            dates[exit_idx],
            "long" if side > 0 else "short",
            float(entry_price),
            float(exit_price),
            float(gross),
            int(exit_idx - entry_idx),
            open_trade,
        )
