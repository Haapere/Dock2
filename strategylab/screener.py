"""Auswahlkriterien für handelbare Werte.

Die Frage "welchen Wert handle ich?" entscheidet über den Erfolg eines Bots
mindestens so stark wie die Strategie selbst. Dieses Modul beantwortet sie
nicht mit Bauchgefühl, sondern mit messbaren Eigenschaften der Kursreihe.

Die Kennzahlen zerfallen in zwei Gruppen:

**Ausschlusskriterien** (hart, K.-o.): Liquidität, Preisniveau, Historienlänge,
Volatilitätsband, Kostenhürde, Datenqualität, Gap-Risiko. Wer hier durchfällt,
ist für einen systematischen Bot ungeeignet — egal wie gut der Backtest aussieht.
Der häufigste stille Killer ist die **Kostenhürde**: Bewegt sich ein Wert im
Schnitt 0,8 % pro Tag und kostet ein Rundlauf 0,3 %, dann frisst jeder Trade ein
Drittel einer Tagesbewegung. Solche Werte sind praktisch nicht profitabel zu
handeln, obwohl der kostenlose Backtest glänzt.

**Charakterisierung** (weich, richtungsweisend): Efficiency Ratio und
Lag-1-Autokorrelation sagen, *welche Art* Strategie zum Wert passt — Trendfolge
braucht trendende Werte, Mean Reversion braucht rückkehrende. Eine Trendfolge-
Strategie auf einem Seitwärtswert zu optimieren erzeugt zuverlässig Overfitting.

Wichtig gegen Selection Bias: Die Auswahl darf nur Daten sehen, die zum
Auswahlzeitpunkt vorlagen. Dafür gibt es `until` — die Kennzahlen werden dann
ausschließlich aus Daten bis zu diesem Datum berechnet. Wer sein Universum auf
der vollen Historie screent und anschließend auf derselben Historie backtestet,
misst nur noch, welche Werte in der Vergangenheit gut liefen.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from strategylab.indicators import atr

TRADING_DAYS = 252


@dataclass
class ScreenCriteria:
    """Schwellenwerte für die Werteauswahl.

    Die Voreinstellungen zielen auf einen Retail-Bot mit Tagesdaten, der bei
    einem Neobroker mit rund 0,1 % Gebühr plus 0,05 % Slippage je Rundlauf
    handelt. Wer andere Kosten hat, muss vor allem `max_cost_hurdle` anpassen.
    """

    min_years: float = 5.0
    """Mindesthistorie. Unter ~5 Jahren fehlt die Datenbasis für eine
    Walk-Forward-Validierung mit mehreren unabhängigen Testfenstern."""

    min_median_turnover: float = 5_000_000.0
    """Medianer Tagesumsatz (Kurs × Volumen) in Währungseinheiten. Darunter
    bewegt die eigene Order den Kurs und die Slippage-Annahme wird unrealistisch."""

    min_price: float = 5.0
    """Mindestkurs. Bei Pennystocks ist der Spread in Prozent unkalkulierbar."""

    min_annual_vol: float = 0.12
    """Unter ~12 % Jahresvolatilität sind die Bewegungen zu klein, um nach
    Kosten etwas übrig zu lassen."""

    max_annual_vol: float = 0.60
    """Über ~60 % dominieren Sprünge und Nachrichten; Tagesdaten-Signale
    kommen zu spät und Stops werden ausgehebelt."""

    max_cost_hurdle: float = 0.35
    """Rundlaufkosten geteilt durch die typische Tagesbewegung (ATR%). Der
    wichtigste Filter überhaupt — siehe Modul-Docstring."""

    max_stale_ratio: float = 0.15
    """Anteil Tage ohne Kursveränderung. Hohe Werte deuten auf illiquide
    Werte oder lückenhafte Daten hin."""

    max_gap_ratio: float = 0.05
    """Anteil Tage mit Eröffnungssprung über 2×ATR. Wo häufig gesprungen wird,
    greifen Stop-Loss-Regeln nicht zum gewünschten Kurs."""

    round_trip_cost: float = 0.003
    """Angenommene Gesamtkosten eines Rundlaufs (rein + raus), inkl. Spread.
    0,003 = 0,3 %. Lieber zu hoch als zu niedrig ansetzen."""

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class InstrumentProfile:
    """Messwerte und Urteil für einen einzelnen Wert."""

    symbol: str
    metrics: dict[str, float]
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    @property
    def character(self) -> str:
        """Trendend, rückkehrend oder gemischt — bestimmt die Strategiefamilie.

        Maßstab ist `er_ratio`, die Efficiency Ratio relativ zum Zufallspfad
        (siehe `er_vs_random_walk`). Absolute ER-Schwellen wären hier ein
        Denkfehler: Ein reiner Zufallspfad liegt je nach Fensterlänge bei
        ER ≈ 0,1, sodass eine Schwelle von "ER > 0,3 = Trend" praktisch nie
        anspricht und jeder Wert als rückkehrend gälte.

        Das neutrale Band ist bewusst breit. Gemessen an simulierten Zufalls-
        pfaden streut er_ratio auch ohne jede echte Struktur etwa zwischen 0,6
        und 1,2 — überlappende Fenster liefern viel weniger unabhängige
        Information, als ihre Anzahl vermuten lässt. Nur außerhalb von
        0,75–1,25 ist die Einstufung mehr als Rauschen, und selbst dann ist
        sie ein Hinweis für die Strategieauswahl, kein Beweis.
        """
        er_ratio = self.metrics["er_ratio"]
        ac = self.metrics["autocorr_1"]
        if er_ratio >= 1.25 and ac > -0.02:
            return "trendend"
        if er_ratio <= 0.75 or ac < -0.05:
            return "rückkehrend"
        return "gemischt"

    @property
    def suggested_strategies(self) -> list[str]:
        return {
            "trendend": ["sma_cross", "momentum", "bollinger_breakout"],
            "rückkehrend": ["rsi_reversion"],
            "gemischt": ["sma_cross", "rsi_reversion"],
        }[self.character]

    @property
    def score(self) -> float:
        """Eignungs-Score 0–100 für die Rangfolge innerhalb der bestandenen Werte.

        Bewertet drei Dinge, die einen Wert gut handelbar machen: viel
        Bewegung im Verhältnis zu den Kosten, ausgeprägter Charakter (klar
        trendend oder klar rückkehrend statt lauwarm) und saubere Daten.
        Der Score rangiert nur — er ersetzt keine Validierung der Strategie.
        """
        if self.failures:
            return 0.0
        m = self.metrics
        # Kostenspielraum: 0 bei Hürde == Grenze, 1 bei Kosten nahe null.
        cost_room = max(0.0, 1.0 - m["cost_hurdle"] / 0.35)
        # Charakterstärke: Abstand vom Zufallspfad (er_ratio == 1.0).
        character = min(1.0, abs(m["er_ratio"] - 1.0) / 0.25)
        quality = max(0.0, 1.0 - m["stale_ratio"] / 0.15) * max(
            0.0, 1.0 - m["gap_ratio"] / 0.05
        )
        return round(100.0 * (0.5 * cost_room + 0.3 * character + 0.2 * quality), 1)


def _effective_window(close: pd.Series, window: int) -> int:
    if len(close) < window + 1:
        return max(10, len(close) // 3)
    return window


def efficiency_ratio(close: pd.Series, window: int = 100) -> float:
    """Kaufmans Efficiency Ratio: gerichtete Bewegung / zurückgelegter Weg.

    1,0 = perfekter Trend (jeder Tag in dieselbe Richtung), 0,0 = reines
    Hin und Her ohne Nettoveränderung. Über den Median vieler Fenster
    gemittelt, damit eine einzelne Trendphase das Bild nicht verzerrt.
    """
    window = _effective_window(close, window)
    direction = (close - close.shift(window)).abs()
    path = close.diff().abs().rolling(window).sum()
    ratio = direction / path.replace(0.0, np.nan)
    value = ratio.median()
    return float(value) if pd.notna(value) else 0.0


def er_vs_random_walk(close: pd.Series, window: int = 100) -> float:
    """Efficiency Ratio relativ zum Zufallspfad — der eigentlich aussagekräftige Wert.

    Ein Zufallspfad legt in `window` Schritten eine gerichtete Strecke von etwa
    √window zurück, bei einem Weg von window Schritten; seine ER liegt also
    systematisch bei rund 1/√window. Bei window=100 sind das 0,10 — eine
    absolute Schwelle wie "ER > 0,3 heißt Trend" würde deshalb nie ansprechen.

    Erst das Verhältnis trägt Information: 1,0 = ununterscheidbar von Zufall,
    deutlich über 1,0 = echte Trendneigung, deutlich unter 1,0 = Rückkehr zum
    Mittelwert.
    """
    window = _effective_window(close, window)
    baseline = 1.0 / math.sqrt(window)
    return efficiency_ratio(close, window) / baseline


def profile_instrument(
    symbol: str,
    df: pd.DataFrame,
    criteria: ScreenCriteria | None = None,
    until: str | pd.Timestamp | None = None,
) -> InstrumentProfile:
    """Vermisst einen Wert und prüft ihn gegen die Ausschlusskriterien.

    `until` schneidet die Daten ab, damit die Auswahl nur Informationen nutzt,
    die zum Auswahlzeitpunkt vorlagen (kein Selection Bias in den Backtest).
    """
    criteria = criteria or ScreenCriteria()
    if until is not None:
        df = df.loc[df.index <= pd.Timestamp(until)]
    if len(df) < 30:
        return InstrumentProfile(
            symbol=symbol,
            metrics=_empty_metrics(),
            failures=[f"Zu wenig Daten: {len(df)} Tage (mindestens 30 nötig)"],
        )

    close = df["Close"]
    rets = close.pct_change().dropna()
    years = len(df) / TRADING_DAYS

    atr_series = atr(df, 14)
    atr_pct = float((atr_series / close).median())
    if not math.isfinite(atr_pct) or atr_pct <= 0:
        atr_pct = float(rets.abs().median()) or 1e-9

    turnover = (close * df["Volume"]).replace(0.0, np.nan)
    median_turnover = float(turnover.median()) if turnover.notna().any() else 0.0

    prev_close = close.shift(1)
    gap = (df["Open"] - prev_close).abs()
    gap_ratio = float((gap > 2.0 * atr_series).mean())

    annual_vol = float(rets.std(ddof=1) * math.sqrt(TRADING_DAYS))
    cost_hurdle = criteria.round_trip_cost / atr_pct
    autocorr = float(rets.autocorr(lag=1)) if len(rets) > 10 else 0.0
    if not math.isfinite(autocorr):
        autocorr = 0.0

    metrics = {
        "days": float(len(df)),
        "years": round(years, 2),
        "last_price": round(float(close.iloc[-1]), 2),
        "median_turnover": round(median_turnover, 0),
        "annual_vol": round(annual_vol, 4),
        "atr_pct": round(atr_pct, 5),
        "cost_hurdle": round(cost_hurdle, 3),
        "efficiency_ratio": round(efficiency_ratio(close), 3),
        "er_ratio": round(er_vs_random_walk(close), 3),
        "autocorr_1": round(autocorr, 4),
        "gap_ratio": round(gap_ratio, 4),
        "stale_ratio": round(float((rets == 0).mean()), 4),
        "buyhold_return": round(float(close.iloc[-1] / close.iloc[0] - 1.0), 4),
    }

    failures: list[str] = []
    warnings: list[str] = []

    if years < criteria.min_years:
        failures.append(
            f"Historie zu kurz: {years:.1f} Jahre (mindestens {criteria.min_years:.0f})"
        )
    if metrics["last_price"] < criteria.min_price:
        failures.append(
            f"Kurs zu niedrig: {metrics['last_price']:.2f} (mindestens {criteria.min_price:.2f})"
        )
    if median_turnover > 0 and median_turnover < criteria.min_median_turnover:
        failures.append(
            f"Zu illiquide: {median_turnover:,.0f} Tagesumsatz "
            f"(mindestens {criteria.min_median_turnover:,.0f})"
        )
    elif median_turnover == 0:
        warnings.append("Kein Volumen in den Daten — Liquidität ungeprüft")
    if annual_vol < criteria.min_annual_vol:
        failures.append(
            f"Zu ruhig: {annual_vol:.1%} Jahresvolatilität "
            f"(mindestens {criteria.min_annual_vol:.0%}) — Kosten fressen die Bewegung"
        )
    if annual_vol > criteria.max_annual_vol:
        failures.append(
            f"Zu wild: {annual_vol:.1%} Jahresvolatilität "
            f"(höchstens {criteria.max_annual_vol:.0%}) — Tagessignale kommen zu spät"
        )
    if cost_hurdle > criteria.max_cost_hurdle:
        failures.append(
            f"Kostenhürde zu hoch: ein Rundlauf kostet {cost_hurdle:.0%} einer "
            f"typischen Tagesbewegung (höchstens {criteria.max_cost_hurdle:.0%})"
        )
    if metrics["stale_ratio"] > criteria.max_stale_ratio:
        failures.append(
            f"Datenqualität: {metrics['stale_ratio']:.1%} der Tage ohne Kursänderung "
            f"(höchstens {criteria.max_stale_ratio:.0%})"
        )
    if gap_ratio > criteria.max_gap_ratio:
        failures.append(
            f"Gap-Risiko: {gap_ratio:.1%} der Tage mit Eröffnungssprung über 2×ATR "
            f"(höchstens {criteria.max_gap_ratio:.0%}) — Stops greifen unzuverlässig"
        )

    if cost_hurdle > criteria.max_cost_hurdle * 0.7 and not failures:
        warnings.append("Kostenhürde nahe der Grenze — wenig Spielraum für Fehler")
    if years < criteria.min_years * 1.5 and years >= criteria.min_years:
        warnings.append("Kurze Historie — Walk-Forward liefert nur wenige Fenster")

    return InstrumentProfile(symbol=symbol, metrics=metrics, failures=failures, warnings=warnings)


def _empty_metrics() -> dict[str, float]:
    return {
        "days": 0.0, "years": 0.0, "last_price": 0.0, "median_turnover": 0.0,
        "annual_vol": 0.0, "atr_pct": 0.0, "cost_hurdle": float("inf"),
        "efficiency_ratio": 0.0, "er_ratio": 1.0, "autocorr_1": 0.0,
        "gap_ratio": 0.0, "stale_ratio": 0.0, "buyhold_return": 0.0,
    }


def screen_universe(
    data: dict[str, pd.DataFrame],
    criteria: ScreenCriteria | None = None,
    until: str | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, list[InstrumentProfile]]:
    """Screent mehrere Werte und liefert eine sortierte Übersicht.

    Rückgabe: (Tabelle, Profile). Die Tabelle ist nach Bestehen und Score
    sortiert — oben stehen die Kandidaten, die weiterverfolgt werden sollten.
    """
    profiles = [profile_instrument(sym, df, criteria, until) for sym, df in data.items()]
    rows = []
    for p in profiles:
        rows.append(
            {
                "symbol": p.symbol,
                "bestanden": "ja" if p.passed else "nein",
                "score": p.score,
                "charakter": p.character if p.passed else "-",
                "jahre": p.metrics["years"],
                "vola_pa": p.metrics["annual_vol"],
                "kostenhuerde": p.metrics["cost_hurdle"],
                "er_ratio": p.metrics["er_ratio"],
                "autokorr": p.metrics["autocorr_1"],
                "grund": "; ".join(p.failures) if p.failures else "; ".join(p.warnings),
            }
        )
    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.sort_values(
            ["bestanden", "score"], ascending=[True, False]
        ).reset_index(drop=True)
    return table, profiles


def summary_text(table: pd.DataFrame, profiles: list[InstrumentProfile]) -> str:
    """Menschenlesbarer Bericht zur Werteauswahl."""
    passed = [p for p in profiles if p.passed]
    lines = [
        f"Werteauswahl: {len(passed)} von {len(profiles)} Werten bestehen die Ausschlusskriterien",
        "",
        table.to_string(index=False),
        "",
    ]
    if passed:
        lines.append("Empfohlene Strategiefamilie je bestandenem Wert:")
        for p in sorted(passed, key=lambda x: -x.score):
            lines.append(
                f"  {p.symbol:<12} {p.character:<12} Score {p.score:>5.1f}   "
                f"→ {', '.join(p.suggested_strategies)}"
            )
        lines.append("")
    else:
        lines.append(
            "Kein Wert hat bestanden. Das ist ein Ergebnis, kein Fehler — mit\n"
            "ungeeigneten Werten ist auch die beste Strategie nicht profitabel.\n"
        )
    lines.append(
        "Bestanden heißt nur: handelbar. Ob eine Strategie darauf einen Vorteil\n"
        "hat, klärt erst 'strategylab check'."
    )
    return "\n".join(lines)
