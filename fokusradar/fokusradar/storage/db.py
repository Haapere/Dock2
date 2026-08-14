"""Zugriff auf die lokale SQLite-Datenbank.

Alle Rohdaten bleiben in dieser Datei auf dem Gerät. Die Verschlüsselung per
SQLCipher ist für Phase 3 vorgesehen; bis dahin sollte die Datenbank im
Benutzerprofil liegen (Standardpfad) und nicht in einem Sync-Ordner.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from fokusradar import timeutil
from fokusradar.capture.base import WindowInfo
from fokusradar.storage.schema import apply_schema


@dataclass(frozen=True)
class WindowEvent:
    """Eine zusammenhängende Nutzung eines Fensters."""

    id: int
    started_at: datetime
    process_name: str
    window_title: str | None
    category: str | None
    ended_at: datetime | None
    duration_seconds: int | None

    @property
    def is_open(self) -> bool:
        return self.duration_seconds is None

    @property
    def effective_seconds(self) -> int:
        """Dauer in Sekunden — bei laufender Nutzung bis zum letzten Lebenszeichen.

        Dadurch taucht das gerade aktive Fenster in der Auswertung des laufenden
        Tages mit seiner bisherigen Zeit auf und nicht mit null.
        """
        if self.duration_seconds is not None:
            return int(self.duration_seconds)
        if self.ended_at is not None:
            return max(0, int(round((self.ended_at - self.started_at).total_seconds())))
        return 0


@dataclass(frozen=True)
class ActivitySample:
    """Ein Messpunkt des Aktivitätslevels."""

    timestamp: datetime
    idle_seconds: int | None
    input_events_count: int | None


@dataclass(frozen=True)
class Suggestion:
    """Ein Verbesserungsvorschlag (lokal erzeugt oder aus der Cloud)."""

    id: int
    date: date
    source: str
    text: str
    category: str | None
    dismissed: bool


@dataclass(frozen=True)
class AppTotal:
    """Aufsummierte Nutzung eines Programms in einem Zeitraum."""

    process_name: str
    seconds: int
    events: int


class Database:
    """Schmale Hülle um ``sqlite3`` mit den Abfragen von FokusRadar."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser()
        self._connection: sqlite3.Connection | None = None

    # -- Verbindung ---------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        """Verbindung öffnen (idempotent) und Schema sicherstellen."""
        if self._connection is not None:
            return self._connection
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA foreign_keys = ON")
        apply_schema(connection)
        self._connection = connection
        return connection

    @property
    def connection(self) -> sqlite3.Connection:
        return self.connect()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "Database":
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- Schreiben ----------------------------------------------------------

    def open_window_event(
        self,
        info: WindowInfo,
        started_at: datetime,
        *,
        store_title: bool = True,
        category: str | None = None,
    ) -> int:
        """Neue Fensternutzung beginnen und deren ID zurückgeben."""
        cursor = self.connection.execute(
            "INSERT INTO window_events (timestamp, process_name, window_title, category)"
            " VALUES (?, ?, ?, ?)",
            (
                timeutil.isoformat(started_at),
                info.process_name,
                info.window_title if store_title else None,
                category,
            ),
        )
        return int(cursor.lastrowid)

    def touch_window_event(self, event_id: int, at: datetime) -> None:
        """Ende einer laufenden Nutzung fortschreiben (Absicherung bei Absturz)."""
        self.connection.execute(
            "UPDATE window_events SET ended_at = ? WHERE id = ? AND duration_seconds IS NULL",
            (timeutil.isoformat(at), event_id),
        )

    def close_window_event(self, event_id: int, ended_at: datetime) -> int:
        """Nutzung abschließen und die Dauer in Sekunden zurückgeben."""
        row = self.connection.execute(
            "SELECT timestamp FROM window_events WHERE id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return 0
        started = timeutil.parse(row["timestamp"])
        duration = max(0, int(round((timeutil.to_utc(ended_at) - started).total_seconds())))
        self.connection.execute(
            "UPDATE window_events SET ended_at = ?, duration_seconds = ? WHERE id = ?",
            (timeutil.isoformat(ended_at), duration, event_id),
        )
        return duration

    def close_dangling_window_events(self) -> int:
        """Beim Start offene Nutzungen früherer Läufe abschließen.

        Als Ende gilt der zuletzt fortgeschriebene Zeitstempel; fehlt er, der
        Beginn (Dauer 0). Gibt die Anzahl der bereinigten Zeilen zurück.
        """
        cursor = self.connection.execute(
            """
            UPDATE window_events
               SET ended_at = COALESCE(ended_at, timestamp),
                   duration_seconds = CAST(
                       MAX(0, (julianday(COALESCE(ended_at, timestamp)) - julianday(timestamp))
                              * 86400.0
                       ) + 0.5 AS INTEGER)
             WHERE duration_seconds IS NULL
            """
        )
        return cursor.rowcount if cursor.rowcount > 0 else 0

    def record_activity(
        self,
        at: datetime,
        idle_seconds: float | None,
        input_events_count: int | None,
    ) -> None:
        """Einen Messpunkt des Aktivitätslevels speichern."""
        self.connection.execute(
            "INSERT INTO activity_level (timestamp, idle_seconds, input_events_count)"
            " VALUES (?, ?, ?)",
            (
                timeutil.isoformat(at),
                None if idle_seconds is None else int(round(idle_seconds)),
                input_events_count,
            ),
        )

    # -- Lesen --------------------------------------------------------------

    @staticmethod
    def _to_event(row: sqlite3.Row) -> WindowEvent:
        return WindowEvent(
            id=row["id"],
            started_at=timeutil.parse(row["timestamp"]),
            process_name=row["process_name"],
            window_title=row["window_title"],
            category=row["category"],
            ended_at=timeutil.parse(row["ended_at"]) if row["ended_at"] else None,
            duration_seconds=row["duration_seconds"],
        )

    def window_events(
        self,
        *,
        day: date | None = None,
        limit: int | None = None,
        ascending: bool = False,
    ) -> list[WindowEvent]:
        """Fensternutzungen, neueste zuerst; optional auf einen Tag begrenzt."""
        query = "SELECT * FROM window_events"
        params: list[object] = []
        if day is not None:
            start, end = timeutil.local_day_bounds(day)
            query += " WHERE timestamp >= ? AND timestamp < ?"
            params += [start, end]
        query += " ORDER BY timestamp ASC, id ASC" if ascending else " ORDER BY timestamp DESC, id DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        return [self._to_event(row) for row in self.connection.execute(query, params)]

    def current_window_event(self) -> WindowEvent | None:
        """Gerade laufende Fensternutzung, falls es eine gibt."""
        row = self.connection.execute(
            "SELECT * FROM window_events WHERE duration_seconds IS NULL"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return self._to_event(row) if row else None

    def app_totals(self, day: date, *, limit: int | None = None) -> list[AppTotal]:
        """Zeit je Programm an einem lokalen Kalendertag, absteigend sortiert."""
        start, end = timeutil.local_day_bounds(day)
        query = """
            SELECT process_name,
                   SUM(COALESCE(
                       duration_seconds,
                       -- laufende Nutzung: bis zum letzten Lebenszeichen,
                       -- +0.5 weil CAST abschneidet statt zu runden
                       CAST(MAX(0.0, (julianday(COALESCE(ended_at, timestamp))
                                      - julianday(timestamp)) * 86400.0) + 0.5 AS INTEGER)
                   )) AS seconds,
                   COUNT(*) AS events
              FROM window_events
             WHERE timestamp >= ? AND timestamp < ?
             GROUP BY process_name
             ORDER BY seconds DESC, events DESC, process_name
        """
        params: list[object] = [start, end]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        return [
            AppTotal(
                process_name=row["process_name"],
                seconds=int(row["seconds"] or 0),
                events=int(row["events"]),
            )
            for row in self.connection.execute(query, params)
        ]

    def activity_samples(
        self, *, day: date | None = None, limit: int | None = None
    ) -> list[ActivitySample]:
        """Messpunkte des Aktivitätslevels, neueste zuerst."""
        query = "SELECT * FROM activity_level"
        params: list[object] = []
        if day is not None:
            start, end = timeutil.local_day_bounds(day)
            query += " WHERE timestamp >= ? AND timestamp < ?"
            params += [start, end]
        query += " ORDER BY timestamp DESC, id DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        return [
            ActivitySample(
                timestamp=timeutil.parse(row["timestamp"]),
                idle_seconds=row["idle_seconds"],
                input_events_count=row["input_events_count"],
            )
            for row in self.connection.execute(query, params)
        ]

    def table_counts(self) -> dict[str, int]:
        """Zeilenzahl je Tabelle — für die Statusanzeige."""
        tables = [
            "window_events",
            "activity_level",
            "screenshots_meta",
            "daily_summaries",
            "suggestions",
            "exclusion_list",
        ]
        return {
            table: int(
                self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            )
            for table in tables
        }

    # -- Kategorien, Zusammenfassungen, Vorschläge (Phase 2) -----------------

    def set_categories(self, assignments: list[tuple[int, str]]) -> int:
        """Kategorien mehrerer Fensternutzungen setzen; gibt die Anzahl zurück."""
        if not assignments:
            return 0
        self.connection.executemany(
            "UPDATE window_events SET category = ? WHERE id = ?",
            [(category, event_id) for event_id, category in assignments],
        )
        return len(assignments)

    def save_daily_summary(
        self,
        day: date,
        *,
        total_active_minutes: int,
        category_breakdown: dict[str, int],
        top_distractions: list[dict[str, object]],
    ) -> None:
        """Tageszusammenfassung speichern oder aktualisieren."""
        self.connection.execute(
            """
            INSERT INTO daily_summaries
                   (date, total_active_minutes, category_breakdown, top_distractions)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                   total_active_minutes = excluded.total_active_minutes,
                   category_breakdown   = excluded.category_breakdown,
                   top_distractions     = excluded.top_distractions
            """,
            (
                day.isoformat(),
                total_active_minutes,
                json.dumps(category_breakdown, ensure_ascii=False),
                json.dumps(top_distractions, ensure_ascii=False),
            ),
        )

    def daily_summary(self, day: date) -> dict[str, object] | None:
        """Gespeicherte Tageszusammenfassung lesen."""
        row = self.connection.execute(
            "SELECT * FROM daily_summaries WHERE date = ?", (day.isoformat(),)
        ).fetchone()
        if row is None:
            return None
        return {
            "date": date.fromisoformat(row["date"]),
            "total_active_minutes": row["total_active_minutes"],
            "category_breakdown": json.loads(row["category_breakdown"] or "{}"),
            "top_distractions": json.loads(row["top_distractions"] or "[]"),
        }

    def replace_suggestions(
        self, day: date, source: str, entries: list[tuple[str, str | None]]
    ) -> int:
        """Vorschläge einer Quelle für einen Tag ersetzen.

        Bereits weggeklickte (``dismissed``) Vorschläge bleiben erhalten und
        werden nicht erneut angelegt.
        """
        dismissed = {
            row["suggestion_text"]
            for row in self.connection.execute(
                "SELECT suggestion_text FROM suggestions"
                " WHERE date = ? AND source = ? AND dismissed = 1",
                (day.isoformat(), source),
            )
        }
        self.connection.execute(
            "DELETE FROM suggestions WHERE date = ? AND source = ? AND dismissed = 0",
            (day.isoformat(), source),
        )
        neue = [(text, category) for text, category in entries if text not in dismissed]
        self.connection.executemany(
            "INSERT INTO suggestions (date, source, suggestion_text, category)"
            " VALUES (?, ?, ?, ?)",
            [(day.isoformat(), source, text, category) for text, category in neue],
        )
        return len(neue)

    def suggestions(
        self, *, day: date | None = None, include_dismissed: bool = False
    ) -> list[Suggestion]:
        """Vorschläge lesen, neueste zuerst."""
        query = "SELECT * FROM suggestions"
        conditions: list[str] = []
        params: list[object] = []
        if day is not None:
            conditions.append("date = ?")
            params.append(day.isoformat())
        if not include_dismissed:
            conditions.append("dismissed = 0")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY date DESC, id ASC"
        return [
            Suggestion(
                id=row["id"],
                date=date.fromisoformat(row["date"]),
                source=row["source"],
                text=row["suggestion_text"],
                category=row["category"],
                dismissed=bool(row["dismissed"]),
            )
            for row in self.connection.execute(query, params)
        ]

    def dismiss_suggestion(self, suggestion_id: int) -> bool:
        """Einen Vorschlag als erledigt markieren."""
        cursor = self.connection.execute(
            "UPDATE suggestions SET dismissed = 1 WHERE id = ?", (suggestion_id,)
        )
        return cursor.rowcount > 0

    def tracked_days(self) -> list[date]:
        """Alle lokalen Kalendertage mit Daten, neueste zuerst."""
        days = {
            timeutil.to_local(timeutil.parse(row["timestamp"])).date()
            for row in self.connection.execute("SELECT timestamp FROM window_events")
        }
        return sorted(days, reverse=True)
