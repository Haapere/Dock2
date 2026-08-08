"""Portfolio-Backtest über mehrere Werte.

Ein Bot auf einem einzigen Wert ist eine Wette, kein System. Selbst mit echtem
Vorteil entscheidet dann der Zufall eines einzelnen Kursverlaufs über das
Ergebnis, und der Drawdown ist so tief wie der schlechteste Lauf dieses einen
Werts. Diversifikation ist der einzige Hebel, der das Risiko senkt, *ohne* den
erwarteten Vorteil zu verkleinern — deshalb ist ein Portfolio-Backtest kein
Extra, sondern der eigentliche Test.

Die Rechnung ist dabei unbestechlich: Bei k Werten mit gleichem Vorteil und
durchschnittlicher Korrelation ρ sinkt die Portfoliovolatilität auf
√(ρ + (1-ρ)/k) der Einzelvolatilität. Aus fünf unkorrelierten Werten (ρ = 0)
wird gut die halbe Schwankung bei gleichem Ertrag — der Sharpe verdoppelt sich.
Bei ρ = 0,8, wie unter Aktien desselben Marktes üblich, bleiben davon nur rund
8 % Verbesserung. Diversifikation zahlt sich also nur aus, wenn die Werte
wirklich verschieden sind; fünf Technologieaktien sind ein Wert in fünf
Verkleidungen. Genau deshalb gibt dieses Modul die Korrelationsmatrix und den
gemessenen Diversifikationseffekt mit aus, statt Streuung zu behaupten.

Gewichtung nach inverser Volatilität (Risikoparität): Jeder Wert soll denselben
Risikobeitrag leisten. Ein Wert mit doppelter Schwankung erhält halbes Gewicht.
Ohne das dominiert der wildeste Wert das gesamte Depot, und aus dem Portfolio
wird faktisch wieder eine Einzelwette.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategylab import metrics
from strategylab.backtest import Backtester
from strategylab.risk import RiskConfig, RiskManager
from strategylab.strategy import get_strategy

TRADING_DAYS = 252


@dataclass
class PortfolioConfig:
    """Regelwerk für die Kapitalverteilung."""

    weighting: str = "inverse_vol"
    """'inverse_vol' = Risikoparität, 'equal' = Gleichgewichtung."""

    max_weight: float = 0.25
    """Obergrenze je Wert. Verhindert, dass ein einzelner Wert das Depot
    dominiert — auch dann, wenn er gerade besonders ruhig erscheint.

    Die Grenze gilt unabhängig davon, wie viele Werte gerade ein Signal haben.
    Das hat eine wichtige praktische Folge: Bei einem Universum aus drei Werten
    und max_weight = 0,25 ist das Depot höchstens 75 % investiert, der Rest
    bleibt Kasse. Wer voll investiert sein will, braucht mindestens
    1/max_weight Werte im Universum — bei 0,25 also vier. Das ist Absicht:
    Eine Obergrenze, die sich aufweicht, sobald wenige Signale anliegen, wäre
    genau dann unwirksam, wenn das Konzentrationsrisiko am größten ist."""

    vol_window: int = 60
    """Fenster der Volatilitätsschätzung für die Gewichtung."""

    max_gross_exposure: float = 1.0
    """Obergrenze für die Summe aller Positionen. 1,0 = kein Hebel; das Depot
    ist maximal vollständig investiert, nicht mehr."""

    def validate(self) -> None:
        if self.weighting not in ("inverse_vol", "equal"):
            raise ValueError("weighting muss 'inverse_vol' oder 'equal' sein")
        if not 0 < self.max_weight <= 1.0:
            raise ValueError("max_weight muss zwischen 0 und 1 liegen")
        if self.vol_window < 2:
            raise ValueError("vol_window muss mindestens 2 sein")
        if self.max_gross_exposure <= 0:
            raise ValueError("max_gross_exposure muss positiv sein")


@dataclass
class PortfolioResult:
    """Ergebnis eines Portfolio-Backtests."""

    equity: pd.Series
    returns: pd.Series
    allocations: pd.DataFrame  # tatsächlich eingesetztes Kapital je Wert
    per_instrument: pd.DataFrame
    correlation: pd.DataFrame
    stats: dict = field(default_factory=dict)
    diversification: dict = field(default_factory=dict)

    def summary_text(self) -> str:
        s = self.stats
        d = self.diversification
        lines = [
            f"Portfolio-Backtest über {len(self.per_instrument)} Werte",
            f"Zeitraum:           {self.equity.index[0].date()} bis {self.equity.index[-1].date()}",
            "",
            f"Gesamtrendite:      {s['total_return']:+.2%}",
            f"CAGR:               {s['cagr']:+.2%}",
            f"Volatilität p.a.:   {s['annual_volatility']:.2%}",
            f"Sharpe Ratio:       {s['sharpe']:.2f}",
            f"Max. Drawdown:      {s['max_drawdown']:.2%}",
            f"Calmar Ratio:       {s['calmar']:.2f}",
            "",
            "Einzelwerte (jeweils allein gehandelt):",
            self.per_instrument.to_string(index=False),
            "",
            "Diversifikationseffekt:",
            f"  Ø Korrelation der Strategierenditen: {d['avg_correlation']:.2f}",
            f"  Ø Volatilität der Einzelwerte:       {d['avg_single_vol']:.2%}",
            f"  Volatilität des Portfolios:          {d['portfolio_vol']:.2%}",
            f"  Erreichte Risikoreduktion:           {d['vol_reduction']:.1%}",
            f"  Theoretisch möglich bei dieser Ø-Korrelation: {d['theoretical_reduction']:.1%}",
            "",
        ]
        if d["avg_correlation"] > 0.7:
            lines.append(
                "Die Werte sind stark korreliert — sie bewegen sich fast gemeinsam.\n"
                "Das ist keine echte Streuung: Im Stressfall fallen alle zugleich.\n"
                "Für echte Diversifikation braucht es verschiedene Anlageklassen,\n"
                "Regionen oder Strategierichtungen, nicht mehr Werte derselben Art."
            )
        elif d["avg_correlation"] < 0.3:
            lines.append(
                "Die Werte sind schwach korreliert — das ist echte Streuung und der\n"
                "wirksamste Beitrag zu einem stabilen Depot."
            )
        lines.append("")
        lines.append("Korrelationsmatrix der Strategierenditen:")
        lines.append(self.correlation.round(2).to_string())
        return "\n".join(lines)


def _weights(
    positions: pd.DataFrame,
    asset_returns: pd.DataFrame,
    config: PortfolioConfig,
) -> pd.DataFrame:
    """Kapitalgewichte je Wert und Tag.

    Die Volatilität wird rollierend geschätzt und um einen Tag verschoben —
    die Gewichtung für Tag t darf nur Daten bis t-1 kennen. Gewichtet werden
    nur Werte, die an dem Tag tatsächlich eine Position halten; Kapital, das
    kein Signal hat, bleibt unangetastet statt die übrigen Werte zu hebeln.
    """
    active = (positions.abs() > 0).astype(float)

    if config.weighting == "equal":
        raw = active.copy()
    else:
        vol = asset_returns.rolling(
            config.vol_window, min_periods=max(2, config.vol_window // 2)
        ).std(ddof=1).shift(1)
        inv_vol = (1.0 / vol.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)
        raw = inv_vol * active

    raw = raw.fillna(0.0)
    total = raw.sum(axis=1).replace(0.0, np.nan)
    weights = raw.div(total, axis=0).fillna(0.0)

    # Deckelung je Wert, danach erneut normieren — mehrfach, weil das Kappen
    # eines Werts die Gewichte der anderen anhebt und neue Verstöße erzeugt.
    for _ in range(10):
        capped = weights.clip(upper=config.max_weight)
        if np.allclose(capped.to_numpy(), weights.to_numpy()):
            break
        room = config.max_weight - capped
        deficit = weights.sum(axis=1) - capped.sum(axis=1)
        room_total = room.sum(axis=1).replace(0.0, np.nan)
        weights = capped + room.mul(deficit / room_total, axis=0).fillna(0.0)
    weights = weights.clip(upper=config.max_weight)

    # Bruttoexposition begrenzen: Anteil investierten Kapitals nie über Grenze.
    gross = weights.sum(axis=1)
    scale = (config.max_gross_exposure / gross.replace(0.0, np.nan)).clip(upper=1.0).fillna(0.0)
    return weights.mul(scale, axis=0)


def run_portfolio(
    data: dict[str, pd.DataFrame],
    strategy_name: str,
    params: dict | dict[str, dict] | None = None,
    config: PortfolioConfig | None = None,
    backtester: Backtester | None = None,
    risk: RiskConfig | None = None,
) -> PortfolioResult:
    """Backtestet eine Strategie gleichzeitig auf mehreren Werten.

    `params` sind entweder Parameter für alle Werte oder ein Dictionary
    {symbol: params} für werteigene Parameter — Letzteres ist realistischer,
    weil verschiedene Werte verschiedene Zeitkonstanten haben.

    `risk` wendet die Risikoregeln auf jeden Wert einzeln an (Stop, Vol-Ziel);
    die Kapitalverteilung darüber übernimmt `config`.
    """
    if not data:
        raise ValueError("Kein Wert übergeben")
    config = config or PortfolioConfig()
    config.validate()
    backtester = backtester or Backtester()
    cost = backtester.cost_per_turnover

    per_symbol_params: dict[str, dict] = {}
    for symbol in data:
        if params and all(isinstance(v, dict) for v in params.values()):
            per_symbol_params[symbol] = dict(params.get(symbol, {}))
        else:
            per_symbol_params[symbol] = dict(params or {})

    index = None
    for df in data.values():
        index = df.index if index is None else index.union(df.index)

    positions: dict[str, pd.Series] = {}
    asset_returns: dict[str, pd.Series] = {}
    single_rows = []
    single_returns: dict[str, pd.Series] = {}

    for symbol, df in data.items():
        strategy = get_strategy(strategy_name, **per_symbol_params[symbol])
        target = strategy.generate_signals(df).astype(float).reindex(df.index).fillna(0.0)
        if risk is not None:
            target = RiskManager(risk).apply(df, target, cost).positions
        limit = risk.max_leverage if risk is not None else 1.0
        target = target.clip(-limit, limit)

        # Gleiches Ausführungsmodell wie im Einzel-Backtest: Signal von Tag t
        # wird ab t+1 gehalten.
        held = target.shift(1).fillna(0.0)
        rets = df["Close"].pct_change().fillna(0.0)

        positions[symbol] = held.reindex(index).fillna(0.0)
        asset_returns[symbol] = rets.reindex(index).fillna(0.0)

        single = held * rets - held.diff().abs().fillna(held.abs()) * cost
        single_returns[symbol] = single.reindex(index).fillna(0.0)
        single_equity = (1.0 + single).cumprod()
        single_rows.append(
            {
                "symbol": symbol,
                "cagr": round(metrics.cagr(single_equity), 4),
                "vola_pa": round(metrics.annual_volatility(single), 4),
                "sharpe": round(metrics.sharpe_ratio(single), 2),
                "max_dd": round(metrics.max_drawdown(single_equity), 4),
                "exposition": round(float((held.abs() > 0).mean()), 3),
            }
        )

    pos_df = pd.DataFrame(positions).reindex(index).fillna(0.0)
    ret_df = pd.DataFrame(asset_returns).reindex(index).fillna(0.0)

    weights = _weights(pos_df, ret_df, config)
    allocations = weights * pos_df

    gross_returns = (allocations * ret_df).sum(axis=1)
    turnover = allocations.diff().abs().fillna(allocations.abs()).sum(axis=1)
    portfolio_returns = gross_returns - turnover * cost

    equity = backtester.initial_capital * (1.0 + portfolio_returns).cumprod()
    stats = metrics.summary(
        equity, portfolio_returns, allocations.abs().sum(axis=1),
        pd.DataFrame(columns=["return", "holding_days"]),
    )

    single_ret_df = pd.DataFrame(single_returns)
    correlation = single_ret_df.corr()
    off_diagonal = correlation.to_numpy()[~np.eye(len(correlation), dtype=bool)]
    avg_corr = float(np.nanmean(off_diagonal)) if len(off_diagonal) else 1.0

    avg_single_vol = float(np.mean([r["vola_pa"] for r in single_rows]))
    portfolio_vol = stats["annual_volatility"]
    k = len(data)
    theoretical = 1.0 - math.sqrt(max(0.0, avg_corr + (1.0 - avg_corr) / k))

    return PortfolioResult(
        equity=equity,
        returns=portfolio_returns,
        allocations=allocations,
        per_instrument=pd.DataFrame(single_rows),
        correlation=correlation,
        stats=stats,
        diversification={
            "avg_correlation": round(avg_corr, 3),
            "avg_single_vol": round(avg_single_vol, 4),
            "portfolio_vol": round(portfolio_vol, 4),
            "vol_reduction": round(
                1.0 - portfolio_vol / avg_single_vol if avg_single_vol > 0 else 0.0, 4
            ),
            "theoretical_reduction": round(theoretical, 4),
            "n_instruments": k,
        },
    )
