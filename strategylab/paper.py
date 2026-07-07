"""Papertrading / Forward-Test: Strategie auf neuen Daten simuliert weiterführen.

Ablauf:
1. `init` legt eine JSON-Zustandsdatei an (Strategie, Parameter, Startdatum,
   Startkapital). Das Startdatum trennt Vergangenheit von "Zukunft".
2. `update` wird später (z.B. täglich/wöchentlich) mit aktualisierten Kursdaten
   aufgerufen. Nur Daten nach dem Startdatum fließen in die Bewertung ein —
   so entsteht ein echter Out-of-Sample-Track-Record.
3. `status` zeigt die bisherige Forward-Performance und die aktuelle Position.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from strategylab.backtest import Backtester
from strategylab.strategy import get_strategy


@dataclass
class PaperAccount:
    strategy_name: str
    params: dict
    start_date: str  # ISO-Datum: ab hier zählt der Forward-Test
    initial_capital: float
    commission: float
    slippage: float
    history: list  # [{date, close, position, equity}, ...]

    @classmethod
    def load(cls, path: str | Path) -> "PaperAccount":
        with open(path) as f:
            raw = json.load(f)
        return cls(**raw)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.__dict__, f, indent=2, default=str)


def init_account(
    path: str | Path,
    strategy_name: str,
    params: dict,
    start_date: str | None = None,
    initial_capital: float = 10_000.0,
    commission: float = 0.001,
    slippage: float = 0.0005,
) -> PaperAccount:
    """Legt einen neuen Papertrading-Zustand an."""
    get_strategy(strategy_name, **params)  # validiert Name + Parameter
    account = PaperAccount(
        strategy_name=strategy_name,
        params=params,
        start_date=start_date or date.today().isoformat(),
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
        history=[],
    )
    account.save(path)
    return account


def update_account(path: str | Path, df: pd.DataFrame) -> PaperAccount:
    """Berechnet den Forward-Test mit den aktuellen Kursdaten neu.

    Die Strategie sieht die volle Historie (für Indikator-Warmup), bewertet
    wird aber ausschließlich der Zeitraum ab start_date. Die Berechnung ist
    deterministisch aus (Zustandsdatei + Kursdaten) reproduzierbar.
    """
    account = PaperAccount.load(path)
    start = pd.Timestamp(account.start_date)

    backtester = Backtester(
        initial_capital=account.initial_capital,
        commission=account.commission,
        slippage=account.slippage,
    )
    strategy = get_strategy(account.strategy_name, **account.params)
    result = backtester.run(strategy, df)

    mask = result.equity.index >= start
    if not mask.any():
        raise ValueError(
            f"Keine Kursdaten nach dem Startdatum {account.start_date} vorhanden"
        )

    fwd_returns = result.returns[mask]
    fwd_equity = account.initial_capital * (1.0 + fwd_returns).cumprod()
    fwd_positions = result.positions[mask]
    closes = df["Close"][mask]

    account.history = [
        {
            "date": d.date().isoformat(),
            "close": round(float(c), 4),
            "position": float(p),
            "equity": round(float(e), 2),
        }
        for d, c, p, e in zip(fwd_equity.index, closes, fwd_positions, fwd_equity)
    ]
    account.save(path)
    return account


def status_text(account: PaperAccount) -> str:
    header = (
        f"Papertrading: {account.strategy_name} {account.params}\n"
        f"Forward-Test seit: {account.start_date}\n"
        f"Startkapital:      {account.initial_capital:,.2f}"
    )
    if not account.history:
        return header + "\nNoch keine Daten — 'paper update' mit aktuellen Kursen aufrufen."

    last = account.history[-1]
    equity = last["equity"]
    ret = equity / account.initial_capital - 1.0
    position = {1.0: "LONG", 0.0: "FLAT", -1.0: "SHORT"}.get(last["position"], str(last["position"]))
    equities = [h["equity"] for h in account.history]
    peak = max(equities)
    dd = equity / peak - 1.0
    return (
        f"{header}\n"
        f"Letzter Stand:     {last['date']} (Close {last['close']})\n"
        f"Aktuelle Position: {position}\n"
        f"Equity:            {equity:,.2f} ({ret:+.2%})\n"
        f"Drawdown v. Hoch:  {dd:.2%}\n"
        f"Beobachtete Tage:  {len(account.history)}"
    )
