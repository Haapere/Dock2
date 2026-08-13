"""Tests der Erfassungsschleife."""

from __future__ import annotations

import pytest

from fokusradar import timeutil
from fokusradar.agent import Tracker
from tests.conftest import FakeIdleBackend, FakeInputCounter, FakeWindowBackend


@pytest.fixture
def parts(database, config):
    windows = FakeWindowBackend()
    idle = FakeIdleBackend(0.0)
    counter = FakeInputCounter()
    tracker = Tracker(
        database,
        config,
        window_backend=windows,
        idle_backend=idle,
        input_counter=counter,
    )
    tracker.start()
    return tracker, windows, idle, counter


def test_gleiches_fenster_erzeugt_nur_eine_zeile(parts, database, clock):
    tracker, windows, _idle, _counter = parts
    windows.set("code.exe", "main.py")

    for _ in range(5):
        tracker.tick(clock.advance(3))

    events = database.window_events()
    assert len(events) == 1
    assert events[0].is_open

    tracker.stop(clock.now)
    assert database.window_events()[0].duration_seconds == 12  # 5 Abfragen à 3 s


def test_fensterwechsel_schliesst_die_vorige_nutzung(parts, database, clock):
    tracker, windows, _idle, _counter = parts
    windows.set("code.exe", "main.py")
    tracker.tick(clock.now)

    windows.set("firefox.exe", "Nachrichten")
    tracker.tick(clock.advance(60))
    tracker.stop(clock.advance(30))

    events = list(reversed(database.window_events()))
    assert [(e.process_name, e.duration_seconds) for e in events] == [
        ("code.exe", 60),
        ("firefox.exe", 30),
    ]


def test_titelwechsel_gilt_als_neue_nutzung(parts, database, clock):
    tracker, windows, _idle, _counter = parts
    windows.set("code.exe", "main.py")
    tracker.tick(clock.now)
    windows.set("code.exe", "test_agent.py")
    tracker.tick(clock.advance(30))
    tracker.stop(clock.advance(10))

    events = list(reversed(database.window_events()))
    assert [e.window_title for e in events] == ["main.py", "test_agent.py"]


def test_pause_wird_nicht_der_letzten_app_zugerechnet(parts, database, clock):
    tracker, windows, idle, _counter = parts
    windows.set("code.exe", "main.py")
    tracker.tick(clock.now)

    # Zehn Minuten später meldet das System: seit 600 s keine Eingabe.
    idle.seconds = 600.0
    tracker.tick(clock.advance(600))

    event = database.window_events()[0]
    assert event.duration_seconds == 0  # die gesamte Zeit war Pause
    assert tracker.stats.idle_periods == 1

    # Solange die Pause anhält, entsteht keine neue Sitzung.
    idle.seconds = 900.0
    tracker.tick(clock.advance(300))
    assert len(database.window_events()) == 1


def test_rueckkehr_nach_pause_startet_neue_sitzung(parts, database, clock):
    tracker, windows, idle, _counter = parts
    windows.set("code.exe", "main.py")
    tracker.tick(clock.now)
    tracker.tick(clock.advance(120))  # 2 Minuten aktiv

    idle.seconds = 400.0
    tracker.tick(clock.advance(400))  # Pause erkannt, rückwirkend beendet

    idle.seconds = 0.0
    tracker.tick(clock.advance(60))  # zurück am Rechner
    tracker.stop(clock.advance(60))

    events = list(reversed(database.window_events()))
    assert [e.duration_seconds for e in events] == [120, 60]


def test_pause_beendet_nie_vor_dem_beginn(parts, database, clock):
    tracker, windows, idle, _counter = parts
    windows.set("code.exe")
    tracker.tick(clock.now)

    # Die letzte Eingabe liegt vor dem Beginn dieser Fensternutzung.
    idle.seconds = 3600.0
    tracker.tick(clock.advance(10))

    assert database.window_events()[0].duration_seconds == 0


def test_ohne_fenster_wird_die_sitzung_beendet(parts, database, clock):
    tracker, windows, _idle, _counter = parts
    windows.set("code.exe")
    tracker.tick(clock.now)

    windows.set(None)  # z. B. Sperrbildschirm
    tracker.tick(clock.advance(45))

    assert database.window_events()[0].duration_seconds == 45
    assert database.current_window_event() is None


def test_aktivitaetslevel_wird_im_eigenen_takt_geschrieben(parts, database, clock):
    tracker, windows, idle, _counter = parts
    windows.set("code.exe")
    idle.seconds = 5.0

    tracker.tick(clock.now)  # erster Messpunkt
    for _ in range(9):
        tracker.tick(clock.advance(3))  # 27 s später: noch kein zweiter
    assert len(database.activity_samples()) == 1

    tracker.tick(clock.advance(60))
    samples = database.activity_samples()
    assert len(samples) == 2
    assert samples[0].idle_seconds == 5
    assert samples[0].input_events_count == 7  # Zählerstand der Attrappe


def test_eingabe_zaehlung_wird_gespeichert_wenn_aktiv(database, config, clock):
    counter = FakeInputCounter(per_take=13)
    tracker = Tracker(
        database,
        config,
        window_backend=FakeWindowBackend(),
        idle_backend=FakeIdleBackend(0.0),
        input_counter=counter,
    )
    tracker.start()
    assert counter.started
    tracker.tick(clock.now)

    assert database.activity_samples()[0].input_events_count == 13
    tracker.stop(clock.now)
    assert not counter.started


def test_run_beendet_nach_max_ticks(database, config, clock):
    windows = FakeWindowBackend()
    windows.set("code.exe")
    tracker = Tracker(
        database,
        config,
        window_backend=windows,
        idle_backend=FakeIdleBackend(0.0),
        input_counter=FakeInputCounter(),
    )
    stats = tracker.run(max_ticks=3, sleeper=lambda _seconds: None)

    assert stats.ticks == 3
    assert stats.window_events == 1
    assert database.current_window_event() is None  # sauber abgeschlossen


def test_backend_report_nennt_grund_bei_fehlendem_backend(database, config):
    from fokusradar.capture.base import NullIdleBackend, NullWindowBackend
    from fokusradar.capture.input_counter import NullInputCounter

    tracker = Tracker(
        database,
        config,
        window_backend=NullWindowBackend("kein X11"),
        idle_backend=NullIdleBackend("keine Messung"),
        input_counter=NullInputCounter("abgeschaltet"),
    )
    report = dict(tracker.backend_report())
    assert report["Fenster-Erfassung"] == "inaktiv — kein X11"
    assert report["Idle-Erkennung"] == "inaktiv — keine Messung"
    assert report["Eingabe-Zählung"] == "inaktiv — abgeschaltet"


def test_ohne_fenster_backend_laeuft_die_schleife_weiter(database, config, clock):
    from fokusradar.capture.base import NullIdleBackend, NullWindowBackend
    from fokusradar.capture.input_counter import NullInputCounter

    tracker = Tracker(
        database,
        config,
        window_backend=NullWindowBackend("kein X11"),
        idle_backend=NullIdleBackend("keine Messung"),
        input_counter=NullInputCounter("abgeschaltet"),
    )
    tracker.start()
    tracker.tick(clock.now)
    tracker.stop(clock.advance(5))

    assert database.window_events() == []
    samples = database.activity_samples()
    assert len(samples) == 1
    assert samples[0].idle_seconds is None


def test_reste_frueherer_laeufe_werden_beim_start_geschlossen(database, config, clock):
    from fokusradar.capture.base import WindowInfo

    event_id = database.open_window_event(WindowInfo("alt.exe"), clock.now)
    database.touch_window_event(event_id, clock.advance(300))

    meldungen: list[str] = []
    tracker = Tracker(
        database,
        config,
        window_backend=FakeWindowBackend(),
        idle_backend=FakeIdleBackend(0.0),
        input_counter=FakeInputCounter(),
        on_event=meldungen.append,
    )
    tracker.start()

    assert database.window_events()[0].duration_seconds == 300
    assert any("früheren Lauf" in text for text in meldungen)


def test_zeitstempel_werden_als_utc_gespeichert(parts, database, clock):
    tracker, windows, _idle, _counter = parts
    windows.set("code.exe")
    tracker.tick(clock.now)

    roh = database.connection.execute("SELECT timestamp FROM window_events").fetchone()[0]
    assert roh.endswith("+00:00")
    assert timeutil.parse(roh) == clock.now
