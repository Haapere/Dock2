"""Tests der Speicher-Schicht."""

from __future__ import annotations

from datetime import timedelta

from fokusradar import timeutil
from fokusradar.capture.base import WindowInfo
from fokusradar.storage.db import Database
from fokusradar.storage.schema import SCHEMA_VERSION


def test_schema_wird_angelegt_und_ist_idempotent(tmp_path):
    path = tmp_path / "db.sqlite"
    with Database(path) as db:
        counts = db.table_counts()
        version = db.connection.execute("PRAGMA user_version").fetchone()[0]

    assert version == SCHEMA_VERSION
    assert set(counts) == {
        "window_events",
        "activity_level",
        "screenshots_meta",
        "daily_summaries",
        "suggestions",
        "exclusion_list",
        "api_usage",
        "android_usage",
    }
    assert all(count == 0 for count in counts.values())

    # Zweites Öffnen darf nichts kaputt machen.
    with Database(path) as db:
        assert db.table_counts()["window_events"] == 0


def test_fensternutzung_oeffnen_und_schliessen(database, clock):
    event_id = database.open_window_event(WindowInfo("code.exe", "main.py"), clock.now)
    laufend = database.current_window_event()
    assert laufend is not None
    assert laufend.is_open
    assert laufend.process_name == "code.exe"

    dauer = database.close_window_event(event_id, clock.advance(90))
    assert dauer == 90

    events = database.window_events()
    assert len(events) == 1
    assert events[0].duration_seconds == 90
    assert events[0].window_title == "main.py"
    assert database.current_window_event() is None


def test_titel_kann_weggelassen_werden(database, clock):
    database.open_window_event(
        WindowInfo("bank.exe", "Kontostand"), clock.now, store_title=False
    )
    assert database.window_events()[0].window_title is None


def test_offene_sitzung_wird_beim_start_bereinigt(database, clock):
    event_id = database.open_window_event(WindowInfo("code.exe"), clock.now)
    database.touch_window_event(event_id, clock.advance(120))

    repariert = database.close_dangling_window_events()
    assert repariert == 1

    event = database.window_events()[0]
    assert event.duration_seconds == 120
    assert database.close_dangling_window_events() == 0


def test_zeiten_je_programm(database, clock):
    for name, seconds in (("code.exe", 600), ("firefox.exe", 300), ("code.exe", 120)):
        event_id = database.open_window_event(WindowInfo(name), clock.now)
        database.close_window_event(event_id, clock.advance(seconds))

    tag = timeutil.to_local(clock.now).date()
    totals = database.app_totals(tag)
    assert [(item.process_name, item.seconds, item.events) for item in totals] == [
        ("code.exe", 720, 2),
        ("firefox.exe", 300, 1),
    ]


def test_tagesgrenzen_trennen_die_daten(database, clock):
    heute = database.open_window_event(WindowInfo("code.exe"), clock.now)
    database.close_window_event(heute, clock.advance(60))

    morgen_start = clock.now + timedelta(days=1)
    spaeter = database.open_window_event(WindowInfo("code.exe"), morgen_start)
    database.close_window_event(spaeter, morgen_start + timedelta(seconds=30))

    tag = timeutil.to_local(clock.now).date()
    assert [item.seconds for item in database.app_totals(tag)] == [60]
    assert len(database.tracked_days()) == 2


def test_aktivitaets_messpunkte(database, clock):
    database.record_activity(clock.now, idle_seconds=12.4, input_events_count=42)
    database.record_activity(clock.advance(60), idle_seconds=None, input_events_count=None)

    samples = database.activity_samples()
    assert len(samples) == 2
    assert samples[-1].idle_seconds == 12  # gerundet gespeichert
    assert samples[-1].input_events_count == 42
    assert samples[0].idle_seconds is None
