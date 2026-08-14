"""Datenbankschema und Migrationen.

Das Schema folgt Abschnitt 6 des Bauplans. Alle Tabellen späterer Phasen
werden bereits angelegt, damit Phase 2-4 nur noch schreiben müssen.

``api_usage`` (Phase 4) kommt gegenüber dem Bauplan hinzu: ohne sie ließe sich
das dort geforderte Kosten-Tracking nicht führen.

Zwei bewusste Ergänzungen gegenüber dem Bauplan bei ``window_events``:
``ended_at`` und ``duration_seconds``. Statt alle paar Sekunden eine Zeile zu
schreiben, hält FokusRadar pro *zusammenhängender* Fensternutzung genau eine
Zeile und schreibt deren Ende fort. Das spart rund 99 % der Zeilen und macht
die Fokus-Sessions aus Phase 2 zu einer einfachen Abfrage.
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS window_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,          -- Beginn der Fensternutzung (UTC, ISO-8601)
    process_name TEXT NOT NULL,
    window_title TEXT,
    category TEXT,                        -- ab Phase 2
    ended_at DATETIME,                    -- fortgeschrieben, solange das Fenster aktiv ist
    duration_seconds INTEGER              -- NULL, solange die Nutzung läuft
);

CREATE INDEX IF NOT EXISTS idx_window_events_timestamp
    ON window_events (timestamp);

CREATE TABLE IF NOT EXISTS activity_level (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    idle_seconds INTEGER,
    input_events_count INTEGER
);

CREATE INDEX IF NOT EXISTS idx_activity_level_timestamp
    ON activity_level (timestamp);

CREATE TABLE IF NOT EXISTS screenshots_meta (      -- ab Phase 3
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    ocr_text TEXT,
    screenshot_path TEXT,
    deleted_at DATETIME
);

CREATE TABLE IF NOT EXISTS daily_summaries (       -- ab Phase 2
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL UNIQUE,
    total_active_minutes INTEGER,
    category_breakdown TEXT,   -- JSON
    top_distractions TEXT      -- JSON
);

CREATE TABLE IF NOT EXISTS suggestions (           -- ab Phase 2/4
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    source TEXT CHECK(source IN ('local','cloud')),
    suggestion_text TEXT NOT NULL,
    category TEXT,
    dismissed BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS exclusion_list (        -- ab Phase 3
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL,
    pattern_type TEXT CHECK(pattern_type IN ('process','title'))
);

CREATE TABLE IF NOT EXISTS api_usage (             -- ab Phase 4
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    date DATE NOT NULL,                -- ausgewerteter Tag
    kind TEXT NOT NULL,                -- 'taeglich' oder 'woche'
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_api_usage_timestamp
    ON api_usage (timestamp);
"""


def apply_schema(connection: sqlite3.Connection) -> int:
    """Schema anlegen bzw. aktualisieren; gibt die Schemaversion zurück.

    Mehrfaches Aufrufen ist unschädlich.
    """
    current = connection.execute("PRAGMA user_version").fetchone()[0]
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"Die Datenbank wurde mit einer neueren FokusRadar-Version angelegt "
            f"(Schemaversion {current}, unterstützt wird {SCHEMA_VERSION})."
        )
    connection.executescript(SCHEMA_SQL)
    if current != SCHEMA_VERSION:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    connection.commit()
    return SCHEMA_VERSION
