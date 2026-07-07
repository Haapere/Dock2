"""Datenbeschaffung: CSV-Import, Stooq-Download und synthetische Kursdaten."""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def load_csv(path: str | Path) -> pd.DataFrame:
    """Lädt eine OHLCV-CSV-Datei mit Datumsindex.

    Erwartet mindestens eine Date- und eine Close-Spalte; fehlende
    OHLC-Spalten werden aus Close ergänzt, damit auch reine
    Schlusskurs-Reihen nutzbar sind.
    """
    df = pd.read_csv(path)
    date_col = None
    for candidate in ("Date", "date", "Datum", "timestamp", "Timestamp"):
        if candidate in df.columns:
            date_col = candidate
            break
    if date_col is None:
        raise ValueError(f"Keine Datumsspalte in {path} gefunden (erwartet z.B. 'Date')")

    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col).sort_index()
    df.index.name = "Date"

    rename = {c: c.capitalize() for c in df.columns}
    df = df.rename(columns=rename)
    if "Close" not in df.columns:
        raise ValueError(f"Keine 'Close'-Spalte in {path} gefunden")

    for col in ("Open", "High", "Low"):
        if col not in df.columns:
            df[col] = df["Close"]
    if "Volume" not in df.columns:
        df["Volume"] = 0.0

    df = df[OHLCV_COLUMNS].astype(float)
    df = df[~df.index.duplicated(keep="last")]
    df = df.dropna(subset=["Close"])
    if df.empty:
        raise ValueError(f"{path} enthält keine verwertbaren Kursdaten")
    return df


def fetch_stooq(symbol: str, timeout: int = 30) -> pd.DataFrame:
    """Lädt Tagesdaten von stooq.com (kostenlos, ohne API-Key).

    Symbolformat: 'aapl.us', 'sap.de', '^spx' usw.
    """
    url = f"https://stooq.com/q/d/l/?s={symbol.lower()}&i=d"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    if not raw or raw.strip() in ("No data", "Exceeded the daily hits limit"):
        raise ValueError(f"Stooq lieferte keine Daten für '{symbol}': {raw.strip()!r}")
    df = pd.read_csv(io.StringIO(raw))
    if "Close" not in df.columns or df.empty:
        raise ValueError(f"Unerwartete Antwort von Stooq für '{symbol}'")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    if "Volume" not in df.columns:
        df["Volume"] = 0.0
    return df[OHLCV_COLUMNS].astype(float)


def generate_synthetic(
    days: int = 1500,
    start_price: float = 100.0,
    annual_drift: float = 0.07,
    annual_vol: float = 0.20,
    seed: int | None = 42,
    start: str = "2020-01-01",
) -> pd.DataFrame:
    """Erzeugt synthetische OHLCV-Daten (GBM mit Regime-Wechseln).

    Nützlich, um Strategien und die Pipeline ohne Internetzugang zu testen.
    Die Regime-Wechsel (Trend-, Seitwärts- und Stressphasen) machen die
    Reihe realistischer als reines Rauschen.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start, periods=days)

    # Regime: Blöcke von 60-250 Tagen mit eigenem Drift/Vol-Multiplikator
    drift = np.empty(days)
    vol = np.empty(days)
    i = 0
    while i < days:
        block = int(rng.integers(60, 250))
        regime = rng.choice(["bull", "bear", "chop"], p=[0.45, 0.2, 0.35])
        if regime == "bull":
            d_mult, v_mult = 2.0, 0.8
        elif regime == "bear":
            d_mult, v_mult = -2.0, 1.6
        else:
            d_mult, v_mult = 0.0, 1.0
        drift[i : i + block] = annual_drift * d_mult
        vol[i : i + block] = annual_vol * v_mult
        i += block

    dt = 1.0 / 252.0
    log_returns = (drift - 0.5 * vol**2) * dt + vol * np.sqrt(dt) * rng.standard_normal(days)
    close = start_price * np.exp(np.cumsum(log_returns))

    prev_close = np.concatenate([[start_price], close[:-1]])
    gap = rng.normal(0, 0.2, days) * vol * np.sqrt(dt)
    open_ = prev_close * np.exp(gap)
    intraday = np.abs(rng.normal(0, 1.0, days)) * vol * np.sqrt(dt)
    high = np.maximum(open_, close) * np.exp(intraday * 0.5)
    low = np.minimum(open_, close) * np.exp(-intraday * 0.5)
    volume = rng.lognormal(mean=13, sigma=0.4, size=days).round()

    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=dates,
    ).rename_axis("Date")


def save_csv(df: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index_label="Date")
