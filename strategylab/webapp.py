"""Grafische Web-Oberfläche für StrategyLab.

Startet einen lokalen Webserver (nur Python-Standardbibliothek, keine
zusätzlichen Abhängigkeiten) und öffnet die Oberfläche im Browser. Dort lassen
sich Daten laden, Backtests rechnen, Parameter optimieren und Walk-Forward-
Analysen durchführen — komplett per Mausklick.

Aufruf:  strategylab gui
"""

from __future__ import annotations

import io
import json
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files

import numpy as np
import pandas as pd

from strategylab import data as data_mod
from strategylab.backtest import Backtester
from strategylab.strategy import get_strategy, list_strategies
from strategylab.walkforward import optimize, walk_forward

# Aktueller Datensatz, geteilt über alle Anfragen (lokale Einzelnutzer-App).
_STATE: dict = {"df": None, "source": None}

MAX_CHART_POINTS = 500


def _load_index_html() -> str:
    return (files("strategylab") / "web" / "index.html").read_text(encoding="utf-8")


def _downsample(series: pd.Series, n: int = MAX_CHART_POINTS) -> pd.Series:
    """Reduziert eine Serie auf höchstens n Punkte (letzter Punkt bleibt erhalten)."""
    if len(series) <= n:
        return series
    idx = np.linspace(0, len(series) - 1, n).round().astype(int)
    idx = np.unique(np.append(idx, len(series) - 1))
    return series.iloc[idx]


def _series_payload(*named_series: tuple[str, pd.Series]) -> dict:
    """Baut ein JSON-fähiges Chart-Paket aus gemeinsam indizierten Serien."""
    reference = named_series[0][1]
    ds_index = _downsample(reference).index
    dates = [d.strftime("%Y-%m-%d") for d in ds_index]
    payload = {"dates": dates}
    for name, series in named_series:
        values = series.reindex(ds_index)
        payload[name] = [round(float(v), 4) if pd.notna(v) else None for v in values]
    return payload


def _require_df() -> pd.DataFrame:
    if _STATE["df"] is None:
        raise ValueError("Es sind noch keine Kursdaten geladen. Bitte zuerst Daten laden.")
    return _STATE["df"]


def _dataset_info() -> dict:
    df = _STATE["df"]
    if df is None:
        return {"loaded": False}
    price = _downsample(df["Close"])
    return {
        "loaded": True,
        "source": _STATE["source"],
        "rows": int(len(df)),
        "start": df.index[0].strftime("%Y-%m-%d"),
        "end": df.index[-1].strftime("%Y-%m-%d"),
        "preview": {
            "dates": [d.strftime("%Y-%m-%d") for d in price.index],
            "close": [round(float(v), 4) for v in price.values],
        },
    }


# --- API-Handler ----------------------------------------------------------

def api_strategies() -> dict:
    strategies = []
    for name, cls in list_strategies():
        fields = []
        for key, default in cls.params.items():
            if isinstance(default, bool):
                ftype = "bool"
            elif isinstance(default, int):
                ftype = "int"
            elif isinstance(default, float):
                ftype = "float"
            else:
                ftype = "text"
            fields.append({"name": key, "default": default, "type": ftype})
        strategies.append({"name": name, "doc": (cls.__doc__ or "").strip().split("\n")[0], "params": fields})
    return {"strategies": strategies}


def api_generate(body: dict) -> dict:
    days = int(body.get("days", 1500))
    seed = int(body.get("seed", 42))
    df = data_mod.generate_synthetic(days=days, seed=seed)
    _STATE["df"] = df
    _STATE["source"] = f"Synthetische Daten ({days} Tage, Seed {seed})"
    return _dataset_info()


def api_fetch(body: dict) -> dict:
    symbol = str(body.get("symbol", "")).strip()
    if not symbol:
        raise ValueError("Bitte ein Symbol angeben, z. B. aapl.us oder sap.de")
    df = data_mod.fetch_stooq(symbol)
    _STATE["df"] = df
    _STATE["source"] = f"Stooq: {symbol} ({len(df)} Tage)"
    return _dataset_info()


def api_upload(body: dict) -> dict:
    content = body.get("content", "")
    filename = body.get("filename", "upload.csv")
    if not content:
        raise ValueError("Die Datei ist leer.")
    df = data_mod.load_csv(io.StringIO(content))
    _STATE["df"] = df
    _STATE["source"] = f"Datei: {filename} ({len(df)} Tage)"
    return _dataset_info()


def api_dataset(_body: dict | None = None) -> dict:
    return _dataset_info()


def _backtester(body: dict) -> Backtester:
    return Backtester(
        initial_capital=float(body.get("capital", 10_000)),
        commission=float(body.get("commission", 0.001)),
        slippage=float(body.get("slippage", 0.0005)),
    )


def api_backtest(body: dict) -> dict:
    df = _require_df()
    strategy = get_strategy(body["strategy"], **body.get("params", {}))
    result = _backtester(body).run(strategy, df)

    drawdown = (result.equity / result.equity.cummax() - 1.0) * 100.0
    charts = _series_payload(
        ("equity", result.equity),
        ("benchmark", result.benchmark_equity),
    )
    charts_dd = _series_payload(("drawdown", drawdown))

    trades = result.trades.tail(30).copy()
    trade_rows = []
    for _, t in trades.iterrows():
        trade_rows.append({
            "entry_date": str(t["entry_date"])[:10],
            "exit_date": str(t["exit_date"])[:10],
            "side": t["side"],
            "entry_price": round(float(t["entry_price"]), 2),
            "exit_price": round(float(t["exit_price"]), 2),
            "ret": round(float(t["return"]) * 100, 2),
            "holding_days": int(t["holding_days"]),
            "open": bool(t["open"]),
        })

    return {
        "stats": _clean(result.stats),
        "params": _clean(result.params),
        "equity_chart": charts,
        "drawdown_chart": charts_dd,
        "trades": trade_rows,
    }


def api_optimize(body: dict) -> dict:
    df = _require_df()
    grid = {k: list(v) for k, v in body["grid"].items()}
    metric = body.get("metric", "sharpe")
    result = optimize(body["strategy"], df, grid, backtester=_backtester(body), metric=metric)
    return {
        "best_params": _clean(result.best_params),
        "ranking": [_clean(r) for r in result.ranking.to_dict(orient="records")],
        "columns": list(result.ranking.columns),
    }


def api_walkforward(body: dict) -> dict:
    df = _require_df()
    grid = {k: list(v) for k, v in body["grid"].items()}
    result = walk_forward(
        body["strategy"], df, grid,
        train_size=int(body.get("train", 500)),
        test_size=int(body.get("test", 125)),
        backtester=_backtester(body),
        metric=body.get("metric", "sharpe"),
    )
    windows = [_clean(r) for r in result.windows.to_dict(orient="records")]
    oos_equity = _series_payload(("equity", result.oos_equity))
    positive = int((result.windows["oos_return"] > 0).sum())
    return {
        "windows": windows,
        "columns": [str(c) for c in result.windows.columns],
        "oos_stats": _clean(result.oos_stats),
        "oos_equity_chart": oos_equity,
        "positive_windows": positive,
        "total_windows": int(len(result.windows)),
    }


def _clean(obj):
    """Macht Werte JSON-serialisierbar (inf -> None, numpy -> python, Datum -> str)."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if (np.isinf(f) or np.isnan(f)) else round(f, 6)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()[:10]
    return obj


_POST_ROUTES = {
    "/api/generate": api_generate,
    "/api/fetch": api_fetch,
    "/api/upload": api_upload,
    "/api/dataset": api_dataset,
    "/api/backtest": api_backtest,
    "/api/optimize": api_optimize,
    "/api/walkforward": api_walkforward,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D401 - Konsole ruhig halten
        pass

    def _json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            html = _load_index_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        elif self.path == "/api/strategies":
            self._json(api_strategies())
        else:
            self._json({"error": "Nicht gefunden"}, status=404)

    def do_POST(self) -> None:
        handler = _POST_ROUTES.get(self.path)
        if handler is None:
            self._json({"error": "Nicht gefunden"}, status=404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw or b"{}")
            self._json(handler(body))
        except (ValueError, KeyError) as exc:
            self._json({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001 - dem Nutzer eine Meldung geben
            self._json({"error": f"Unerwarteter Fehler: {exc}"}, status=500)


def _lan_ip() -> str | None:
    """Ermittelt die IP-Adresse im lokalen Netz (für den Zugriff vom Handy)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Verbindet nichts wirklich, verrät aber die eigene LAN-Adresse.
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    return None


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """Startet den Webserver und öffnet optional den Browser.

    host="0.0.0.0" macht die Oberfläche auch für andere Geräte im selben
    WLAN erreichbar (z. B. Handy/Tablet).
    """
    server = None
    for candidate in range(port, port + 20):
        try:
            server = ThreadingHTTPServer((host, candidate), Handler)
            port = candidate
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError(f"Kein freier Port im Bereich {port}-{port + 20} gefunden")

    local_url = f"http://127.0.0.1:{port}/"
    lan_exposed = host not in ("127.0.0.1", "localhost")
    print(f"StrategyLab-Oberfläche läuft auf {local_url}")
    if lan_exposed:
        ip = _lan_ip()
        if ip:
            print("\n  Auf dem Handy/Tablet im selben WLAN diese Adresse im Browser öffnen:")
            print(f"      http://{ip}:{port}/\n")
        else:
            print("  (LAN-Adresse konnte nicht ermittelt werden — bitte die IP des Rechners verwenden.)")
        print("  Hinweis: Im Handy-Modus ist die Oberfläche für alle Geräte im")
        print("  Netzwerk erreichbar. Nur in vertrauenswürdigen WLANs verwenden.")
    print("\nZum Beenden Strg+C drücken.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(local_url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nOberfläche beendet.")
    finally:
        server.server_close()
