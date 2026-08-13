"""Tests der Kommandozeile."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fokusradar import timeutil
from fokusradar.capture.base import WindowInfo
from fokusradar.cli import main
from fokusradar.storage.db import Database


@pytest.fixture
def db_pfad(tmp_path):
    return tmp_path / "fokusradar.db"


def _daten_anlegen(pfad, *, tag_versatz: int = 0) -> None:
    """Zwei abgeschlossene Fensternutzungen und einen Messpunkt schreiben."""
    beginn = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(
        days=tag_versatz, hours=1
    )
    with Database(pfad) as db:
        erstes = db.open_window_event(WindowInfo("code.exe", "main.py"), beginn)
        db.close_window_event(erstes, beginn + timedelta(minutes=25))
        zweites = db.open_window_event(WindowInfo("firefox.exe", "Nachrichten"), beginn + timedelta(minutes=25))
        db.close_window_event(zweites, beginn + timedelta(minutes=35))
        db.record_activity(beginn + timedelta(minutes=35), idle_seconds=8, input_events_count=120)


def test_status_ohne_daten(db_pfad, capsys):
    assert main(["--db", str(db_pfad), "status"]) == 0
    ausgabe = capsys.readouterr().out
    assert "Noch keine Daten erfasst" in ausgabe
    assert "window_events" in ausgabe
    assert "Vorgabewerte" in ausgabe


def test_log_und_zeiten_zeigen_die_rohdaten(db_pfad, capsys):
    _daten_anlegen(db_pfad)

    assert main(["--db", str(db_pfad), "log"]) == 0
    log = capsys.readouterr().out
    assert "code.exe" in log and "firefox.exe" in log
    assert "main.py" in log
    assert "25m 00s" in log

    assert main(["--db", str(db_pfad), "zeiten", "--tag", "heute"]) == 0
    zeiten = capsys.readouterr().out
    assert "Erfaste" not in zeiten  # kein Tippfehler in der Überschrift
    assert "code.exe" in zeiten
    assert "35m 00s" in zeiten  # Gesamtsumme 25 + 10 Minuten
    assert "71.4%" in zeiten


def test_zeiten_meldet_leeren_tag(db_pfad, capsys):
    _daten_anlegen(db_pfad)
    assert main(["--db", str(db_pfad), "zeiten", "--tag", "-5"]) == 0
    assert "keine Daten" in capsys.readouterr().out


def test_log_kann_auf_einen_tag_begrenzt_werden(db_pfad, capsys):
    _daten_anlegen(db_pfad)
    _daten_anlegen(db_pfad, tag_versatz=1)

    assert main(["--db", str(db_pfad), "log", "--tag", "gestern"]) == 0
    gestern = capsys.readouterr().out
    zeilen = [z for z in gestern.splitlines() if "code.exe" in z or "firefox.exe" in z]
    assert len(zeilen) == 2

    assert main(["--db", str(db_pfad), "log"]) == 0
    alles = capsys.readouterr().out
    zeilen = [z for z in alles.splitlines() if "code.exe" in z or "firefox.exe" in z]
    assert len(zeilen) == 4


def test_aktivitaet_zeigt_messpunkte(db_pfad, capsys):
    _daten_anlegen(db_pfad)
    assert main(["--db", str(db_pfad), "aktivitaet"]) == 0
    ausgabe = capsys.readouterr().out
    assert "8s" in ausgabe
    assert "120" in ausgabe


def test_track_laeuft_begrenzt_und_schreibt(db_pfad, capsys, monkeypatch):
    from tests.conftest import FakeIdleBackend, FakeInputCounter, FakeWindowBackend

    fenster = FakeWindowBackend()
    fenster.set("code.exe", "main.py")
    monkeypatch.setattr("fokusradar.agent.create_window_backend", lambda: fenster)
    monkeypatch.setattr("fokusradar.agent.create_idle_backend", lambda: FakeIdleBackend(0.0))
    monkeypatch.setattr(
        "fokusradar.agent.create_input_counter", lambda _setting: FakeInputCounter()
    )

    code = main(
        ["--db", str(db_pfad), "track", "--intervall", "0.01", "--dauer", "0.05", "-v"]
    )
    assert code == 0
    ausgabe = capsys.readouterr().out
    assert "Erfassung läuft" in ausgabe
    assert "Fenster: code.exe" in ausgabe
    assert "Beendet — Abfragen:" in ausgabe

    with Database(db_pfad) as db:
        events = db.window_events()
    assert len(events) == 1
    assert events[0].process_name == "code.exe"
    assert not events[0].is_open  # sauber abgeschlossen


def test_config_anlegen_und_anzeigen(tmp_path, capsys):
    pfad = tmp_path / "config.toml"
    assert main(["--config", str(pfad), "config", "--anlegen"]) == 0
    assert pfad.is_file()
    assert "angelegt" in capsys.readouterr().out

    # Ein zweites Anlegen überschreibt nichts, sondern meldet den Konflikt.
    assert main(["--config", str(pfad), "config", "--anlegen"]) == 1
    assert "bereits eine Konfiguration" in capsys.readouterr().err

    assert main(["--config", str(pfad), "config"]) == 0
    assert str(pfad) in capsys.readouterr().out


def test_fehlerhafte_konfiguration_liefert_exitcode_2(tmp_path, capsys):
    pfad = tmp_path / "config.toml"
    pfad.write_text("[erfassung]\nintervall_sekunden = -1\n", encoding="utf-8")
    assert main(["--config", str(pfad), "status"]) == 2
    assert "Fehler in der Konfiguration" in capsys.readouterr().err


def test_unverstaendlicher_tag_liefert_exitcode_2(db_pfad, capsys):
    assert main(["--db", str(db_pfad), "log", "--tag", "irgendwann"]) == 2
    assert "Unverständliche Tagesangabe" in capsys.readouterr().err


def test_tagesangaben_werden_verstanden():
    heute = datetime(2026, 8, 13).date()
    assert timeutil.parse_day("heute", heute) == heute
    assert timeutil.parse_day("gestern", heute) == heute - timedelta(days=1)
    assert timeutil.parse_day("-3", heute) == heute - timedelta(days=3)
    assert timeutil.parse_day("2026-01-02", heute) == datetime(2026, 1, 2).date()
