"""Der Bot: aus geprüfter Strategie werden konkrete Orders.

Dieses Modul verbindet alles: Es liest eine Konfiguration, berechnet für den
aktuellen Tag die Zielpositionen über das gesamte Universum, wendet Risiko- und
Portfolioregeln an und stellt den Ist-Beständen gegenüber, was gekauft oder
verkauft werden müsste.

## Bewusst keine automatische Ausführung

Der Bot platziert keine Orders. Es gibt keine Broker-Anbindung, und das ist eine
Entscheidung, keine fehlende Funktion. Ein Programm mit Zugriff auf ein echtes
Depot kann bei einem Fehler in Minuten Geld verlieren, das in Monaten verdient
wurde — durch einen Datenfehler, ein Vorzeichen an der falschen Stelle, einen
doppelt ausgeführten Auftrag oder einen Kursfeed, der einen Aktiensplit als
90-%-Absturz meldet. Solange kein monatelanger Papertrading-Track-Record
existiert und die Order-Logik nicht in Ruhe gegen echte Depotauszüge geprüft
wurde, ist manuelle Ausführung die richtige Betriebsart: Der Bot rechnet, ein
Mensch entscheidet und tippt. Das kostet bei einer Strategie mit Haltedauern von
Wochen praktisch nichts an Rendite und verhindert die teuren Unfälle.

## Sicherheitssperre

Der Bot gibt keine Orders aus, solange kein Prüfprotokoll (`strategylab check
--save`) vorliegt, das die Strategie freigegeben hat. Bei einem NO-GO verweigert
er die Ausgabe. Das ist die technische Umsetzung der Reihenfolge "erst prüfen,
dann Geld" — damit die Sperre nicht in einem schwachen Moment übersprungen wird.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from strategylab.data import load_csv
from strategylab.portfolio import PortfolioConfig, _weights
from strategylab.risk import RiskConfig, RiskManager
from strategylab.strategy import get_strategy


@dataclass
class BotConfig:
    """Vollständige Beschreibung eines Bots."""

    name: str = "mein_bot"
    universe: dict[str, str] = field(default_factory=dict)
    """{Symbol: Pfad zur OHLCV-CSV}."""

    strategy: str = "sma_cross"
    params: dict = field(default_factory=dict)
    """Parameter für alle Werte, oder {Symbol: {Parameter}} je Wert."""

    capital: float = 10_000.0
    commission: float = 0.001
    slippage: float = 0.0005

    min_order_value: float = 250.0
    """Orders unter diesem Gegenwert werden verworfen. Bei 5 € Gebühr sind
    250 € Ordervolumen bereits 2 % Kosten — kleinere Orders lohnen nie."""

    risk: dict = field(default_factory=lambda: asdict(RiskConfig()))
    portfolio: dict = field(default_factory=lambda: asdict(PortfolioConfig()))

    check_file: str | None = None
    """Pfad zum Prüfprotokoll aus 'strategylab check --save'. Ohne Freigabe
    gibt der Bot keine Orders aus."""

    @classmethod
    def load(cls, path: str | Path) -> "BotConfig":
        raw = json.loads(Path(path).read_text())
        unknown = set(raw) - {f for f in cls.__dataclass_fields__}
        if unknown:
            raise ValueError(f"Unbekannte Felder in der Konfiguration: {sorted(unknown)}")
        return cls(**raw)

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False))

    def risk_config(self) -> RiskConfig:
        return RiskConfig(**self.risk)

    def portfolio_config(self) -> PortfolioConfig:
        return PortfolioConfig(**self.portfolio)

    def params_for(self, symbol: str) -> dict:
        if self.params and all(isinstance(v, dict) for v in self.params.values()):
            return dict(self.params.get(symbol, {}))
        return dict(self.params)

    def cost_per_turnover(self) -> float:
        return self.commission + self.slippage


def template_config(name: str = "mein_bot") -> BotConfig:
    """Beispielkonfiguration zum Ausfüllen."""
    return BotConfig(
        name=name,
        universe={"aapl.us": "data/aapl.csv", "sap.de": "data/sap.csv"},
        strategy="sma_cross",
        params={"fast": 20, "slow": 100},
        check_file=f"checks/{name}.json",
    )


def load_universe(config: BotConfig) -> dict[str, pd.DataFrame]:
    """Lädt alle Kursdateien des Universums."""
    if not config.universe:
        raise ValueError("Das Universum ist leer — mindestens ein Wert nötig")
    data = {}
    for symbol, path in config.universe.items():
        if not Path(path).exists():
            raise FileNotFoundError(
                f"Kursdatei für '{symbol}' fehlt: {path}\n"
                f"Mit 'strategylab data fetch --symbol {symbol} --out {path}' laden."
            )
        data[symbol] = load_csv(path)
    return data


@dataclass
class Approval:
    """Ergebnis der Freigabeprüfung."""

    allowed: bool
    verdict: str
    reason: str


def check_approval(config: BotConfig) -> Approval:
    """Prüft, ob ein Prüfprotokoll die Strategie freigibt."""
    if not config.check_file:
        return Approval(
            False, "FEHLT",
            "Kein Prüfprotokoll in der Konfiguration hinterlegt ('check_file'). "
            "Zuerst 'strategylab check ... --save <datei>' laufen lassen.",
        )
    path = Path(config.check_file)
    if not path.exists():
        return Approval(
            False, "FEHLT",
            f"Prüfprotokoll {path} existiert nicht. Zuerst "
            f"'strategylab check ... --save {path}' laufen lassen.",
        )
    record = json.loads(path.read_text())
    verdict = record.get("verdict", "UNBEKANNT")
    if verdict == "NO-GO":
        failed = [c["name"] for c in record.get("criteria", []) if c["hard"] and not c["passed"]]
        return Approval(
            False, verdict,
            "Die Realitätsprüfung hat die Strategie abgelehnt. Gerissene "
            f"K.-o.-Kriterien: {', '.join(failed) or 'unbekannt'}. "
            "Diese Strategie gehört nicht an echtes Geld.",
        )
    if record.get("strategy") != config.strategy:
        return Approval(
            False, verdict,
            f"Das Protokoll gilt für Strategie '{record.get('strategy')}', "
            f"die Konfiguration nutzt '{config.strategy}'. Erneut prüfen.",
        )
    if verdict == "VORSICHT":
        return Approval(
            True, verdict,
            "Bedingte Freigabe: alle K.-o.-Kriterien bestanden, weiche Kriterien "
            "gerissen. Nur für Papertrading, nicht für echtes Geld.",
        )
    return Approval(True, verdict, "Die Realitätsprüfung hat die Strategie freigegeben.")


def compute_targets(config: BotConfig, data: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    """Berechnet die Zielpositionen für den letzten verfügbaren Handelstag.

    Wichtig: Es wird das Signal des **letzten abgeschlossenen** Tages verwendet.
    Das entspricht genau dem Ausführungsmodell des Backtesters (Signal von Tag t
    wird ab t+1 gehalten) — der Bot handelt also nie auf einem Kurs, den er im
    Backtest noch nicht kennen konnte.
    """
    data = data if data is not None else load_universe(config)
    risk_cfg = config.risk_config()
    pf_cfg = config.portfolio_config()
    pf_cfg.validate()
    cost = config.cost_per_turnover()

    index = None
    for df in data.values():
        index = df.index if index is None else index.union(df.index)

    positions, asset_returns, last_prices, last_dates = {}, {}, {}, {}
    for symbol, df in data.items():
        strategy = get_strategy(config.strategy, **config.params_for(symbol))
        target = strategy.generate_signals(df).astype(float).reindex(df.index).fillna(0.0)
        target = RiskManager(risk_cfg).apply(df, target, cost).positions
        target = target.clip(-risk_cfg.max_leverage, risk_cfg.max_leverage)
        positions[symbol] = target.reindex(index).fillna(0.0)
        asset_returns[symbol] = df["Close"].pct_change().fillna(0.0).reindex(index).fillna(0.0)
        last_prices[symbol] = float(df["Close"].iloc[-1])
        last_dates[symbol] = df.index[-1].date().isoformat()

    pos_df = pd.DataFrame(positions).reindex(index).fillna(0.0)
    ret_df = pd.DataFrame(asset_returns).reindex(index).fillna(0.0)
    weights = _weights(pos_df, ret_df, pf_cfg)
    allocations = (weights * pos_df).iloc[-1]

    rows = []
    for symbol in data:
        alloc = float(allocations.get(symbol, 0.0))
        price = last_prices[symbol]
        value = config.capital * alloc
        rows.append(
            {
                "symbol": symbol,
                "signal": float(pos_df[symbol].iloc[-1]),
                "zielanteil": round(alloc, 4),
                "zielwert": round(value, 2),
                "kurs": round(price, 4),
                "zielstueck": int(abs(value) // price) * (1 if value >= 0 else -1),
                "kursdatum": last_dates[symbol],
            }
        )
    return pd.DataFrame(rows).sort_values("symbol").reset_index(drop=True)


def load_holdings(path: str | Path | None) -> dict[str, float]:
    """Lädt die Ist-Bestände als {Symbol: Stückzahl}.

    Fehlt die Datei, wird ein leeres Depot angenommen — der erste Lauf erzeugt
    dann Kauforders für alle Zielpositionen.
    """
    if path is None or not Path(path).exists():
        return {}
    raw = json.loads(Path(path).read_text())
    holdings = raw.get("holdings", raw)
    return {str(k): float(v) for k, v in holdings.items()}


def save_holdings(path: str | Path, holdings: dict[str, float]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {"updated": date.today().isoformat(), "holdings": holdings},
            indent=2, ensure_ascii=False,
        )
    )


def generate_orders(
    targets: pd.DataFrame, holdings: dict[str, float], min_order_value: float = 250.0
) -> pd.DataFrame:
    """Vergleicht Ziel- und Ist-Bestand und leitet Orders ab.

    Orders unter `min_order_value` werden verworfen: Bei kleinen Beträgen
    übersteigen Gebühren und Spread den Nutzen der genaueren Gewichtung. Die
    Position weicht dann vorübergehend leicht vom Ziel ab — das ist billiger,
    als jede Nachkommastelle nachzukaufen.
    """
    rows = []
    symbols = sorted(set(targets["symbol"]) | set(holdings))
    by_symbol = targets.set_index("symbol")

    for symbol in symbols:
        target_shares = int(by_symbol.loc[symbol, "zielstueck"]) if symbol in by_symbol.index else 0
        price = float(by_symbol.loc[symbol, "kurs"]) if symbol in by_symbol.index else 0.0
        current = holdings.get(symbol, 0.0)
        delta = target_shares - current
        if delta == 0:
            continue
        value = abs(delta) * price
        if price <= 0:
            rows.append(
                {
                    "symbol": symbol, "aktion": "PRUEFEN", "stueck": abs(delta),
                    "kurs": price, "gegenwert": 0.0,
                    "hinweis": "Kein aktueller Kurs — Position manuell prüfen",
                }
            )
            continue
        if value < min_order_value and target_shares != 0:
            rows.append(
                {
                    "symbol": symbol, "aktion": "HALTEN", "stueck": abs(delta),
                    "kurs": round(price, 4), "gegenwert": round(value, 2),
                    "hinweis": f"Anpassung unter Mindestordergröße ({min_order_value:.0f})",
                }
            )
            continue
        rows.append(
            {
                "symbol": symbol,
                "aktion": "KAUFEN" if delta > 0 else "VERKAUFEN",
                "stueck": abs(delta),
                "kurs": round(price, 4),
                "gegenwert": round(value, 2),
                "hinweis": "Zielposition schließen" if target_shares == 0 else "",
            }
        )
    columns = ["symbol", "aktion", "stueck", "kurs", "gegenwert", "hinweis"]
    return pd.DataFrame(rows, columns=columns)


def orders_text(
    config: BotConfig, targets: pd.DataFrame, orders: pd.DataFrame, approval: Approval
) -> str:
    """Menschenlesbarer Tagesbericht des Bots."""
    actionable = orders[orders["aktion"].isin(["KAUFEN", "VERKAUFEN"])]
    invested = float(targets["zielwert"].abs().sum())
    lines = [
        f"Bot: {config.name}   Strategie: {config.strategy}",
        f"Kapital: {config.capital:,.2f}   Freigabe: {approval.verdict}",
        "",
        "Zielpositionen (Signal des letzten abgeschlossenen Handelstags):",
        targets.to_string(index=False),
        "",
        f"Investiert: {invested:,.2f} von {config.capital:,.2f} "
        f"({invested / config.capital:.1%}), Rest bleibt Kasse.",
        "",
    ]
    if orders.empty:
        lines.append("Keine Orders nötig — Depot entspricht den Zielpositionen.")
    else:
        lines.append("Orders:")
        lines.append(orders.to_string(index=False))
        lines.append("")
        lines.append(
            f"{len(actionable)} Order(s) auszuführen, Gesamtvolumen "
            f"{float(actionable['gegenwert'].sum()):,.2f}."
        )
    lines += [
        "",
        "Diese Orders sind ein Vorschlag zur manuellen Ausführung. Der Bot hat "
        "keine\nVerbindung zu einem Depot und platziert nichts selbst.",
    ]
    if approval.verdict == "VORSICHT":
        lines.append("")
        lines.append(f"Achtung: {approval.reason}")
    return "\n".join(lines)


def run_bot(
    config: BotConfig,
    holdings_file: str | Path | None = None,
    require_approval: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, Approval]:
    """Berechnet Zielpositionen und Orders für heute.

    `require_approval=False` überspringt die Sicherheitssperre — ausschließlich
    für Tests und Trockenläufe gedacht, nicht für den Betrieb mit echtem Geld.
    """
    approval = check_approval(config)
    if require_approval and not approval.allowed:
        raise PermissionError(
            f"Bot gesperrt ({approval.verdict}): {approval.reason}\n\n"
            "Die Sperre ist Absicht. Eine Strategie ohne bestandene "
            "Realitätsprüfung\nzu handeln ist der schnellste Weg, Geld zu verlieren."
        )
    data = load_universe(config)
    targets = compute_targets(config, data)
    orders = generate_orders(targets, load_holdings(holdings_file), config.min_order_value)
    return targets, orders, approval
