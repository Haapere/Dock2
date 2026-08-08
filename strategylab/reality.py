"""Realitätsprüfung: Ist der Vorteil echt oder Zufall?

Ein guter Backtest ist billig. Wer 500 Parameterkombinationen durchprobiert,
findet garantiert eine mit Sharpe 1,5 — selbst auf reinem Zufallsrauschen.
Dieses Modul prüft deshalb nicht "wie gut sieht es aus", sondern "wie sicher
ist es kein Zufall". Fünf unabhängige Angriffe auf das Ergebnis:

1. **Kostensensitivität** — bis zu welchen Transaktionskosten überlebt der
   Vorteil? Die Break-Even-Kosten sagen mehr als jede Renditezahl: Liegen sie
   nur knapp über den echten Kosten, ist die Strategie im Live-Betrieb tot,
   sobald der Spread einmal weiter ist als gedacht.

2. **Permutationstest** — die Positionsserie wird zyklisch zufällig verschoben.
   Das erhält Haltedauern, Umschlag und Marktexposition exakt, zerstört aber
   die Ausrichtung zwischen Signal und Kurs. Wenn die echte Strategie nicht
   deutlich besser ist als ihre zufällig getimten Zwillinge, war es Timing-Glück
   oder bloß eingesammelte Marktdrift. Ergebnis ist ein p-Wert.

3. **Deflated Sharpe Ratio** (Bailey/López de Prado) — korrigiert den Sharpe um
   die Anzahl der Versuche. Der beste aus N Versuchen ist systematisch zu gut;
   die DSR gibt die Wahrscheinlichkeit an, dass der wahre Vorteil trotzdem über
   null liegt. Sie berücksichtigt zusätzlich Schiefe und Wölbung der Renditen,
   also die typischen dicken Verlusttage.

4. **Parameter-Plateau** — liegt das beste Ergebnis auf einem breiten Hochplateau
   oder ist es eine einzelne Spitze zwischen schlechten Nachbarn? Eine Spitze
   bedeutet: minimal andere Marktbedingungen und der Vorteil ist weg.

5. **Zeitliche Stabilität** — Jahresaufschlüsselung und Anteil profitabler
   Walk-Forward-Fenster. Ein Ergebnis, das aus einem einzigen guten Jahr stammt,
   ist keine Strategie, sondern eine Anekdote.

Kostenkonvention: `cost_per_turnover` sind die Kosten für eine Positions-
änderung um 100 %. Ein voller Rundlauf (rein und raus) kostet das Doppelte.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

from strategylab import metrics
from strategylab.backtest import Backtester
from strategylab.strategy import get_strategy
from strategylab.walkforward import grid_combinations, optimize, walk_forward

TRADING_DAYS = 252
_NORMAL = NormalDist()
_EULER_GAMMA = 0.5772156649015329


def _py(value: Any) -> Any:
    """NumPy-Skalare in native Python-Typen wandeln.

    Parameter wandern in JSON-Konfigurationen und Ausgaben; `np.int64(20)`
    wäre dort weder serialisierbar noch lesbar.
    """
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


# ---------------------------------------------------------------- Kostenanalyse

def cost_sensitivity(
    strategy_name: str,
    df: pd.DataFrame,
    params: dict[str, Any],
    cost_levels: list[float] | None = None,
    initial_capital: float = 10_000.0,
) -> pd.DataFrame:
    """Backtest bei verschiedenen Kostenniveaus.

    `cost_levels` sind Kosten je Umschichtung. Die Spalte `rundlauf` zeigt
    den anschaulicheren Wert: was ein vollständiger Trade kostet.
    """
    if cost_levels is None:
        cost_levels = [0.0, 0.0005, 0.001, 0.0015, 0.0025, 0.005, 0.01]
    rows = []
    for cost in cost_levels:
        bt = Backtester(initial_capital=initial_capital, commission=cost, slippage=0.0)
        result = bt.run(get_strategy(strategy_name, **params), df)
        rows.append(
            {
                "kosten_je_umschichtung": cost,
                "rundlauf": 2 * cost,
                "cagr": round(result.stats["cagr"], 4),
                "sharpe": round(result.stats["sharpe"], 3),
                "max_drawdown": round(result.stats["max_drawdown"], 4),
            }
        )
    return pd.DataFrame(rows)


def breakeven_cost(sensitivity: pd.DataFrame) -> float:
    """Kostenniveau je Umschichtung, bei dem der CAGR auf null fällt.

    Lineare Interpolation zwischen den beiden Stützstellen, die den Nulldurch-
    gang einschließen. Ist die Strategie schon kostenfrei unprofitabel, ist das
    Ergebnis 0,0; überlebt sie alle geprüften Niveaus, `inf`.
    """
    sens = sensitivity.sort_values("kosten_je_umschichtung").reset_index(drop=True)
    if sens.iloc[0]["cagr"] <= 0:
        return 0.0
    for i in range(1, len(sens)):
        prev, cur = sens.iloc[i - 1], sens.iloc[i]
        if cur["cagr"] <= 0:
            span = prev["cagr"] - cur["cagr"]
            if span <= 0:
                return float(prev["kosten_je_umschichtung"])
            frac = prev["cagr"] / span
            step = cur["kosten_je_umschichtung"] - prev["kosten_je_umschichtung"]
            return float(prev["kosten_je_umschichtung"] + frac * step)
    return float("inf")


# ------------------------------------------------------------ Permutationstest

def permutation_test(
    positions: pd.Series,
    asset_returns: pd.Series,
    cost_per_turnover: float,
    n_permutations: int = 500,
    seed: int = 42,
) -> dict[str, float]:
    """Prüft, ob das *Timing* der Positionen einen Vorteil trägt.

    Nullhypothese: Die Positionsserie ist zufällig gegenüber dem Kursverlauf
    ausgerichtet. Umgesetzt durch zyklisches Verschieben um einen Zufallsversatz —
    Haltedauern, Umschlag und Exposition bleiben identisch, nur die Ausrichtung
    verschwindet. Der p-Wert ist der Anteil der Zufallsvarianten, die mindestens
    so gut sind wie das Original (mit +1-Korrektur, damit p nie exakt 0 wird).
    """
    pos = positions.to_numpy(dtype=float)
    rets = asset_returns.to_numpy(dtype=float)
    n = len(pos)
    if n < 30:
        raise ValueError("Permutationstest braucht mindestens 30 Datenpunkte")

    def sharpe_of(p: np.ndarray) -> float:
        turnover = np.abs(np.diff(p, prepend=0.0))
        r = p * rets - turnover * cost_per_turnover
        sd = r.std(ddof=1)
        if sd == 0 or not math.isfinite(sd):
            return 0.0
        return float(r.mean() / sd * math.sqrt(TRADING_DAYS))

    actual = sharpe_of(pos)
    rng = np.random.default_rng(seed)
    # Versatz nicht zu klein wählen, sonst bleibt die Ausrichtung fast erhalten.
    min_shift = max(5, n // 50)
    offsets = rng.integers(min_shift, n - min_shift, size=n_permutations)
    random_sharpes = np.array([sharpe_of(np.roll(pos, int(k))) for k in offsets])

    n_better = int((random_sharpes >= actual).sum())
    return {
        "actual_sharpe": round(actual, 3),
        "random_sharpe_mean": round(float(random_sharpes.mean()), 3),
        "random_sharpe_p95": round(float(np.percentile(random_sharpes, 95)), 3),
        "p_value": round((1 + n_better) / (1 + n_permutations), 4),
        "n_permutations": float(n_permutations),
    }


# ---------------------------------------------------------- Deflated Sharpe

def probabilistic_sharpe(
    sharpe_annual: float,
    n_obs: int,
    skew: float,
    kurtosis: float,
    benchmark_sharpe_annual: float = 0.0,
) -> float:
    """Wahrscheinlichkeit, dass der wahre Sharpe über `benchmark_sharpe_annual` liegt.

    Berücksichtigt die Verteilungsform: negative Schiefe und hohe Wölbung — also
    seltene, heftige Verlusttage — machen einen gemessenen Sharpe unzuverlässiger.
    `kurtosis` ist die nicht-exzessive Wölbung (Normalverteilung = 3).
    """
    if n_obs < 3:
        return 0.0
    sr = sharpe_annual / math.sqrt(TRADING_DAYS)
    sr0 = benchmark_sharpe_annual / math.sqrt(TRADING_DAYS)
    variance = 1.0 - skew * sr + (kurtosis - 1.0) / 4.0 * sr**2
    if variance <= 0:
        return 0.0
    z = (sr - sr0) * math.sqrt(n_obs - 1) / math.sqrt(variance)
    return float(_NORMAL.cdf(z))


def expected_max_sharpe(n_trials: int, sharpe_std_annual: float) -> float:
    """Erwarteter bester Sharpe aus `n_trials` wertlosen Versuchen.

    Das ist die Latte, die ein Ergebnis überspringen muss, um mehr zu sein als
    der Gewinner einer Lotterie. Sie wächst mit der Anzahl der Versuche und mit
    der Streuung der Ergebnisse.
    """
    if n_trials <= 1 or sharpe_std_annual <= 0:
        return 0.0
    z1 = _NORMAL.inv_cdf(1.0 - 1.0 / n_trials)
    z2 = _NORMAL.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    return float(sharpe_std_annual * ((1.0 - _EULER_GAMMA) * z1 + _EULER_GAMMA * z2))


def deflated_sharpe(
    returns: pd.Series,
    sharpe_annual: float,
    n_trials: int,
    sharpe_std_annual: float,
) -> dict[str, float]:
    """Deflated Sharpe Ratio: Sharpe nach Abzug des Mehrfachtest-Vorteils."""
    r = returns.dropna()
    skew = float(r.skew()) if len(r) > 3 else 0.0
    kurt = float(r.kurtosis()) + 3.0 if len(r) > 3 else 3.0
    hurdle = expected_max_sharpe(n_trials, sharpe_std_annual)
    dsr = probabilistic_sharpe(sharpe_annual, len(r), skew, kurt, benchmark_sharpe_annual=hurdle)
    return {
        "n_trials": float(n_trials),
        "sharpe_hurdle": round(hurdle, 3),
        "skew": round(skew, 3),
        "kurtosis": round(kurt, 2),
        "deflated_sharpe_prob": round(dsr, 4),
        "psr_vs_zero": round(
            probabilistic_sharpe(sharpe_annual, len(r), skew, kurt, 0.0), 4
        ),
    }


# --------------------------------------------------------- Parameter-Plateau

def parameter_plateau(
    ranking: pd.DataFrame,
    grid: dict[str, list[Any]],
    metric: str = "sharpe",
) -> dict[str, float]:
    """Prüft, ob das Optimum auf einem Plateau liegt oder eine Einzelspitze ist.

    Verglichen wird der beste Wert mit dem Mittel seiner unmittelbaren Nachbarn
    im Parameterraster. Ein Verhältnis nahe 1 heißt: die Umgebung funktioniert
    auch, der Parameter ist unkritisch. Deutlich unter 1 heißt: Zufallsfund.
    """
    param_keys = sorted(grid)
    if ranking.empty:
        return {"plateau_ratio": 0.0, "neighbours": 0.0, "positive_share": 0.0}

    best = ranking.iloc[0]
    best_metric = float(best[metric])
    index_of = {k: {v: i for i, v in enumerate(grid[k])} for k in param_keys}

    neighbour_metrics = []
    for _, row in ranking.iloc[1:].iterrows():
        distance = 0
        valid = True
        for k in param_keys:
            pos_best = index_of[k].get(best[k])
            pos_row = index_of[k].get(row[k])
            if pos_best is None or pos_row is None:
                valid = False
                break
            distance += abs(pos_best - pos_row)
        if valid and distance == 1:
            neighbour_metrics.append(float(row[metric]))

    positive_share = float((ranking[metric] > 0).mean())
    if not neighbour_metrics or best_metric <= 0:
        return {
            "plateau_ratio": 0.0,
            "neighbours": float(len(neighbour_metrics)),
            "positive_share": round(positive_share, 3),
        }
    ratio = float(np.mean(neighbour_metrics)) / best_metric
    return {
        "plateau_ratio": round(ratio, 3),
        "neighbours": float(len(neighbour_metrics)),
        "positive_share": round(positive_share, 3),
        "best_metric": round(best_metric, 3),
        "median_metric": round(float(ranking[metric].median()), 3),
    }


# ------------------------------------------------------ Zeitliche Stabilität

def yearly_breakdown(returns: pd.Series, benchmark_returns: pd.Series) -> pd.DataFrame:
    """Rendite je Kalenderjahr — Strategie gegen Buy & Hold."""
    rows = []
    for year, chunk in returns.groupby(returns.index.year):
        bench = benchmark_returns.loc[chunk.index]
        equity = (1.0 + chunk).cumprod()
        rows.append(
            {
                "jahr": int(year),
                "tage": len(chunk),
                "strategie": round(float(equity.iloc[-1] - 1.0), 4),
                "buy_hold": round(float((1.0 + bench).cumprod().iloc[-1] - 1.0), 4),
                "sharpe": round(metrics.sharpe_ratio(chunk), 2),
                "max_dd": round(metrics.max_drawdown(equity), 4),
            }
        )
    return pd.DataFrame(rows)


# ----------------------------------------------------------------- Gesamturteil

@dataclass
class Criterion:
    """Ein einzelnes Prüfkriterium mit Urteil und Begründung."""

    name: str
    value: float
    threshold: str
    passed: bool
    hard: bool
    explanation: str

    def line(self) -> str:
        mark = "OK  " if self.passed else "FAIL"
        weight = "K.o." if self.hard else "weich"
        if self.value is None or (isinstance(self.value, float) and math.isnan(self.value)):
            val = "n/a"  # nicht messbar, z.B. ohne Walk-Forward-Grid
        elif math.isinf(self.value):
            val = "unbegrenzt" if self.value > 0 else "-unbegrenzt"
        else:
            val = f"{self.value:.3f}"
        return f"  [{mark}] {self.name:<34} {val:>10}  (nötig: {self.threshold}, {weight})"


@dataclass
class RealityCheck:
    """Gesamtergebnis der Realitätsprüfung."""

    strategy_name: str
    params: dict
    criteria: list[Criterion] = field(default_factory=list)
    cost_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    yearly: pd.DataFrame = field(default_factory=pd.DataFrame)
    yearly_label: str = ""
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialisierbares Protokoll — Grundlage der Freigabe für den Bot."""
        return {
            "strategy": self.strategy_name,
            "params": {k: _py(v) for k, v in self.params.items()},
            "verdict": self.verdict,
            "criteria": [
                {
                    "name": c.name,
                    "value": None if not math.isfinite(c.value) else round(float(c.value), 4),
                    "threshold": c.threshold,
                    "passed": c.passed,
                    "hard": c.hard,
                }
                for c in self.criteria
            ],
            "breakeven_cost": (
                None
                if not math.isfinite(self.details.get("breakeven_cost", float("nan")))
                else round(self.details["breakeven_cost"], 6)
            ),
        }

    def save(self, path) -> None:
        """Schreibt das Prüfprotokoll als JSON."""
        from pathlib import Path

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))

    @property
    def hard_failures(self) -> list[Criterion]:
        return [c for c in self.criteria if c.hard and not c.passed]

    @property
    def soft_failures(self) -> list[Criterion]:
        return [c for c in self.criteria if not c.hard and not c.passed]

    @property
    def verdict(self) -> str:
        if self.hard_failures:
            return "NO-GO"
        if self.soft_failures:
            return "VORSICHT"
        return "GO"

    def summary_text(self) -> str:
        lines = [
            f"Realitätsprüfung: {self.strategy_name} {self.params}",
            "=" * 78,
            "",
            "Einzelkriterien:",
        ]
        lines += [c.line() for c in self.criteria]
        lines += ["", "Kostensensitivität:", self.cost_table.to_string(index=False), ""]
        if not self.yearly.empty:
            lines += [f"Jahresaufschlüsselung — {self.yearly_label}:",
                      self.yearly.to_string(index=False), ""]

        lines += ["=" * 78, f"URTEIL: {self.verdict}", ""]
        if self.verdict == "NO-GO":
            lines.append("Mindestens ein K.-o.-Kriterium ist gerissen:")
            lines += [f"  - {c.name}: {c.explanation}" for c in self.hard_failures]
            lines.append("")
            lines.append(
                "Diese Strategie gehört nicht an echtes Geld. Das ist der Normalfall,\n"
                "nicht das Scheitern des Verfahrens — die meisten Strategieideen halten\n"
                "einer ehrlichen Prüfung nicht stand. Genau dafür ist die Prüfung da."
            )
        elif self.verdict == "VORSICHT":
            lines.append("Alle K.-o.-Kriterien bestanden, aber weiche Kriterien reißen:")
            lines += [f"  - {c.name}: {c.explanation}" for c in self.soft_failures]
            lines.append("")
            lines.append(
                "Kandidat für einen Forward-Test mit Spielgeld ('paper'), nicht für\n"
                "echtes Kapital. Erst mehrere Monate echter Papertrading-Track-Record."
            )
        else:
            lines.append(
                "Alle Kriterien bestanden. Das ist eine notwendige, keine hinreichende\n"
                "Bedingung: Es bedeutet, dass der gemessene Vorteil statistisch nicht\n"
                "als Zufall erklärbar ist — nicht, dass er in der Zukunft anhält.\n"
                "Nächster Schritt ist trotzdem der Papertrading-Forward-Test."
            )
        return "\n".join(lines)


def full_check(
    strategy_name: str,
    df: pd.DataFrame,
    params: dict[str, Any] | None = None,
    grid: dict[str, list[Any]] | None = None,
    backtester: Backtester | None = None,
    train_size: int = 500,
    test_size: int = 125,
    n_permutations: int = 500,
    n_trials: int | None = None,
    seed: int = 42,
    min_trades: int = 30,
    min_oos_sharpe: float = 0.5,
    max_p_value: float = 0.05,
    min_dsr: float = 0.95,
    cost_safety_factor: float = 3.0,
    max_oos_drawdown: float = 0.25,
    min_positive_windows: float = 0.6,
    min_plateau_ratio: float = 0.6,
) -> RealityCheck:
    """Führt alle Prüfungen aus und fällt ein Gesamturteil.

    Mit `grid` läuft zusätzlich eine Walk-Forward-Analyse; die Kennzahlen
    stammen dann aus den Out-of-Sample-Fenstern. Ohne `grid` gibt es keine
    ehrliche Out-of-Sample-Schätzung — dann kann das Urteil nie GO lauten.

    `n_trials` ist die Anzahl der insgesamt probierten Varianten für die
    Deflated Sharpe Ratio. Ehrlich ist die Zahl aller Versuche des gesamten
    Forschungsprojekts, nicht nur des letzten Rasters. Wer zehn Strategien mit
    je 50 Kombinationen durchprobiert hat, sollte 500 angeben.
    """
    backtester = backtester or Backtester()
    params = dict(params or {})
    cost_per_turnover = backtester.cost_per_turnover
    details: dict[str, Any] = {}

    # --- Walk-Forward: die einzige ehrliche Zukunftsschätzung ---------------
    wf = None
    if grid:
        wf = walk_forward(
            strategy_name, df, grid,
            train_size=train_size, test_size=test_size,
            backtester=backtester,
        )
        # Ohne explizite Vorgabe die Parameter des letzten Fensters nehmen —
        # das sind die, die ein Bot heute tatsächlich handeln würde.
        params = params or {k: _py(wf.windows.iloc[-1][k]) for k in sorted(grid)}
        eval_returns = wf.oos_returns
        oos_sharpe = wf.oos_stats["sharpe"]
        oos_drawdown = abs(wf.oos_stats["max_drawdown"])
        positive_windows = float((wf.windows["oos_return"] > 0).mean())
        details["walkforward_windows"] = wf.windows
        opt = optimize(strategy_name, df, grid, backtester=backtester)
        details["ranking"] = opt.ranking
        plateau = parameter_plateau(opt.ranking, grid)
        sharpe_std = float(opt.ranking["sharpe"].std(ddof=1))
        trials = n_trials if n_trials is not None else len(grid_combinations(grid))
    else:
        eval_returns = pd.Series(dtype=float)
        oos_sharpe = float("nan")
        oos_drawdown = float("nan")
        positive_windows = float("nan")
        plateau = {"plateau_ratio": float("nan")}
        sharpe_std = 0.0
        trials = n_trials if n_trials is not None else 1

    # --- In-Sample-Backtest als Referenz und für Positionsserie ------------
    result = backtester.run(get_strategy(strategy_name, **params), df)
    details["in_sample_stats"] = result.stats
    if eval_returns.empty:
        eval_returns = result.returns

    asset_returns = df["Close"].pct_change().fillna(0.0)
    perm = permutation_test(
        result.positions, asset_returns, cost_per_turnover,
        n_permutations=n_permutations, seed=seed,
    )
    details["permutation"] = perm

    dsr = deflated_sharpe(
        eval_returns, oos_sharpe if grid else result.stats["sharpe"], trials, sharpe_std
    )
    details["deflated_sharpe"] = dsr
    details["plateau"] = plateau

    sens = cost_sensitivity(strategy_name, df, params, initial_capital=backtester.initial_capital)
    be_cost = breakeven_cost(sens)
    details["breakeven_cost"] = be_cost

    benchmark_returns = asset_returns
    # Wo eine Walk-Forward-Analyse lief, ist deren Out-of-Sample-Reihe die
    # ehrlichere Grundlage für die Jahrestabelle.
    if wf is not None:
        yearly = yearly_breakdown(wf.oos_returns, benchmark_returns.loc[wf.oos_returns.index])
        yearly_label = "Out-of-Sample (Walk-Forward)"
    else:
        yearly = yearly_breakdown(result.returns, benchmark_returns)
        yearly_label = "In-Sample-Backtest — keine Zukunftsaussage"
    benchmark_sharpe = metrics.sharpe_ratio(benchmark_returns)
    details["benchmark_sharpe"] = benchmark_sharpe

    # --- Kriterien --------------------------------------------------------
    criteria: list[Criterion] = []

    criteria.append(
        Criterion(
            "Out-of-Sample-Sharpe", oos_sharpe if grid else float("nan"),
            f"> {min_oos_sharpe}", bool(grid) and oos_sharpe > min_oos_sharpe, True,
            "Ohne Walk-Forward-Grid gibt es keine Out-of-Sample-Schätzung — "
            "ein In-Sample-Backtest allein rechtfertigt niemals Echtgeld."
            if not grid else
            f"Der Out-of-Sample-Sharpe von {oos_sharpe:.2f} liegt unter {min_oos_sharpe}. "
            "Nach Kosten und Steuern bleibt davon nichts Verlässliches übrig.",
        )
    )
    criteria.append(
        Criterion(
            "Permutationstest p-Wert", perm["p_value"], f"< {max_p_value}",
            perm["p_value"] < max_p_value, True,
            f"Mit p={perm['p_value']:.3f} erreichen {perm['p_value']:.0%} der zufällig "
            f"getimten Varianten dasselbe Ergebnis. Das Timing trägt keinen "
            f"nachweisbaren Vorteil (zufälliger Sharpe im Mittel "
            f"{perm['random_sharpe_mean']:.2f} gegen echte {perm['actual_sharpe']:.2f}).",
        )
    )
    criteria.append(
        Criterion(
            "Deflated Sharpe (Wahrsch.)", dsr["deflated_sharpe_prob"], f"> {min_dsr}",
            dsr["deflated_sharpe_prob"] > min_dsr, True,
            f"Nach Korrektur für {int(dsr['n_trials'])} Versuche liegt die "
            f"Wahrscheinlichkeit eines echten Vorteils bei nur "
            f"{dsr['deflated_sharpe_prob']:.1%}. Die Messlatte allein aus "
            f"Mehrfachtests liegt bei Sharpe {dsr['sharpe_hurdle']:.2f}.",
        )
    )
    cost_needed = cost_safety_factor * cost_per_turnover
    criteria.append(
        Criterion(
            "Break-Even-Kosten", be_cost, f"> {cost_needed:.4f}",
            be_cost > cost_needed, True,
            f"Der Vorteil verschwindet bereits bei Kosten von {be_cost:.4f} je "
            f"Umschichtung ({2 * be_cost:.2%} je Rundlauf). Angesetzt sind "
            f"{cost_per_turnover:.4f} — der Sicherheitsabstand von Faktor "
            f"{cost_safety_factor:.0f} fehlt. Ein einziger weiter Spread "
            f"kippt die Strategie ins Minus.",
        )
    )
    n_trades = float(result.stats["num_trades"])
    criteria.append(
        Criterion(
            "Anzahl Trades", n_trades, f">= {min_trades}", n_trades >= min_trades, False,
            f"Nur {int(n_trades)} Trades sind keine belastbare Stichprobe; "
            f"Trefferquote und Sharpe sind hier reines Rauschen.",
        )
    )
    criteria.append(
        Criterion(
            "Profitable WF-Fenster", positive_windows, f">= {min_positive_windows:.0%}",
            bool(grid) and positive_windows >= min_positive_windows, False,
            "Ohne Walk-Forward nicht messbar." if not grid else
            f"Nur {positive_windows:.0%} der Testfenster waren profitabel. Das "
            f"Gesamtergebnis stammt aus wenigen Glücksphasen statt aus einem "
            f"stabilen Vorteil.",
        )
    )
    criteria.append(
        Criterion(
            "Max. Drawdown (OOS)", oos_drawdown if grid else float("nan"),
            f"< {max_oos_drawdown:.0%}",
            bool(grid) and oos_drawdown < max_oos_drawdown, False,
            "Ohne Walk-Forward nicht messbar." if not grid else
            f"Ein Drawdown von {oos_drawdown:.0%} ist psychologisch schwer "
            f"durchzuhalten — die meisten schalten den Bot genau am tiefsten "
            f"Punkt ab und realisieren den Verlust.",
        )
    )
    # Die Latte ist der bessere von Buy & Hold und Null: In einem fallenden
    # Markt reicht es nicht, weniger zu verlieren als der Index — ein Bot, der
    # unterm Strich Geld verbrennt, hat keinen Zweck.
    reference_sharpe = max(benchmark_sharpe, 0.0)
    strategy_sharpe = oos_sharpe if grid else result.stats["sharpe"]
    criteria.append(
        Criterion(
            "Besser als Buy & Hold und > 0", strategy_sharpe, f"> {reference_sharpe:.2f}",
            math.isfinite(strategy_sharpe) and strategy_sharpe > reference_sharpe, False,
            f"Risikoadjustiert schlägt die Strategie (Sharpe "
            f"{strategy_sharpe:.2f}) die Messlatte aus Buy & Hold "
            f"(Sharpe {benchmark_sharpe:.2f}) und Null nicht. Dann ist ein "
            f"breiter ETF die bessere und billigere Wahl.",
        )
    )
    plateau_ratio = plateau.get("plateau_ratio", float("nan"))
    criteria.append(
        Criterion(
            "Parameter-Plateau", plateau_ratio, f"> {min_plateau_ratio}",
            bool(grid) and math.isfinite(plateau_ratio) and plateau_ratio > min_plateau_ratio,
            False,
            "Ohne Grid nicht messbar." if not grid else
            f"Die Nachbarparameter erreichen nur {plateau_ratio:.0%} des besten "
            f"Ergebnisses. Das Optimum ist eine Zufallsspitze, kein robustes Plateau.",
        )
    )

    return RealityCheck(
        strategy_name=strategy_name,
        params=params,
        criteria=criteria,
        cost_table=sens,
        yearly=yearly,
        yearly_label=yearly_label,
        details=details,
    )
