import json
from pathlib import Path

import pandas as pd
import pytest

from strategylab.bot import (
    BotConfig,
    check_approval,
    compute_targets,
    generate_orders,
    load_holdings,
    load_universe,
    orders_text,
    run_bot,
    save_holdings,
    template_config,
)
from strategylab.data import generate_synthetic, save_csv


@pytest.fixture
def workspace(tmp_path):
    """Ein einsatzfähiger Bot mit Kursdaten und Freigabe."""
    for i, symbol in enumerate(["aaa", "bbb", "ccc", "ddd"]):
        save_csv(generate_synthetic(days=1200, seed=300 + i), tmp_path / f"data/{symbol}.csv")
    config = BotConfig(
        name="test",
        universe={s: str(tmp_path / f"data/{s}.csv") for s in ["aaa", "bbb", "ccc", "ddd"]},
        strategy="sma_cross",
        params={"fast": 20, "slow": 80},
        capital=50_000.0,
        check_file=str(tmp_path / "checks/test.json"),
    )
    return config, tmp_path


def write_check(path, verdict="GO", strategy="sma_cross", criteria=None):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "strategy": strategy,
                "params": {"fast": 20, "slow": 80},
                "verdict": verdict,
                "criteria": criteria or [],
            }
        )
    )


# ------------------------------------------------------------- Konfiguration

def test_config_roundtrip(tmp_path):
    config = template_config("bot_x")
    path = tmp_path / "bot.json"
    config.save(path)
    loaded = BotConfig.load(path)
    assert loaded.name == "bot_x"
    assert loaded.universe == config.universe
    assert loaded.risk_config().target_vol == config.risk_config().target_vol


def test_unknown_config_fields_are_rejected(tmp_path):
    """Ein Tippfehler in der Konfiguration darf nicht stillschweigend als
    Voreinstellung durchgehen — das wäre ein Bot, der anders handelt als gedacht."""
    path = tmp_path / "bot.json"
    path.write_text(json.dumps({"name": "x", "kaptial": 1000}))
    with pytest.raises(ValueError, match="Unbekannte Felder"):
        BotConfig.load(path)


def test_shared_and_per_symbol_params():
    shared = BotConfig(params={"fast": 20, "slow": 80})
    assert shared.params_for("aaa") == {"fast": 20, "slow": 80}
    per_symbol = BotConfig(params={"aaa": {"fast": 5}, "bbb": {"fast": 50}})
    assert per_symbol.params_for("aaa") == {"fast": 5}
    assert per_symbol.params_for("unbekannt") == {}


def test_missing_price_file_names_the_fix(tmp_path):
    config = BotConfig(universe={"aaa": str(tmp_path / "fehlt.csv")})
    with pytest.raises(FileNotFoundError, match="data fetch"):
        load_universe(config)


def test_empty_universe_is_rejected():
    with pytest.raises(ValueError, match="Universum ist leer"):
        load_universe(BotConfig())


# ------------------------------------------------------------ Sicherheitssperre

def test_bot_is_blocked_without_a_check_file(workspace):
    config, _ = workspace
    approval = check_approval(config)
    assert not approval.allowed
    assert approval.verdict == "FEHLT"
    with pytest.raises(PermissionError, match="gesperrt"):
        run_bot(config)


def test_bot_is_blocked_without_check_file_configured():
    approval = check_approval(BotConfig(check_file=None))
    assert not approval.allowed
    assert "check_file" in approval.reason


def test_bot_is_blocked_on_a_no_go_verdict(workspace):
    config, _ = workspace
    write_check(
        config.check_file, verdict="NO-GO",
        criteria=[{"name": "Permutationstest p-Wert", "hard": True, "passed": False}],
    )
    approval = check_approval(config)
    assert not approval.allowed
    assert "Permutationstest" in approval.reason
    with pytest.raises(PermissionError):
        run_bot(config)


def test_bot_is_blocked_when_the_check_belongs_to_another_strategy(workspace):
    """Ein Protokoll für eine andere Strategie ist keine Freigabe."""
    config, _ = workspace
    write_check(config.check_file, verdict="GO", strategy="rsi_reversion")
    approval = check_approval(config)
    assert not approval.allowed
    assert "rsi_reversion" in approval.reason


def test_caution_verdict_allows_paper_trading_with_a_warning(workspace):
    config, _ = workspace
    write_check(config.check_file, verdict="VORSICHT")
    approval = check_approval(config)
    assert approval.allowed
    assert "Papertrading" in approval.reason


def test_go_verdict_allows_orders(workspace):
    config, _ = workspace
    write_check(config.check_file, verdict="GO")
    targets, orders, approval = run_bot(config)
    assert approval.allowed
    assert approval.verdict == "GO"
    assert len(targets) == 4


def test_dry_run_bypasses_the_gate_explicitly(workspace):
    config, _ = workspace
    targets, orders, approval = run_bot(config, require_approval=False)
    assert not approval.allowed
    assert len(targets) == 4


# ------------------------------------------------------------- Zielpositionen

def test_targets_cover_the_whole_universe(workspace):
    config, _ = workspace
    targets = compute_targets(config)
    assert set(targets["symbol"]) == set(config.universe)
    assert (targets["zielanteil"].abs() <= 0.25 + 1e-9).all()
    assert (targets["zielwert"].abs() <= config.capital).all()


def test_target_shares_match_value_and_price(workspace):
    config, _ = workspace
    targets = compute_targets(config)
    for row in targets.itertuples():
        assert abs(row.zielstueck) <= abs(row.zielwert) / row.kurs + 1


def test_investment_never_exceeds_capital(workspace):
    config, _ = workspace
    targets = compute_targets(config)
    assert targets["zielwert"].abs().sum() <= config.capital + 1e-6


# -------------------------------------------------------------------- Orders

def test_orders_from_an_empty_portfolio_are_all_buys():
    targets = pd.DataFrame(
        [
            {"symbol": "aaa", "signal": 1.0, "zielanteil": 0.25, "zielwert": 2500.0,
             "kurs": 50.0, "zielstueck": 50, "kursdatum": "2026-01-02"},
        ]
    )
    orders = generate_orders(targets, {}, min_order_value=250.0)
    assert list(orders["aktion"]) == ["KAUFEN"]
    assert orders.iloc[0]["stueck"] == 50


def test_no_orders_when_holdings_match_targets():
    targets = pd.DataFrame(
        [{"symbol": "aaa", "signal": 1.0, "zielanteil": 0.25, "zielwert": 2500.0,
          "kurs": 50.0, "zielstueck": 50, "kursdatum": "2026-01-02"}]
    )
    assert generate_orders(targets, {"aaa": 50.0}).empty


def test_position_is_closed_when_the_signal_disappears():
    targets = pd.DataFrame(
        [{"symbol": "aaa", "signal": 0.0, "zielanteil": 0.0, "zielwert": 0.0,
          "kurs": 50.0, "zielstueck": 0, "kursdatum": "2026-01-02"}]
    )
    orders = generate_orders(targets, {"aaa": 50.0})
    assert orders.iloc[0]["aktion"] == "VERKAUFEN"
    assert "schließen" in orders.iloc[0]["hinweis"]


def test_small_adjustments_are_suppressed():
    """Bei 5 € Gebühr sind 100 € Ordervolumen 5 % Kosten — solche Anpassungen
    kosten mehr, als die genauere Gewichtung wert ist."""
    targets = pd.DataFrame(
        [{"symbol": "aaa", "signal": 1.0, "zielanteil": 0.25, "zielwert": 2550.0,
          "kurs": 50.0, "zielstueck": 51, "kursdatum": "2026-01-02"}]
    )
    orders = generate_orders(targets, {"aaa": 50.0}, min_order_value=250.0)
    assert orders.iloc[0]["aktion"] == "HALTEN"
    assert "Mindestordergröße" in orders.iloc[0]["hinweis"]


def test_closing_a_position_is_never_suppressed():
    """Ein Verkauf auf null muss auch unter der Mindestordergröße durchgehen —
    sonst bleibt eine Restposition ohne Signal für immer im Depot."""
    targets = pd.DataFrame(
        [{"symbol": "aaa", "signal": 0.0, "zielanteil": 0.0, "zielwert": 0.0,
          "kurs": 50.0, "zielstueck": 0, "kursdatum": "2026-01-02"}]
    )
    orders = generate_orders(targets, {"aaa": 1.0}, min_order_value=250.0)
    assert orders.iloc[0]["aktion"] == "VERKAUFEN"


def test_holdings_outside_the_universe_are_sold():
    targets = pd.DataFrame(
        [{"symbol": "aaa", "signal": 0.0, "zielanteil": 0.0, "zielwert": 0.0,
          "kurs": 50.0, "zielstueck": 0, "kursdatum": "2026-01-02"}]
    )
    orders = generate_orders(targets, {"aaa": 0.0, "altbestand": 10.0})
    row = orders[orders["symbol"] == "altbestand"].iloc[0]
    assert row["aktion"] == "PRUEFEN"
    assert "Kein aktueller Kurs" in row["hinweis"]


# ----------------------------------------------------------------- Bestände

def test_holdings_roundtrip(tmp_path):
    path = tmp_path / "holdings.json"
    save_holdings(path, {"aaa": 10.0, "bbb": 0.0})
    assert load_holdings(path) == {"aaa": 10.0, "bbb": 0.0}


def test_missing_holdings_file_means_empty_portfolio(tmp_path):
    assert load_holdings(tmp_path / "fehlt.json") == {}
    assert load_holdings(None) == {}


def test_bot_is_idempotent_after_recording_holdings(workspace):
    """Zweiter Lauf am selben Tag darf nichts mehr auslösen — sonst würde der
    Bot dieselbe Position mehrfach kaufen."""
    config, tmp_path = workspace
    write_check(config.check_file, verdict="GO")
    holdings_file = tmp_path / "holdings.json"

    targets, orders, _ = run_bot(config, holdings_file)
    save_holdings(holdings_file, {r.symbol: float(r.zielstueck) for r in targets.itertuples()})

    _, orders_again, _ = run_bot(config, holdings_file)
    actionable = orders_again[orders_again["aktion"].isin(["KAUFEN", "VERKAUFEN"])]
    assert actionable.empty


# ------------------------------------------------------------------ Ausgabe

def test_orders_text_states_that_nothing_is_executed_automatically(workspace):
    config, _ = workspace
    write_check(config.check_file, verdict="GO")
    targets, orders, approval = run_bot(config)
    text = orders_text(config, targets, orders, approval)
    assert "manuellen Ausführung" in text
    assert "platziert nichts selbst" in text


def test_orders_text_repeats_the_caution_warning(workspace):
    config, _ = workspace
    write_check(config.check_file, verdict="VORSICHT")
    targets, orders, approval = run_bot(config)
    text = orders_text(config, targets, orders, approval)
    assert "Achtung" in text
    assert "Papertrading" in text
