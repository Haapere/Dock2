"""Tests der Screenshot- und OCR-Kette sowie der Erfassungssperren."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fokusradar.agent import Tracker
from fokusradar.capture.screenshots import (
    clean_ocr_text,
    create_ocr_backend,
    create_screenshot_backend,
    screenshot_filename,
)
from fokusradar.config import ScreenshotConfig
from fokusradar.processing.exclusions import ExclusionList, ExclusionRule
from tests.conftest import (
    FakeIdleBackend,
    FakeInputCounter,
    FakeOcrBackend,
    FakeScreenshotBackend,
    FakeWindowBackend,
)


def _tracker(database, config, *, windows=None, exclusions=None, shots=None, ocr=None):
    return Tracker(
        database,
        config,
        window_backend=windows or FakeWindowBackend(),
        idle_backend=FakeIdleBackend(0.0),
        input_counter=FakeInputCounter(),
        exclusions=exclusions if exclusions is not None else ExclusionList(),
        screenshot_backend=shots or FakeScreenshotBackend(),
        ocr_backend=ocr or FakeOcrBackend(),
    )


@pytest.fixture
def shot_config(config):
    """Konfiguration mit eingeschalteten Screenshots (Intervall 5 Minuten)."""
    return replace(
        config,
        screenshots=ScreenshotConfig(enabled=True, interval_seconds=300, delete_image=True),
    )


# -- Hilfsfunktionen ---------------------------------------------------------


def test_ocr_text_wird_aufgeraeumt():
    assert clean_ocr_text("  Zeile eins  \n\n\n   Zeile   zwei ") == "Zeile eins\nZeile zwei"
    assert clean_ocr_text("   \n  ") is None
    assert clean_ocr_text(None) is None
    gekuerzt = clean_ocr_text("x" * 500, max_length=100)
    assert len(gekuerzt) == 100 and gekuerzt.endswith("…")


def test_dateiname_nutzt_die_ortszeit(clock):
    name = screenshot_filename(clock.now)
    assert name.endswith(".png") and name.startswith("2026-08-13")


def test_abgeschaltete_backends_melden_den_grund():
    shots = create_screenshot_backend(False)
    ocr = create_ocr_backend(False)
    assert not shots.available() and "abgeschaltet" in shots.unavailable_reason()
    assert not ocr.available() and ocr.text(None) is None


# -- Ausschlussliste und Smart Pause ----------------------------------------


def test_ausgeschlossenes_fenster_wird_nicht_gespeichert(database, config, clock):
    fenster = FakeWindowBackend()
    tracker = _tracker(
        database,
        config,
        windows=fenster,
        exclusions=ExclusionList([ExclusionRule("keepass*.exe", "process")]),
    )
    tracker.start()

    fenster.set("code.exe", "main.py")
    tracker.tick(clock.now)
    fenster.set("KeePassXC.exe", "Meine Passwörter")
    tracker.tick(clock.advance(60))
    tracker.tick(clock.advance(60))
    tracker.stop(clock.advance(10))

    events = database.window_events()
    assert len(events) == 1
    assert events[0].process_name == "code.exe"
    assert events[0].duration_seconds == 60  # bis zum Wechsel in den Tresor
    assert tracker.stats.excluded == 2


def test_titelmuster_greift_ebenfalls(database, config, clock):
    fenster = FakeWindowBackend()
    tracker = _tracker(
        database,
        config,
        windows=fenster,
        exclusions=ExclusionList([ExclusionRule("online-banking", "title")]),
    )
    tracker.start()

    fenster.set("firefox.exe", "Sparkasse Online-Banking")
    tracker.tick(clock.now)
    tracker.stop(clock.advance(30))

    assert database.window_events() == []
    assert "Ausschlussliste" in (tracker.blocked_reason or "")


def test_smart_pause_bei_videocall(database, config, clock):
    fenster = FakeWindowBackend()
    meldungen: list[str] = []
    tracker = _tracker(database, config, windows=fenster)
    tracker._on_event = meldungen.append
    tracker.start()

    fenster.set("code.exe", "main.py")
    tracker.tick(clock.now)
    fenster.set("teams.exe", "Wochenrunde")
    tracker.tick(clock.advance(120))
    assert tracker.blocked_reason and "Smart Pause" in tracker.blocked_reason
    assert tracker.stats.smart_pauses == 1

    fenster.set("code.exe", "main.py")
    tracker.tick(clock.advance(1800))
    tracker.stop(clock.advance(60))

    events = list(reversed(database.window_events()))
    assert [e.process_name for e in events] == ["code.exe", "code.exe"]
    assert [e.duration_seconds for e in events] == [120, 60]
    assert any("Smart Pause" in text for text in meldungen)
    assert any("läuft wieder" in text for text in meldungen)


def test_tracker_holt_die_liste_aus_der_datenbank(database, config):
    database.add_exclusion("tresor.exe", "process")
    tracker = Tracker(
        database,
        config,
        window_backend=FakeWindowBackend(),
        idle_backend=FakeIdleBackend(0.0),
        input_counter=FakeInputCounter(),
    )
    assert tracker.exclusions.excludes("tresor.exe")


# -- Screenshots -------------------------------------------------------------


def test_screenshot_mit_ocr_und_geloeschtem_bild(database, shot_config, clock):
    fenster = FakeWindowBackend()
    fenster.set("code.exe", "main.py")
    shots = FakeScreenshotBackend()
    ocr = FakeOcrBackend()
    tracker = _tracker(database, shot_config, windows=fenster, shots=shots, ocr=ocr)
    tracker.start()

    tracker.tick(clock.now)

    eintraege = database.screenshots()
    assert len(eintraege) == 1
    eintrag = eintraege[0]
    assert eintrag.ocr_text == "Kostenstelle 4711\nAngebot"
    assert eintrag.screenshot_path is None  # Pfad wird gar nicht erst gespeichert
    assert eintrag.deleted_at is not None
    assert not shots.captures[0].exists()  # Bild ist weg, nur der Text bleibt
    assert ocr.calls == 1


def test_bild_bleibt_liegen_wenn_gewuenscht(database, shot_config, clock):
    behalten = replace(
        shot_config, screenshots=replace(shot_config.screenshots, delete_image=False)
    )
    fenster = FakeWindowBackend()
    fenster.set("code.exe", "main.py")
    shots = FakeScreenshotBackend()
    tracker = _tracker(database, behalten, windows=fenster, shots=shots)
    tracker.start()
    tracker.tick(clock.now)

    eintrag = database.screenshots()[0]
    assert eintrag.screenshot_path == str(shots.captures[0])
    assert eintrag.deleted_at is None
    assert shots.captures[0].exists()


def test_screenshot_haelt_sein_intervall_ein(database, shot_config, clock):
    fenster = FakeWindowBackend()
    fenster.set("code.exe", "main.py")
    tracker = _tracker(database, shot_config, windows=fenster)
    tracker.start()

    tracker.tick(clock.now)
    for _ in range(10):
        tracker.tick(clock.advance(20))  # nach 200 s noch keine zweite Aufnahme
    assert len(database.screenshots()) == 1

    tracker.tick(clock.advance(300))
    assert len(database.screenshots()) == 2


def test_kein_screenshot_bei_ausschluss_oder_pause(database, shot_config, clock):
    fenster = FakeWindowBackend()
    idle = FakeIdleBackend(0.0)
    tracker = Tracker(
        database,
        shot_config,
        window_backend=fenster,
        idle_backend=idle,
        input_counter=FakeInputCounter(),
        exclusions=ExclusionList([ExclusionRule("keepass*.exe", "process")]),
        screenshot_backend=FakeScreenshotBackend(),
        ocr_backend=FakeOcrBackend(),
    )
    tracker.start()

    fenster.set("KeePassXC.exe", "Tresor")
    tracker.tick(clock.now)
    fenster.set("teams.exe", "Besprechung")
    tracker.tick(clock.advance(600))
    assert database.screenshots() == []

    # Auch während einer Pause wird nichts aufgenommen.
    fenster.set("code.exe", "main.py")
    idle.seconds = 900.0
    tracker.tick(clock.advance(900))
    assert database.screenshots() == []

    # Zurück an der Arbeit: jetzt schon.
    idle.seconds = 0.0
    tracker.tick(clock.advance(60))
    assert len(database.screenshots()) == 1


def test_abgeschaltete_screenshots_bleiben_aus(database, config, clock):
    fenster = FakeWindowBackend()
    fenster.set("code.exe", "main.py")
    shots = FakeScreenshotBackend()
    tracker = _tracker(database, config, windows=fenster, shots=shots)
    tracker.start()
    tracker.tick(clock.now)

    assert database.screenshots() == []
    assert shots.captures == []


def test_gescheiterte_aufnahme_wird_gemeldet(database, shot_config, clock):
    fenster = FakeWindowBackend()
    fenster.set("code.exe", "main.py")
    meldungen: list[str] = []
    tracker = _tracker(
        database, shot_config, windows=fenster, shots=FakeScreenshotBackend(works=False)
    )
    tracker._on_event = meldungen.append
    tracker.start()
    tracker.tick(clock.now)

    assert database.screenshots() == []
    assert any("fehlgeschlagen" in text for text in meldungen)


def test_ohne_erkannten_text_bleibt_die_spalte_leer(database, shot_config, clock):
    fenster = FakeWindowBackend()
    fenster.set("code.exe", "main.py")
    tracker = _tracker(database, shot_config, windows=fenster, ocr=FakeOcrBackend(None))
    tracker.start()
    tracker.tick(clock.now)

    eintrag = database.screenshots()[0]
    assert eintrag.ocr_text is None
    assert eintrag.deleted_at is not None
