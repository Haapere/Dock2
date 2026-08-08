# StrategyLab

Ein Python-Werkzeug, um Trading-Strategien zu **entwickeln**, auf historischen Daten zu **backtesten**, ihre **Zukunftstauglichkeit zu prüfen** (Walk-Forward-Analyse und Papertrading) und daraus einen **Bot mit Risikomanagement** zu betreiben.

> **Vor dem ersten Euro lesen: [REGELN.md](REGELN.md)**
>
> Dort steht das Regelwerk, die Kriterien der Werteauswahl, die Prüfschwellen und
> der Stufenplan zum Echtgeld — inklusive der unbequemen Einordnung, was ein
> solcher Bot realistisch leisten kann und was nicht. Die kurze Fassung: Das
> Werkzeug kann keine profitable Strategie herbeirechnen. Es kann unprofitable
> Ideen zuverlässig aussortieren, bevor sie Geld kosten. Erwarte, dass die
> Realitätsprüfung deine erste Idee ablehnt — das ist der Normalfall und
> gleichzeitig ihr Nutzen.

## Installation

```bash
pip install -e ".[dev]"
```

Benötigt Python ≥ 3.10, `pandas` und `numpy`. Keine weiteren Abhängigkeiten — auch die HTML-Reports kommen ohne Plot-Bibliothek aus.

## Ganz ohne Terminal: einfach doppelklicken

Für den bequemsten Einstieg liegt für jedes System ein Start-Skript bei. Beim **ersten** Doppelklick richtet es sich selbst ein (eigene Umgebung im Projektordner, dauert ein bis zwei Minuten), danach öffnet sich die Oberfläche jedes Mal direkt im Browser:

| System  | Datei                | Hinweis |
|---------|----------------------|---------|
| Windows | `start-windows.bat`  | Doppelklick genügt |
| macOS   | `start-mac.command`  | Doppelklick; beim allerersten Mal ggf. Rechtsklick → „Öffnen" (Gatekeeper) |
| Linux   | `start-linux.sh`     | einmalig `chmod +x start-linux.sh`, dann ausführen |

Voraussetzung ist nur eine installierte **Python-3**-Version (von [python.org](https://www.python.org/downloads/) — unter Windows im Installer „Add Python to PATH" ankreuzen). Fehlt Python, sagt dir das Skript beim Start Bescheid.

Das Terminal-Fenster, das dabei aufgeht, bitte geöffnet lassen, solange du das Programm nutzt — zum Beenden `Strg+C` drücken oder das Fenster schließen.

## Grafische Oberfläche

Wenn StrategyLab bereits installiert ist, startet die Web-Oberfläche auch direkt:

```bash
strategylab gui
```

Dort lässt sich alles per Mausklick erledigen: Kursdaten laden (Demo, Stooq oder eigene CSV), Backtests mit Equity- und Drawdown-Diagramm, Parameter-Optimierung und Walk-Forward-Analyse. Kein weiterer Befehl nötig. Zum Beenden im Terminal `Strg+C` drücken.

### Auf dem Handy oder Tablet nutzen

Python läuft nicht sinnvoll direkt auf dem Handy. Stattdessen startest du das Programm auf deinem Computer im **Handy-Modus** und öffnest die Oberfläche auf dem Handy im Browser — beide Geräte im selben WLAN:

```bash
strategylab gui --lan
```

Beim Start wird eine Adresse wie `http://192.168.1.42:8765/` angezeigt. Diese gibst du auf dem Handy im Browser ein (oder legst sie als Lesezeichen/Startbildschirm-Symbol an) — fertig. Die Oberfläche ist responsiv und passt sich dem Handybildschirm an.

> Hinweis: Im Handy-Modus ist die Oberfläche für alle Geräte im selben Netzwerk erreichbar. Nutze ihn nur in vertrauenswürdigen WLANs (zu Hause), nicht in offenen öffentlichen Netzen.

## Schnellstart (Kommandozeile)

```bash
# 1. Daten besorgen: synthetische Demo-Daten ...
strategylab data generate --out data/demo.csv --days 1500

# ... oder echte Tagesdaten von stooq.com (kostenlos, ohne API-Key)
strategylab data fetch --symbol aapl.us --out data/aapl.csv
strategylab data fetch --symbol sap.de --out data/sap.csv

# 2. Verfügbare Strategien anzeigen
strategylab list

# 3. Backtest mit HTML-Report
strategylab backtest --data data/demo.csv --strategy sma_cross \
    --params fast=20,slow=50 --report report.html

# 4. Parameter optimieren (Achtung: in-sample!)
strategylab optimize --data data/demo.csv --strategy sma_cross \
    --grid "fast=10|20|30" "slow=50|100|150"

# 5. Zukunftstauglichkeit prüfen: Walk-Forward-Analyse
strategylab walkforward --data data/demo.csv --strategy sma_cross \
    --grid "fast=10|20|30" "slow=50|100" --train 500 --test 125

# 6. Forward-Test / Papertrading starten und regelmäßig fortschreiben
strategylab paper init --account paper.json --strategy sma_cross \
    --params fast=20,slow=50 --start 2026-07-07
strategylab paper update --account paper.json --data data/demo.csv
strategylab paper status --account paper.json
```

## Der empfohlene Weg: von der Idee zum Bot

Die Reihenfolge ist keine Empfehlung, sondern die Reihenfolge, in der die
Fehler auffallen, solange sie noch nichts kosten. Ausführlich in
[REGELN.md](REGELN.md).

```bash
# 1. Sind die Werte überhaupt handelbar? (Liquidität, Kosten, Volatilität, Datenqualität)
#    --until nutzt nur Daten bis zum Stichtag -- gegen Selection Bias.
strategylab screen --data data/*.csv --round-trip-cost 0.003 --until 2021-12-31

# 2. Ist der Vorteil echt oder Zufall? Vier K.-o.-Kriterien, Urteil GO/VORSICHT/NO-GO.
strategylab check --data data/aapl.csv --strategy sma_cross \
    --grid "fast=10|20|30" "slow=100|150|200" \
    --train 750 --test 250 --trials 500 --risk --save checks/aapl.json

# 3. Wie wirkt Streuung über mehrere Werte? (Korrelationsmatrix inklusive)
strategylab portfolio --data data/*.csv --strategy sma_cross \
    --params fast=20,slow=100 --risk

# 4. Bot einrichten und tägliche Orders berechnen -- nur mit Freigabe aus Schritt 2.
strategylab bot init --config bot.json
strategylab bot signals --config bot.json --holdings holdings.json --orders-csv orders.csv
```

### Werteauswahl (`screen`)

Prüft jeden Wert gegen harte Ausschlusskriterien und bestimmt seinen Charakter
(trendend / rückkehrend / gemischt), aus dem sich die passende Strategiefamilie
ergibt. Wichtigste Kennzahl ist die **Kostenhürde**: Rundlaufkosten geteilt
durch die typische Tagesbewegung. Sie ist bei einem Retail-Bot meist die
bindende Grenze — nicht die Signalqualität.

### Realitätsprüfung (`check`)

Fünf unabhängige Angriffe auf das Backtest-Ergebnis: Kostensensitivität mit
Break-Even-Kosten, Monte-Carlo-Permutationstest (zerstört die Ausrichtung
zwischen Signal und Kurs bei gleicher Exposition), Deflated Sharpe Ratio
(korrigiert für die Anzahl der Versuche), Parameter-Plateau statt Zufallsspitze
und zeitliche Stabilität. Ergebnis ist ein Urteil mit begründeten
Einzelkriterien. Bei **NO-GO verweigert der Bot die Ausgabe von Orders** —
`check --save` schreibt das Protokoll, das die Freigabe steuert.

### Risikomanagement (`--risk`)

Verfügbar bei `check`, `portfolio` und im Bot. Drei Bausteine: Positionsgröße
nach Volatilitäts-Ziel (Default 15 % p. a.), ATR-Stop-Loss (Default 3×ATR) und
Notabschaltung bei Depot-Drawdown (Default 20 %, danach 20 Tage Pause).
Alles streng kausal — jede Entscheidung an Tag *t* nutzt nur Daten bis *t*.

### Portfolio (`portfolio`)

Backtest über mehrere Werte mit Risikoparität (inverse Volatilität) und
Gewichtsobergrenze je Wert. Gibt den gemessenen Diversifikationseffekt und die
Korrelationsmatrix aus — damit sichtbar wird, ob wirklich gestreut wurde. Fünf
unkorrelierte Werte senken die Schwankung um etwa 55 %, fünf Werte desselben
Marktes mit Korrelation 0,8 nur um 8 %.

### Bot (`bot`)

Berechnet aus dem Signal des letzten abgeschlossenen Handelstags die
Zielpositionen über das Universum, wendet Risiko- und Portfolioregeln an und
stellt sie dem Ist-Bestand gegenüber. Ergebnis ist eine Orderliste zur
**manuellen** Ausführung.

Es gibt bewusst keine Broker-Anbindung. Ein Programm mit Zugriff auf ein echtes
Depot kann bei einem Datenfehler, einem falschen Vorzeichen oder einem
Kursfeed, der einen Aktiensplit als 90-%-Absturz meldet, in Minuten verlieren,
was in Monaten verdient wurde. Bei Haltedauern von Wochen kostet manuelle
Ausführung praktisch keine Rendite und verhindert genau diese Unfälle.

## Mitgelieferte Strategien

| Name                 | Idee                                                        | Parameter |
|----------------------|-------------------------------------------------------------|-----------|
| `sma_cross`          | Trendfolge: schneller SMA über langsamem SMA → long         | `fast`, `slow`, `allow_short` |
| `rsi_reversion`      | Mean Reversion: Kauf bei überverkauftem RSI, mit Trendfilter | `window`, `oversold`, `exit_level`, `trend_window` |
| `momentum`           | Zeitreihen-Momentum über ein Lookback-Fenster               | `lookback`, `threshold`, `allow_short` |
| `bollinger_breakout` | Ausbruch über das obere Bollinger-Band                      | `window`, `num_std` |
| `buy_hold`           | Benchmark: durchgehend investiert                           | – |

## Eigene Strategie entwickeln

Eine Strategie ist eine Klasse, die aus OHLCV-Daten eine Zielpositions-Serie erzeugt (`+1` = long, `0` = flat, `-1` = short). Ausführung am Folgetag und Kosten übernimmt der Backtester.

```python
import pandas as pd
from strategylab.strategy import Strategy, register_strategy
from strategylab.indicators import ema

@register_strategy
class MeineStrategie(Strategy):
    name = "meine_strategie"
    params = {"window": 50}

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        trend = ema(df["Close"], int(self.p["window"]))
        position = (df["Close"] > trend).astype(float)
        position[trend.isna()] = 0.0
        return position
```

Datei in `strategylab/strategies/` ablegen und in `strategylab/strategies/__init__.py` importieren — danach ist sie in CLI und API unter ihrem Namen verfügbar.

Nutzung als Bibliothek:

```python
from strategylab import Backtester, get_strategy
from strategylab.data import load_csv

df = load_csv("data/demo.csv")
result = Backtester(commission=0.001).run(get_strategy("sma_cross", fast=20, slow=50), df)
print(result.summary_text())
print(result.trades.tail())
```

## Wie das Tool die "Anwendung in der Zukunft" prüft

Ein guter Backtest allein sagt wenig — optimierte Parameter passen sich an die Vergangenheit an (Overfitting). StrategyLab bietet dafür zwei Schutzstufen:

1. **Walk-Forward-Analyse** (`walkforward`): Parameter werden rollierend nur auf einem Trainingsfenster optimiert und dann auf dem *folgenden, ungesehenen* Zeitraum getestet. Das verkettete Out-of-Sample-Ergebnis simuliert, wie es gewesen wäre, die Strategie real zu handeln. Ist es deutlich schwächer als der In-Sample-Backtest, ist die Strategie überangepasst.

2. **Papertrading / Forward-Test** (`paper`): Ab einem Stichtag wird die Strategie auf *echten neuen Daten* simuliert weitergeführt (Zustand in einer JSON-Datei, Update per `paper update` mit frischen Kursen). So entsteht über Wochen/Monate ein ehrlicher Track-Record, bevor echtes Geld im Spiel ist.

## Ausführungsmodell des Backtesters

- Signal von Tag *t* wird zum Schlusskurs von Tag *t* ausgeführt, Renditen laufen ab Tag *t+1* auf → **kein Look-Ahead-Bias**: Die Rendite des Signaltags wird nie mitgenommen (per Test abgesichert).
- Kosten: `commission` + `slippage` als Anteil des gehandelten Volumens bei jeder Positionsänderung (Default 0,1 % + 0,05 %).
- Kennzahlen: Gesamtrendite, CAGR, Volatilität, Sharpe, Sortino, Max Drawdown, Calmar, Exposure, Trefferquote, Profit-Faktor, Ø Haltedauer u. a. — immer im Vergleich zu Buy & Hold.

## Tests

```bash
python -m pytest tests/ -v
```

## Wichtiger Hinweis

Dieses Tool dient der Analyse und Ausbildung. Es ist **keine Anlageberatung**. Backtest-Ergebnisse — auch walk-forward-validierte — garantieren keine zukünftigen Renditen.

Auch ein GO der Realitätsprüfung bedeutet nur: Der gemessene Vorteil lässt sich
statistisch nicht als Zufall erklären. Nicht, dass er in der Zukunft anhält.
Was das Werkzeug ausdrücklich **nicht** kann, steht in
[REGELN.md, Teil 6](REGELN.md) — dazu gehören fehlende Intraday-Absicherung,
Survivorship Bias in den Kursdaten und die steuerliche Belastung häufigen
Handelns.
