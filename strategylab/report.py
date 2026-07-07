"""HTML-Report mit Equity-Kurve und Drawdown als eigenständige Datei (inline SVG)."""

from __future__ import annotations

import html
from pathlib import Path

import pandas as pd

from strategylab.backtest import BacktestResult


def _svg_line_chart(
    series_list: list[tuple[str, pd.Series, str]],
    width: int = 900,
    height: int = 320,
    fill_first: bool = False,
) -> str:
    """Zeichnet Zeitreihen als SVG-Liniendiagramm (keine externen Abhängigkeiten)."""
    pad_left, pad_right, pad_top, pad_bottom = 70, 20, 20, 40
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    all_values = pd.concat([s for _, s, _ in series_list])
    y_min, y_max = float(all_values.min()), float(all_values.max())
    if y_max == y_min:
        y_max = y_min + 1.0
    y_span = y_max - y_min
    y_min -= y_span * 0.05
    y_max += y_span * 0.05
    y_span = y_max - y_min

    index = series_list[0][1].index
    n = len(index)

    def x_pos(i: int) -> float:
        return pad_left + (i / max(n - 1, 1)) * plot_w

    def y_pos(v: float) -> float:
        return pad_top + (1.0 - (v - y_min) / y_span) * plot_h

    parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'style="max-width:100%;height:auto;font-family:sans-serif">'
    ]

    # Horizontale Gitterlinien + Y-Beschriftung
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        value = y_min + frac * y_span
        y = y_pos(value)
        parts.append(
            f'<line x1="{pad_left}" y1="{y:.1f}" x2="{width - pad_right}" y2="{y:.1f}" '
            f'stroke="#ddd" stroke-width="1"/>'
            f'<text x="{pad_left - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="#666">{value:,.0f}</text>'
        )

    # X-Beschriftung: 5 Datumsmarken
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        i = int(frac * (n - 1))
        x = x_pos(i)
        label = index[i].strftime("%Y-%m-%d")
        parts.append(
            f'<text x="{x:.1f}" y="{height - 12}" text-anchor="middle" '
            f'font-size="11" fill="#666">{label}</text>'
        )

    for idx, (label, series, color) in enumerate(series_list):
        pts = " ".join(
            f"{x_pos(i):.1f},{y_pos(float(v)):.1f}" for i, v in enumerate(series.to_numpy())
        )
        if fill_first and idx == 0:
            base_y = y_pos(min(0.0, y_max))
            first_x, last_x = x_pos(0), x_pos(n - 1)
            parts.append(
                f'<polygon points="{first_x:.1f},{base_y:.1f} {pts} {last_x:.1f},{base_y:.1f}" '
                f'fill="{color}" opacity="0.25"/>'
            )
        parts.append(
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.8"/>'
        )
        # Legende
        lx = pad_left + 10 + idx * 180
        parts.append(
            f'<rect x="{lx}" y="{pad_top}" width="12" height="12" fill="{color}"/>'
            f'<text x="{lx + 18}" y="{pad_top + 10}" font-size="12" fill="#333">{html.escape(label)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def _fmt(value, kind: str = "num") -> str:
    if value == float("inf"):
        return "&infin;"
    if kind == "pct":
        return f"{value:+.2%}"
    if kind == "pct0":
        return f"{value:.1%}"
    if kind == "int":
        return f"{int(value)}"
    return f"{value:.2f}"


def render_html(result: BacktestResult, title: str | None = None) -> str:
    s = result.stats
    title = title or f"Backtest: {result.strategy_name}"

    equity_chart = _svg_line_chart(
        [
            ("Strategie", result.equity, "#1f6feb"),
            ("Buy & Hold", result.benchmark_equity, "#999999"),
        ]
    )
    drawdown = (result.equity / result.equity.cummax() - 1.0) * 100.0
    dd_chart = _svg_line_chart([("Drawdown %", drawdown, "#d1242f")], height=220, fill_first=True)

    rows = [
        ("Gesamtrendite", _fmt(s["total_return"], "pct")),
        ("Buy &amp; Hold Rendite", _fmt(s["benchmark_return"], "pct")),
        ("CAGR", _fmt(s["cagr"], "pct")),
        ("Volatilität p.a.", _fmt(s["annual_volatility"], "pct0")),
        ("Sharpe Ratio", _fmt(s["sharpe"])),
        ("Sortino Ratio", _fmt(s["sortino"])),
        ("Max. Drawdown", _fmt(s["max_drawdown"], "pct")),
        ("Calmar Ratio", _fmt(s["calmar"])),
        ("Marktexposition", _fmt(s["exposure"], "pct0")),
        ("Anzahl Trades", _fmt(s["num_trades"], "int")),
        ("Trefferquote", _fmt(s["win_rate"], "pct0")),
        ("&Oslash; Trade-Rendite", _fmt(s["avg_trade_return"], "pct")),
        ("Profit-Faktor", _fmt(s["profit_factor"])),
        ("&Oslash; Haltedauer (Tage)", _fmt(s["avg_holding_days"])),
        ("Summe Kosten (% v. Kapital)", _fmt(s["total_costs_pct"], "pct")),
    ]
    stat_rows = "\n".join(
        f"<tr><td>{name}</td><td class='num'>{value}</td></tr>" for name, value in rows
    )

    trades_html = ""
    if not result.trades.empty:
        recent = result.trades.tail(25).copy()
        recent["entry_date"] = recent["entry_date"].astype(str).str[:10]
        recent["exit_date"] = recent["exit_date"].astype(str).str[:10]
        recent["return"] = (recent["return"] * 100).round(2)
        recent = recent.rename(
            columns={
                "entry_date": "Einstieg", "exit_date": "Ausstieg", "side": "Richtung",
                "entry_price": "Einstiegskurs", "exit_price": "Ausstiegskurs",
                "return": "Rendite %", "holding_days": "Tage", "open": "Offen",
            }
        )
        trades_html = (
            "<h2>Letzte Trades</h2><div class='scroll'>"
            + recent.to_html(index=False, float_format=lambda v: f"{v:.2f}")
            + "</div>"
        )

    params = html.escape(", ".join(f"{k}={v}" for k, v in result.params.items()) or "Defaults")
    period = f"{result.equity.index[0].date()} bis {result.equity.index[-1].date()}"

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", sans-serif; margin: 2rem auto; max-width: 960px; padding: 0 1rem; color: #1a1a1a; }}
  h1 {{ font-size: 1.5rem; }} h2 {{ font-size: 1.15rem; margin-top: 2rem; }}
  .meta {{ color: #555; margin-bottom: 1.5rem; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 480px; }}
  td, th {{ padding: 6px 10px; border-bottom: 1px solid #e2e2e2; text-align: left; font-size: 0.92rem; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .scroll {{ overflow-x: auto; }}
  .scroll table {{ max-width: none; white-space: nowrap; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p class="meta">Strategie <strong>{html.escape(result.strategy_name)}</strong> ({params})<br>
Zeitraum {period} &middot; {len(result.equity)} Handelstage</p>
<h2>Equity-Kurve</h2>
{equity_chart}
<h2>Drawdown</h2>
{dd_chart}
<h2>Kennzahlen</h2>
<table>{stat_rows}</table>
{trades_html}
<p class="meta" style="margin-top:2rem">Hinweis: Vergangenheitsergebnisse sind keine Garantie für zukünftige Renditen.
In-Sample-Backtests überschätzen die Live-Performance systematisch — zur Validierung Walk-Forward-Analyse und Papertrading nutzen.</p>
</body>
</html>
"""


def save_report(result: BacktestResult, path: str | Path, title: str | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(result, title), encoding="utf-8")
    return path
