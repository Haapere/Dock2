# StrategyLab

Ein Python-Werkzeug, um Trading-Strategien zu **entwickeln**, auf historischen Daten zu **backtesten** und ihre **Zukunftstauglichkeit zu prüfen** (Walk-Forward-Analyse und Papertrading/Forward-Test).

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
