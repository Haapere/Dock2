"""Tests der Kommandozeile."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest

from fokusradar import timeutil
from fokusradar.capture.base import WindowInfo
from fokusradar.cli import main
from fokusradar.storage.db import Database


@pytest.fixture
def db_pfad(tmp_path):
    return tmp_path / "fokusradar.db"


def _daten_anlegen(pfad, *, tag_versatz: int = 0) -> None:
    """Zwei abgeschlossene Fensternutzungen und einen Messpunkt schreiben.

    Verankert auf 09:00 Ortszeit des jeweiligen Tages — „vor einer Stunde" wäre
    kurz nach Mitternacht schon der Vortag und die Tagesfilter würden wackeln.
    """
    tag = (datetime.now().astimezone() - timedelta(days=tag_versatz)).date()
    beginn = datetime.combine(tag, time(9, 0)).astimezone()
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


def _tagesdaten(pfad, *, tag_versatz: int = 0) -> None:
    """Einen Arbeitstag mit Fokus- und Ablenkungszeit anlegen."""
    tag = (datetime.now().astimezone() - timedelta(days=tag_versatz)).date()
    start = datetime.combine(tag, time(9, 0)).astimezone()
    verlauf = [
        (0, 3600, "code.exe", "main.py"),
        (60, 1800, "firefox.exe", "Doku – YouTube"),
        (90, 3600, "code.exe", "test.py"),
    ]
    with Database(pfad) as db:
        for versatz, dauer, prozess, titel in verlauf:
            beginn = start + timedelta(minutes=versatz)
            event_id = db.open_window_event(WindowInfo(prozess, titel), beginn)
            db.close_window_event(event_id, beginn + timedelta(seconds=dauer))


def test_auswerten_zeigt_kennzahlen_und_speichert(db_pfad, capsys):
    _tagesdaten(db_pfad)
    assert main(["--db", str(db_pfad), "auswerten"]) == 0
    ausgabe = capsys.readouterr().out

    assert "Erfasste Zeit" in ausgabe
    assert "2h 30m" in ausgabe
    assert "Fokus-Sessions" in ausgabe
    assert "Top-Ablenkungen" in ausgabe
    assert "Vorschläge" in ausgabe

    with Database(db_pfad) as db:
        tag = timeutil.parse_day("heute")
        assert db.daily_summary(tag)["total_active_minutes"] == 150
        assert db.suggestions(day=tag)
        # Die Kategorien stehen jetzt auch an den Rohdaten.
        assert {e.category for e in db.window_events(day=tag)} == {
            "entwicklung",
            "ablenkung",
        }


def test_auswerten_kann_ohne_speichern_laufen(db_pfad, capsys):
    _tagesdaten(db_pfad)
    assert main(["--db", str(db_pfad), "auswerten", "--nicht-speichern"]) == 0
    capsys.readouterr()

    with Database(db_pfad) as db:
        assert db.daily_summary(timeutil.parse_day("heute")) is None
        assert db.suggestions() == []


def test_auswerten_mit_wochentrend(db_pfad, capsys):
    _tagesdaten(db_pfad)
    _tagesdaten(db_pfad, tag_versatz=2)
    assert main(["--db", str(db_pfad), "auswerten", "--woche"]) == 0
    ausgabe = capsys.readouterr().out

    assert "Letzte sieben Tage" in ausgabe
    zeilen = [z for z in ausgabe.splitlines() if z.startswith("20")]
    assert len(zeilen) == 7
    assert sum(1 for z in zeilen if "—" in z) == 5


def test_auswerten_ohne_daten(db_pfad, capsys):
    assert main(["--db", str(db_pfad), "auswerten"]) == 0
    assert "keine Daten" in capsys.readouterr().out


def test_kategorien_anzeigen_und_testen(db_pfad, capsys):
    assert main(["--db", str(db_pfad), "kategorien"]) == 0
    liste = capsys.readouterr().out
    assert "entwicklung" in liste and "zählt als fokus" in liste
    assert "eingebaute Regeln" in liste

    assert main(
        ["--db", str(db_pfad), "kategorien", "--test", "firefox.exe", "--titel", "Musik – YouTube"]
    ) == 0
    test = capsys.readouterr().out
    assert "→ Kategorie: ablenkung" in test


def test_eigene_regeldatei_wird_benutzt(tmp_path, db_pfad, capsys):
    config_pfad = tmp_path / "config.toml"
    (tmp_path / "categories.yaml").write_text(
        "standard: alles\nkategorien:\n  - name: alles\n    zaehlt_als: fokus\n"
        "    prozesse: ['*']\n",
        encoding="utf-8",
    )
    config_pfad.write_text("[erfassung]\nintervall_sekunden = 2\n", encoding="utf-8")

    assert main(["--config", str(config_pfad), "--db", str(db_pfad), "kategorien"]) == 0
    ausgabe = capsys.readouterr().out
    assert "categories.yaml" in ausgabe
    assert "alles" in ausgabe


def test_kaputte_regeldatei_liefert_exitcode_2(tmp_path, db_pfad, capsys):
    config_pfad = tmp_path / "config.toml"
    config_pfad.write_text("[erfassung]\n", encoding="utf-8")
    (tmp_path / "categories.yaml").write_text("kategorien: []\n", encoding="utf-8")

    assert main(["--config", str(config_pfad), "--db", str(db_pfad), "auswerten"]) == 2
    assert "Fehler in den Regeln" in capsys.readouterr().err


def test_config_anlegen_erzeugt_auch_die_regeldatei(tmp_path, capsys):
    pfad = tmp_path / "config.toml"
    assert main(["--config", str(pfad), "config", "--anlegen"]) == 0
    ausgabe = capsys.readouterr().out

    assert (tmp_path / "categories.yaml").is_file()
    assert (tmp_path / "exclusions.yaml").is_file()
    assert "Kategorien:  angelegt" in ausgabe
    assert "Ausschluss:  angelegt" in ausgabe

    assert main(["--config", str(pfad), "config"]) == 0
    anzeige = capsys.readouterr().out
    assert "Regeldatei" in anzeige
    assert "Dashboard          http://127.0.0.1:8760/" in anzeige


def test_ausschluss_wird_beim_ersten_start_aus_der_vorlage_gefuellt(tmp_path, db_pfad, capsys):
    config_pfad = tmp_path / "config.toml"
    config_pfad.write_text("[erfassung]\n", encoding="utf-8")
    (tmp_path / "exclusions.yaml").write_text(
        "prozesse:\n  - tresor.exe\ntitel:\n  - geheim\n", encoding="utf-8"
    )

    assert main(["--config", str(config_pfad), "--db", str(db_pfad), "ausschluss"]) == 0
    ausgabe = capsys.readouterr()
    assert "aus der Vorlage übernommen" in ausgabe.err
    assert "tresor.exe" in ausgabe.out
    assert "geheim" in ausgabe.out

    # Zweiter Aufruf: keine erneute Übernahme.
    assert main(["--config", str(config_pfad), "--db", str(db_pfad), "ausschluss"]) == 0
    assert "übernommen" not in capsys.readouterr().err


def test_ausschluss_pflegen_und_pruefen(db_pfad, capsys):
    assert main(["--db", str(db_pfad), "ausschluss", "hinzufuegen", "--prozess", "tresor.exe"]) == 0
    assert "Aufgenommen" in capsys.readouterr().out

    assert main(["--db", str(db_pfad), "ausschluss", "pruefen", "tresor.exe"]) == 0
    assert "wird NICHT erfasst" in capsys.readouterr().out

    assert main(["--db", str(db_pfad), "ausschluss", "pruefen", "code.exe"]) == 0
    assert "wird erfasst" in capsys.readouterr().out

    with Database(db_pfad) as db:
        regel_id = [r for r in db.exclusions() if r.pattern == "tresor.exe"][0].id
    assert main(["--db", str(db_pfad), "ausschluss", "entfernen", str(regel_id)]) == 0
    assert "entfernt" in capsys.readouterr().out
    assert main(["--db", str(db_pfad), "ausschluss", "entfernen", str(regel_id)]) == 1


def test_ausschluss_hinzufuegen_ohne_muster_meldet_fehler(db_pfad, capsys):
    assert main(["--db", str(db_pfad), "ausschluss", "hinzufuegen"]) == 2
    assert "--prozess oder --titel" in capsys.readouterr().err


def test_screenshots_zeigen_erkannten_text(db_pfad, capsys):
    with Database(db_pfad) as db:
        db.record_screenshot(
            datetime.now().astimezone(),
            ocr_text="Angebot 4711\nKostenstelle",
            deleted_at=datetime.now().astimezone(),
        )

    assert main(["--db", str(db_pfad), "screenshots"]) == 0
    kurz = capsys.readouterr().out
    assert "Bild gelöscht" in kurz
    assert "Angebot 4711" in kurz

    assert main(["--db", str(db_pfad), "screenshots", "--text"]) == 0
    lang = capsys.readouterr().out
    assert "    Kostenstelle" in lang


def test_screenshots_ohne_aufnahmen(db_pfad, capsys):
    assert main(["--db", str(db_pfad), "screenshots"]) == 0
    ausgabe = capsys.readouterr().out
    assert "Keine Aufnahmen" in ausgabe
    assert "abgeschaltet" in ausgabe


def test_verschluesseln_ohne_datenbank(db_pfad, capsys):
    assert main(["--db", str(db_pfad), "verschluesseln", "--ja"]) == 1
    assert "noch keine Datenbank" in capsys.readouterr().err


def test_verschluesseln_stellt_die_datenbank_um(tmp_path, capsys, monkeypatch):
    pytest.importorskip("sqlcipher3", reason="Extra [krypto] nicht installiert")
    from fokusradar.storage import crypto

    monkeypatch.delenv(crypto.KEY_ENV_VAR, raising=False)
    db_pfad = tmp_path / "fokusradar.db"
    _tagesdaten(db_pfad)

    assert main(["--db", str(db_pfad), "verschluesseln", "--ja"]) == 0
    ausgabe = capsys.readouterr().out
    assert "Fertig" in ausgabe
    assert crypto.is_encrypted(db_pfad)
    assert (tmp_path / "schluessel.key").is_file()
    assert (tmp_path / "fokusradar.db.unverschluesselt").is_file()

    # Ein zweiter Lauf erkennt den Zustand.
    assert main(["--db", str(db_pfad), "verschluesseln", "--ja"]) == 0
    assert "bereits verschlüsselt" in capsys.readouterr().out


def test_status_zeigt_verschluesselung_und_ausschluss(tmp_path, capsys, monkeypatch):
    pytest.importorskip("sqlcipher3", reason="Extra [krypto] nicht installiert")
    from fokusradar.storage import crypto

    monkeypatch.delenv(crypto.KEY_ENV_VAR, raising=False)
    db_pfad = tmp_path / "fokusradar.db"
    _tagesdaten(db_pfad)
    main(["--db", str(db_pfad), "verschluesseln", "--ja"])
    capsys.readouterr()

    config_pfad = tmp_path / "config.toml"
    config_pfad.write_text(
        f'[speicher]\ndatenbank = "{db_pfad.as_posix()}"\nverschluesselt = true\n'
        f'schluessel_datei = "{(tmp_path / "schluessel.key").as_posix()}"\n',
        encoding="utf-8",
    )
    assert main(["--config", str(config_pfad), "status"]) == 0
    ausgabe = capsys.readouterr().out
    assert "verschlüsselt)" in ausgabe
    assert "Ausschlussliste:" in ausgabe
    assert "Smart Pause bei" in ausgabe


def test_falscher_schluessel_liefert_exitcode_3(tmp_path, capsys, monkeypatch):
    pytest.importorskip("sqlcipher3", reason="Extra [krypto] nicht installiert")
    from fokusradar.storage import crypto

    db_pfad = tmp_path / "fokusradar.db"
    _tagesdaten(db_pfad)
    monkeypatch.delenv(crypto.KEY_ENV_VAR, raising=False)
    main(["--db", str(db_pfad), "verschluesseln", "--ja"])
    capsys.readouterr()

    config_pfad = tmp_path / "config.toml"
    config_pfad.write_text(
        f'[speicher]\ndatenbank = "{db_pfad.as_posix()}"\nverschluesselt = true\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(crypto.KEY_ENV_VAR, "falscher-schluessel")
    assert main(["--config", str(config_pfad), "status"]) == 3
    assert "Schlüssel" in capsys.readouterr().err
