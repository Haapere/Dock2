"""Zugriff auf die lokale SQLite-Datenbank.

Alle Rohdaten bleiben in dieser Datei auf dem Gerät. Auf Wunsch verschlüsselt
FokusRadar sie mit SQLCipher (``[speicher] verschluesselt = true``, siehe
``fokusradar.storage.crypto``).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from fokusradar import timeutil
from fokusradar.capture.base import WindowInfo
from fokusradar.processing.exclusions import ExclusionList, ExclusionRule
from fokusradar.storage import crypto
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
class ScreenshotRecord:
    """Ein Screenshot-Eintrag: erkannter Text und Verbleib des Bildes."""

    id: int
    timestamp: datetime
    ocr_text: str | None
    screenshot_path: str | None
    deleted_at: datetime | None

    @property
    def image_available(self) -> bool:
        return self.screenshot_path is not None and self.deleted_at is None


@dataclass(frozen=True)
class ApiUsage:
    """Ein Aufruf der Claude-API mit Verbrauch und geschätzten Kosten."""

    id: int
    timestamp: datetime
    date: date
    kind: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float


@dataclass(frozen=True)
class AndroidUsage:
    """App-Nutzung eines Tages auf dem Handy."""

    id: int
    date: date
    device: str
    package_name: str
    app_label: str | None
    seconds: int
    opens: int
    category: str | None
    synced_at: datetime

    @property
    def label(self) -> str:
        """Lesbarer Name, notfalls der Paketname."""
        return self.app_label or self.package_name


@dataclass(frozen=True)
class AppTotal:
    """Aufsummierte Nutzung eines Programms in einem Zeitraum."""

    process_name: str
    seconds: int
    events: int


class DatabaseLocked(RuntimeError):
    """Die Datenbank lässt sich mit diesem Schlüssel nicht öffnen."""

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"{path} lässt sich mit dem hinterlegten Schlüssel nicht öffnen.\n"
            "Stimmt die Schlüsseldatei (bzw. FOKUSRADAR_KEY)? Ist die Datenbank "
            "überhaupt schon verschlüsselt? Umstellen: fokusradar verschluesseln"
        )


class Database:
    """Schmale Hülle um ``sqlite3`` mit den Abfragen von FokusRadar."""

    def __init__(
        self, path: Path | str, *, encrypted: bool = False, key: str | None = None
    ) -> None:
        self.path = Path(path).expanduser()
        self.encrypted = encrypted
        self._key = key
        self._connection: sqlite3.Connection | None = None

    @classmethod
    def from_config(cls, config) -> "Database":
        """Datenbank gemäß Konfiguration öffnen — inklusive Verschlüsselung."""
        if not config.storage.encrypted:
            return cls(config.database_path)
        return cls(
            config.database_path,
            encrypted=True,
            key=crypto.load_or_create_key(config.key_file),
        )

    # -- Verbindung ---------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        """Verbindung öffnen (idempotent) und Schema sicherstellen."""
        if self._connection is not None:
            return self._connection
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.encrypted:
            module = crypto.sqlcipher_module()
            connection = module.connect(str(self.path), isolation_level=None)
            crypto.apply_key(connection, self._key or "")
            try:
                connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
            except Exception as exc:  # sqlcipher meldet "file is not a database"
                connection.close()
                raise DatabaseLocked(self.path) from exc
            # SQLCipher bringt eine eigene Row-Klasse mit; sqlite3.Row passt nicht
            # zu dessen Cursor.
            connection.row_factory = module.Row
        else:
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
            "api_usage",
            "android_usage",
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

    # -- Ausschlussliste und Screenshots (Phase 3) ---------------------------

    def exclusions(self) -> ExclusionList:
        """Gültige Ausschlussliste aus der Datenbank."""
        return ExclusionList(
            [
                ExclusionRule(
                    pattern=row["pattern"],
                    pattern_type=row["pattern_type"],
                    id=row["id"],
                )
                for row in self.connection.execute(
                    "SELECT * FROM exclusion_list ORDER BY pattern_type, pattern"
                )
            ]
        )

    def add_exclusion(self, pattern: str, pattern_type: str = "process") -> int | None:
        """Muster aufnehmen; gibt die ID zurück (``None``, wenn schon vorhanden)."""
        rule = ExclusionRule(pattern.strip(), pattern_type)
        vorhanden = self.connection.execute(
            "SELECT id FROM exclusion_list WHERE pattern = ? AND pattern_type = ?",
            (rule.pattern, rule.pattern_type),
        ).fetchone()
        if vorhanden is not None:
            return None
        cursor = self.connection.execute(
            "INSERT INTO exclusion_list (pattern, pattern_type) VALUES (?, ?)",
            (rule.pattern, rule.pattern_type),
        )
        return int(cursor.lastrowid)

    def remove_exclusion(self, exclusion_id: int) -> bool:
        """Muster löschen."""
        cursor = self.connection.execute(
            "DELETE FROM exclusion_list WHERE id = ?", (exclusion_id,)
        )
        return cursor.rowcount > 0

    def seed_exclusions(self, template: ExclusionList) -> int:
        """Vorlage übernehmen, solange die Liste leer ist.

        Gibt die Anzahl der übernommenen Muster zurück (0, wenn schon etwas
        drinsteht — eine gepflegte Liste wird nie überschrieben).
        """
        if len(self.exclusions()) > 0:
            return 0
        uebernommen = 0
        for rule in template:
            if self.add_exclusion(rule.pattern, rule.pattern_type) is not None:
                uebernommen += 1
        return uebernommen

    def record_screenshot(
        self,
        at: datetime,
        *,
        ocr_text: str | None = None,
        screenshot_path: str | None = None,
        deleted_at: datetime | None = None,
    ) -> int:
        """Screenshot-Eintrag speichern (Text und/oder Ablageort des Bildes)."""
        cursor = self.connection.execute(
            "INSERT INTO screenshots_meta (timestamp, ocr_text, screenshot_path, deleted_at)"
            " VALUES (?, ?, ?, ?)",
            (
                timeutil.isoformat(at),
                ocr_text,
                screenshot_path,
                timeutil.isoformat(deleted_at) if deleted_at else None,
            ),
        )
        return int(cursor.lastrowid)

    def mark_screenshot_deleted(self, screenshot_id: int, at: datetime) -> None:
        """Vermerken, dass das Bild gelöscht wurde (der Text bleibt)."""
        self.connection.execute(
            "UPDATE screenshots_meta SET deleted_at = ? WHERE id = ?",
            (timeutil.isoformat(at), screenshot_id),
        )

    def screenshots(
        self, *, day: date | None = None, limit: int | None = None
    ) -> list[ScreenshotRecord]:
        """Screenshot-Einträge, neueste zuerst."""
        query = "SELECT * FROM screenshots_meta"
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
            ScreenshotRecord(
                id=row["id"],
                timestamp=timeutil.parse(row["timestamp"]),
                ocr_text=row["ocr_text"],
                screenshot_path=row["screenshot_path"],
                deleted_at=timeutil.parse(row["deleted_at"]) if row["deleted_at"] else None,
            )
            for row in self.connection.execute(query, params)
        ]

    # -- Cloud-Verbrauch (Phase 4) ------------------------------------------

    def record_api_usage(
        self,
        at: datetime,
        *,
        day: date,
        kind: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> int:
        """Einen API-Aufruf mit Verbrauch und Kosten festhalten."""
        cursor = self.connection.execute(
            """
            INSERT INTO api_usage
                   (timestamp, date, kind, model, input_tokens, output_tokens,
                    cache_read_tokens, cache_write_tokens, cost_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timeutil.isoformat(at),
                day.isoformat(),
                kind,
                model,
                int(input_tokens),
                int(output_tokens),
                int(cache_read_tokens),
                int(cache_write_tokens),
                float(cost_usd),
            ),
        )
        return int(cursor.lastrowid)

    def api_usage(self, *, limit: int | None = None, since: date | None = None) -> list[ApiUsage]:
        """Aufrufe der Claude-API, neueste zuerst."""
        query = "SELECT * FROM api_usage"
        params: list[object] = []
        if since is not None:
            query += " WHERE date >= ?"
            params.append(since.isoformat())
        query += " ORDER BY timestamp DESC, id DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        return [
            ApiUsage(
                id=row["id"],
                timestamp=timeutil.parse(row["timestamp"]),
                date=date.fromisoformat(row["date"]),
                kind=row["kind"],
                model=row["model"],
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
                cache_read_tokens=row["cache_read_tokens"],
                cache_write_tokens=row["cache_write_tokens"],
                cost_usd=row["cost_usd"],
            )
            for row in self.connection.execute(query, params)
        ]

    def api_cost_summary(self, *, since: date | None = None) -> dict[str, object]:
        """Summen über alle Aufrufe: Anzahl, Token, Kosten, Zeitraum."""
        query = (
            "SELECT COUNT(*) AS aufrufe,"
            " COALESCE(SUM(input_tokens), 0) AS input_tokens,"
            " COALESCE(SUM(output_tokens), 0) AS output_tokens,"
            " COALESCE(SUM(cost_usd), 0) AS kosten,"
            " MIN(date) AS von, MAX(date) AS bis"
            " FROM api_usage"
        )
        params: list[object] = []
        if since is not None:
            query += " WHERE date >= ?"
            params.append(since.isoformat())
        row = self.connection.execute(query, params).fetchone()
        return {
            "aufrufe": int(row["aufrufe"]),
            "input_tokens": int(row["input_tokens"]),
            "output_tokens": int(row["output_tokens"]),
            "kosten_usd": float(row["kosten"]),
            "von": date.fromisoformat(row["von"]) if row["von"] else None,
            "bis": date.fromisoformat(row["bis"]) if row["bis"] else None,
        }

    def has_cloud_suggestions(self, day: date) -> bool:
        """Gibt es für diesen Tag schon Cloud-Vorschläge?"""
        row = self.connection.execute(
            "SELECT 1 FROM suggestions WHERE date = ? AND source = 'cloud' LIMIT 1",
            (day.isoformat(),),
        ).fetchone()
        return row is not None

    def last_api_call(self, kind: str | None = None) -> ApiUsage | None:
        """Letzter Aufruf, optional nach Art (``taeglich``/``woche``) gefiltert."""
        query = "SELECT * FROM api_usage"
        params: list[object] = []
        if kind is not None:
            query += " WHERE kind = ?"
            params.append(kind)
        query += " ORDER BY timestamp DESC, id DESC LIMIT 1"
        row = self.connection.execute(query, params).fetchone()
        if row is None:
            return None
        return ApiUsage(
            id=row["id"],
            timestamp=timeutil.parse(row["timestamp"]),
            date=date.fromisoformat(row["date"]),
            kind=row["kind"],
            model=row["model"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            cache_read_tokens=row["cache_read_tokens"],
            cache_write_tokens=row["cache_write_tokens"],
            cost_usd=row["cost_usd"],
        )

    # -- Android-Begleiter (Phase 5) ----------------------------------------

    def record_android_usage(
        self,
        day: date,
        device: str,
        entries: list[dict[str, object]],
        *,
        synced_at: datetime,
        categorizer=None,
    ) -> int:
        """App-Nutzung eines Handy-Tages speichern (ersetzt vorhandene Zeilen).

        Ein erneuter Sync desselben Tages überschreibt die alten Werte — das
        Handy schickt immer den Stand des ganzen Tages, nicht die Differenz.
        """
        gespeichert = 0
        for eintrag in entries:
            paket = str(eintrag.get("package") or "").strip()
            if not paket:
                continue
            label = eintrag.get("label")
            kategorie = (
                categorizer.categorize(paket, str(label) if label else None)
                if categorizer is not None
                else None
            )
            self.connection.execute(
                """
                INSERT INTO android_usage
                       (date, device, package_name, app_label, seconds, opens,
                        category, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, device, package_name) DO UPDATE SET
                       app_label = excluded.app_label,
                       seconds   = excluded.seconds,
                       opens     = excluded.opens,
                       category  = excluded.category,
                       synced_at = excluded.synced_at
                """,
                (
                    day.isoformat(),
                    device,
                    paket,
                    str(label) if label else None,
                    max(0, int(eintrag.get("seconds") or 0)),
                    max(0, int(eintrag.get("opens") or 0)),
                    kategorie,
                    timeutil.isoformat(synced_at),
                ),
            )
            gespeichert += 1
        return gespeichert

    def android_usage(
        self, *, day: date | None = None, device: str | None = None, limit: int | None = None
    ) -> list[AndroidUsage]:
        """App-Nutzung des Handys, längste zuerst."""
        query = "SELECT * FROM android_usage"
        bedingungen: list[str] = []
        params: list[object] = []
        if day is not None:
            bedingungen.append("date = ?")
            params.append(day.isoformat())
        if device is not None:
            bedingungen.append("device = ?")
            params.append(device)
        if bedingungen:
            query += " WHERE " + " AND ".join(bedingungen)
        query += " ORDER BY date DESC, seconds DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        return [
            AndroidUsage(
                id=row["id"],
                date=date.fromisoformat(row["date"]),
                device=row["device"],
                package_name=row["package_name"],
                app_label=row["app_label"],
                seconds=row["seconds"],
                opens=row["opens"],
                category=row["category"],
                synced_at=timeutil.parse(row["synced_at"]),
            )
            for row in self.connection.execute(query, params)
        ]

    def android_devices(self) -> list[tuple[str, datetime, date]]:
        """Bekannte Geräte mit letztem Sync und letztem erfassten Tag."""
        return [
            (
                row["device"],
                timeutil.parse(row["synced_at"]),
                date.fromisoformat(row["letzter_tag"]),
            )
            for row in self.connection.execute(
                "SELECT device, MAX(synced_at) AS synced_at, MAX(date) AS letzter_tag"
                " FROM android_usage GROUP BY device ORDER BY synced_at DESC"
            )
        ]

    def android_day_seconds(self, day: date) -> int:
        """Gesamte Handy-Nutzung eines Tages in Sekunden."""
        row = self.connection.execute(
            "SELECT COALESCE(SUM(seconds), 0) AS s FROM android_usage WHERE date = ?",
            (day.isoformat(),),
        ).fetchone()
        return int(row["s"])

    def tracked_days(self) -> list[date]:
        """Alle lokalen Kalendertage mit Daten, neueste zuerst."""
        days = {
            timeutil.to_local(timeutil.parse(row["timestamp"])).date()
            for row in self.connection.execute("SELECT timestamp FROM window_events")
        }
        return sorted(days, reverse=True)
