"""Risikomanagement: Positionsgröße, Stop-Loss und Notabschaltung.

Die Strategie sagt, *ob* investiert wird. Das Risikomanagement sagt, *wie viel* —
und wann Schluss ist. Für das Überleben eines Bots ist der zweite Teil wichtiger:
Ein mittelmäßiger Vorteil mit gutem Risikomanagement überlebt Jahre, ein guter
Vorteil mit Vollgas-Positionen stirbt am ersten schlechten Monat.

Drei Bausteine, die aufeinander aufbauen:

1. **Volatilitäts-Zielsteuerung** — die Positionsgröße wird so skaliert, dass das
   Depot ungefähr eine gewünschte Jahresschwankung hat. Wird der Markt unruhig,
   sinkt die Position automatisch. Das ist der wirksamste einzelne Hebel gegen
   böse Überraschungen und kostet langfristig kaum Rendite, weil hohe
   Volatilität historisch mit schlechteren Renditen zusammenfällt.

2. **ATR-Stop-Loss** — begrenzt den Verlust je Trade auf ein Vielfaches der
   typischen Tagesschwankung. Bewusst in ATR und nicht in Prozent, damit der
   Stop bei ruhigen Werten eng und bei wilden Werten weit sitzt; ein fester
   Prozentstop wird bei volatilen Werten sofort ausgelöst.

3. **Drawdown-Notabschaltung** — fällt das Depot um mehr als einen Schwellenwert
   vom Hoch, wird alles verkauft und eine Sperrzeit eingehalten. Das ist die
   Versicherung gegen den Fall, dass der Vorteil real verschwunden ist und nicht
   nur eine Pechphase durchläuft. Sie kostet Rendite, wenn sie zu Unrecht
   auslöst — dafür verhindert sie den Totalverlust.

Alles ist streng kausal: Jede Entscheidung an Tag t nutzt ausschließlich
Informationen bis Tag t. Ein Risikomanagement, das versehentlich in die Zukunft
schaut, macht jeden Backtest wertlos, und es ist genau die Stelle, an der so ein
Fehler am leichtesten passiert (etwa durch eine Volatilität, die über das ganze
Fenster gerechnet wird statt rollierend).

## Was der Stop-Loss hier *nicht* leistet

Mit Tagesdaten wird ein Stop erkannt, wenn das Tagestief den Stopkurs berührt —
verkauft wird aber erst zum Schlusskurs, weil ein Bot auf Tagesbasis nur dort
handeln kann. Der Verlust des Auslösetags fällt also in voller Höhe an; erst ab
dem Folgetag schützt der Stop. Ein echter Stop-Order beim Broker verhält sich
anders: Er füllt nahe am Stopkurs (im Crash mit Slippage darunter). Der Backtest
ist damit die pessimistische Variante — bewusst, denn die optimistische Annahme
"ich werde immer exakt am Stopkurs bedient" ist die häufigste Selbsttäuschung in
Backtests mit Stops. Intraday-Verluste kann diese Konstruktion grundsätzlich
nicht begrenzen; wer das braucht, muss echte Stop-Orders beim Broker platzieren.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategylab.indicators import atr

TRADING_DAYS = 252


@dataclass
class RiskConfig:
    """Regelwerk für die Risikosteuerung.

    Die Voreinstellungen sind bewusst konservativ: 15 % Zielvolatilität liegt
    unter der eines Aktienindex, der Hebel ist auf 1,0 begrenzt (kein
    Fremdkapital), und die Notabschaltung greift bei 20 % Depotverlust.
    """

    target_vol: float | None = 0.15
    """Angestrebte Jahresvolatilität des Depots. None schaltet die
    Volatilitäts-Zielsteuerung ab."""

    vol_window: int = 20
    """Fenster für die Volatilitätsschätzung in Tagen. Kurz genug, um auf
    Stress zu reagieren, lang genug, um nicht auf Rauschen zu zappeln."""

    max_leverage: float = 1.0
    """Obergrenze der Positionsgröße. 1,0 = niemals mehr als das eigene Kapital.
    Über 1,0 nur mit sehr gutem Grund — Hebel vervielfacht auch den Drawdown."""

    min_position: float = 0.05
    """Positionen unter dieser Größe werden auf null gesetzt. Verhindert
    Mini-Orders, deren Gebühren den Nutzen übersteigen."""

    rebalance_band: float = 0.10
    """Toleranzband für die Positionsgröße. Erst wenn die Zielgröße um mehr als
    diesen Betrag von der gehaltenen abweicht, wird umgeschichtet.

    Ohne Band ist die Volatilitäts-Zielsteuerung ein Kostengrab: Die Zielgröße
    schwankt täglich um Bruchteile eines Prozents, jede Anpassung kostet
    Gebühren und Spread, und in Summe frisst das reine Rauschen-Rebalancing den
    Vorteil auf. 0,10 heißt: erst bei 10 Prozentpunkten Abweichung handeln."""

    stop_atr_multiple: float | None = 3.0
    """Stop-Loss-Abstand als Vielfaches des ATR(14). None schaltet den Stop ab.
    Unter etwa 2 wird man vom normalen Rauschen ausgestoppt."""

    max_drawdown_stop: float | None = 0.20
    """Depotverlust vom Hoch, ab dem alles verkauft wird. None schaltet die
    Notabschaltung ab."""

    cooldown_days: int = 20
    """Sperrzeit nach einer Notabschaltung, bevor wieder gehandelt wird."""

    def validate(self) -> None:
        if self.target_vol is not None and self.target_vol <= 0:
            raise ValueError("target_vol muss positiv sein oder None")
        if self.vol_window < 2:
            raise ValueError("vol_window muss mindestens 2 sein")
        if self.max_leverage <= 0:
            raise ValueError("max_leverage muss positiv sein")
        if self.min_position < 0:
            raise ValueError("min_position darf nicht negativ sein")
        if self.rebalance_band < 0:
            raise ValueError("rebalance_band darf nicht negativ sein")
        if self.stop_atr_multiple is not None and self.stop_atr_multiple <= 0:
            raise ValueError("stop_atr_multiple muss positiv sein oder None")
        if self.max_drawdown_stop is not None and not 0 < self.max_drawdown_stop < 1:
            raise ValueError("max_drawdown_stop muss zwischen 0 und 1 liegen oder None")
        if self.cooldown_days < 0:
            raise ValueError("cooldown_days darf nicht negativ sein")


def volatility_scale(
    close: pd.Series, target_vol: float, window: int = 20, max_leverage: float = 1.0
) -> pd.Series:
    """Skalierungsfaktor für die Positionsgröße nach Volatilitäts-Ziel.

    Die Volatilität wird rollierend geschätzt und **um einen Tag verschoben**:
    Die Positionsgröße für Tag t darf nur die Volatilität bis t-1 kennen. Ohne
    diese Verschiebung würde die Schätzung den heutigen Kurs enthalten und der
    Backtest unrealistisch gut aussehen.
    """
    realized = close.pct_change().rolling(window, min_periods=max(2, window // 2)).std(ddof=1)
    annualized = realized * math.sqrt(TRADING_DAYS)
    scale = target_vol / annualized.replace(0.0, np.nan)
    return scale.shift(1).clip(upper=max_leverage).fillna(0.0)


@dataclass
class RiskResult:
    """Ergebnis der Risikosteuerung inkl. Protokoll der Eingriffe."""

    positions: pd.Series
    raw_positions: pd.Series
    stop_events: pd.DataFrame
    shutdown_events: pd.DataFrame

    def summary_text(self) -> str:
        raw_exp = float((self.raw_positions.abs() > 0).mean())
        new_exp = float((self.positions.abs() > 0).mean())
        avg_size = float(self.positions.abs()[self.positions.abs() > 0].mean() or 0.0)
        return (
            f"Risikosteuerung:\n"
            f"  Marktexposition:      {raw_exp:.1%} → {new_exp:.1%}\n"
            f"  Ø Positionsgröße:     {avg_size:.1%} des Kapitals\n"
            f"  Stop-Loss ausgelöst:  {len(self.stop_events)}×\n"
            f"  Notabschaltungen:     {len(self.shutdown_events)}×"
        )


class RiskManager:
    """Wandelt rohe Zielpositionen in risikogesteuerte Positionen um.

    Verarbeitet die Zeitreihe Tag für Tag, weil Stop-Loss und Notabschaltung
    vom bis dahin erreichten Depotstand abhängen — das lässt sich nicht
    vektorisieren, ohne in die Zukunft zu schauen.
    """

    def __init__(self, config: RiskConfig | None = None):
        self.config = config or RiskConfig()
        self.config.validate()

    def apply(
        self, df: pd.DataFrame, target: pd.Series, cost_per_turnover: float = 0.0015
    ) -> RiskResult:
        """Wendet alle Risikoregeln auf die Zielpositionsserie an.

        `target` ist die rohe Strategie-Zielposition (-1/0/+1) *vor* der
        Verschiebung durch den Backtester. Zurück kommt eine Serie im gleichen
        Format, aber mit skalierten Größen und Nullstellen dort, wo Stop oder
        Notabschaltung greifen.
        """
        cfg = self.config
        target = target.reindex(df.index).fillna(0.0).astype(float)

        if cfg.target_vol is not None:
            scale = volatility_scale(df["Close"], cfg.target_vol, cfg.vol_window, cfg.max_leverage)
        else:
            scale = pd.Series(min(1.0, cfg.max_leverage), index=df.index)

        sized = (target * scale).clip(-cfg.max_leverage, cfg.max_leverage)
        sized[sized.abs() < cfg.min_position] = 0.0

        atr_series = atr(df, 14).shift(1)  # Stopweite nur aus Vergangenheitsdaten
        close = df["Close"]
        low, high = df["Low"], df["High"]

        n = len(df)
        out = np.zeros(n)
        stop_rows: list[dict] = []
        shutdown_rows: list[dict] = []

        equity = 1.0
        peak = 1.0
        cooldown = 0
        position = 0.0
        entry_price = np.nan
        stop_price = np.nan
        # Richtung, in die nach einem Stop nicht sofort wieder eingestiegen
        # werden darf (0.0 = keine Sperre). Ohne diese Sperre würde ein noch
        # anliegendes Kaufsignal am Tag nach dem Stop sofort neu kaufen und der
        # Stop wäre wirkungslos. Ein Wechsel in die Gegenrichtung ist ein neues
        # Signal und bleibt erlaubt — sonst käme eine Long/Short-Strategie, die
        # direkt von +1 auf -1 dreht, nie wieder in den Markt.
        blocked_side = 0.0

        sized_arr = sized.to_numpy()
        close_arr = close.to_numpy()
        low_arr, high_arr = low.to_numpy(), high.to_numpy()
        atr_arr = atr_series.to_numpy()

        for i in range(n):
            # 1) Depotentwicklung fortschreiben. Gehalten wird die Position vom
            #    Vortag (out[i-1]); die Kosten ihrer Umschichtung fallen dabei
            #    ebenfalls an, sonst löst die Notabschaltung systematisch zu
            #    spät aus.
            if i > 0:
                held = out[i - 1]
                prev_held = out[i - 2] if i > 1 else 0.0
                day_return = close_arr[i] / close_arr[i - 1] - 1.0
                turnover = abs(held - prev_held)
                equity *= (1.0 + held * day_return) * (1.0 - turnover * cost_per_turnover)
                peak = max(peak, equity)

            # 2) Notabschaltung prüfen — vor jeder neuen Entscheidung.
            if cfg.max_drawdown_stop is not None and position != 0.0:
                drawdown = equity / peak - 1.0
                if drawdown <= -cfg.max_drawdown_stop:
                    shutdown_rows.append(
                        {
                            "date": df.index[i],
                            "drawdown": round(drawdown, 4),
                            "equity": round(equity, 4),
                        }
                    )
                    # Bewusst *keine* Richtungssperre wie beim Stop-Loss: Hier
                    # wirkt die Sperrzeit. Beides zusammen würde einen Bot mit
                    # dauerhaft anliegendem Signal für immer flach stellen, weil
                    # die Sperre erst bei erloschenem Signal fiele.
                    position = 0.0
                    entry_price = stop_price = np.nan
                    cooldown = cfg.cooldown_days
                    out[i] = 0.0
                    continue

            # 3) Stop-Loss prüfen: wurde der Stopkurs heute berührt?
            if position != 0.0 and np.isfinite(stop_price):
                hit = low_arr[i] <= stop_price if position > 0 else high_arr[i] >= stop_price
                if hit:
                    stop_rows.append(
                        {
                            "date": df.index[i],
                            "side": "long" if position > 0 else "short",
                            "entry_price": round(float(entry_price), 4),
                            "stop_price": round(float(stop_price), 4),
                        }
                    )
                    blocked_side = np.sign(position)
                    position = 0.0
                    entry_price = stop_price = np.nan
                    out[i] = 0.0
                    continue

            if cooldown > 0:
                cooldown -= 1
                if cooldown == 0:
                    # Frische Hochwassermarke nach der Sperrzeit. Ohne diesen
                    # Reset bliebe der Drawdown gegenüber dem alten Hoch für
                    # immer unter der Schwelle: Die Notabschaltung würde bei
                    # jeder neuen Position sofort wieder auslösen und der Bot
                    # käme nie mehr in den Markt.
                    peak = equity
                position = 0.0
                out[i] = 0.0
                continue

            desired = sized_arr[i]

            # Toleranzband: kleine Abweichungen nicht umschichten (Kosten).
            if (
                position != 0.0
                and np.sign(desired) == np.sign(position)
                and abs(desired - position) < cfg.rebalance_band
            ):
                desired = position

            # Wiedereinstiegssperre: in der gestoppten Richtung erst wieder
            # handeln, wenn das Signal zwischenzeitlich erloschen ist.
            if blocked_side != 0.0:
                if desired == 0.0:
                    blocked_side = 0.0  # Signal erloschen, Sperre aufgehoben
                    out[i] = 0.0
                    position = 0.0
                    continue
                if np.sign(desired) == blocked_side:
                    out[i] = 0.0  # unverändertes Signal, weiter gesperrt
                    position = 0.0
                    continue
                blocked_side = 0.0  # Gegenrichtung = neues Signal, erlaubt

            # 4) Position setzen und Stopkurs bei Neueinstieg/Richtungswechsel merken.
            changed_side = np.sign(desired) != np.sign(position)
            position = desired
            if position == 0.0:
                entry_price = stop_price = np.nan
            elif changed_side or not np.isfinite(entry_price):
                entry_price = close_arr[i]
                stop_price = np.nan

            # Stopkurs setzen oder nachholen. Das Nachholen ist wichtig: Wird
            # eine Position eröffnet, bevor die ATR genug Vorlauf hat, wäre der
            # Stopkurs sonst dauerhaft undefiniert und die Position liefe für
            # immer ungesichert weiter.
            if (
                position != 0.0
                and cfg.stop_atr_multiple is not None
                and not np.isfinite(stop_price)
                and np.isfinite(atr_arr[i])
            ):
                base = entry_price if np.isfinite(entry_price) else close_arr[i]
                distance = cfg.stop_atr_multiple * atr_arr[i]
                stop_price = base - distance if position > 0 else base + distance

            out[i] = position

        return RiskResult(
            positions=pd.Series(out, index=df.index),
            raw_positions=target,
            stop_events=pd.DataFrame(stop_rows, columns=["date", "side", "entry_price", "stop_price"]),
            shutdown_events=pd.DataFrame(shutdown_rows, columns=["date", "drawdown", "equity"]),
        )
