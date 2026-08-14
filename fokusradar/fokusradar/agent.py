"""Der Tracker: die Erfassungsschleife.

Ablauf je Durchlauf (Standard: alle 3 Sekunden):

1. Idle-Zeit abfragen. Liegt sie über der Schwelle (Vorgabe 5 Minuten), gilt
   die Zeit als Pause: die laufende Fensternutzung wird **rückwirkend** auf den
   Zeitpunkt der letzten Eingabe beendet, damit Pausen nicht der zuletzt
   genutzten Anwendung zugerechnet werden.
2. Sonst das aktive Fenster abfragen und prüfen, ob es überhaupt erfasst werden
   darf: Programme der **Ausschlussliste** und die **Smart Pause** bei
   Videocalls stoppen die Aufzeichnung, bevor irgendetwas gespeichert wird.
3. Ist die Erfassung erlaubt und das Fenster dasselbe wie zuvor, wird nur das
   Ende fortgeschrieben; sonst wird die alte Nutzung beendet und eine neue
   begonnen.
4. In größerem Abstand (Vorgabe 60 Sekunden) einen Messpunkt des
   Aktivitätslevels schreiben (Idle-Sekunden, Anzahl Eingabe-Ereignisse) und
   — falls eingeschaltet — alle paar Minuten einen Screenshot mit lokaler
   Texterkennung.

Die Schleife ist über ``tick(now)`` schrittweise testbar; ``run()`` ist nur die
Hülle mit Schlaf und Abbruchbedingung.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fokusradar import timeutil
from fokusradar.capture import (
    create_idle_backend,
    create_input_counter,
    create_ocr_backend,
    create_screenshot_backend,
    create_window_backend,
)
from fokusradar.capture.base import IdleBackend, WindowBackend, WindowInfo
from fokusradar.capture.screenshots import (
    OcrBackend,
    ScreenshotBackend,
    clean_ocr_text,
    screenshot_filename,
)
from fokusradar.config import Config
from fokusradar.processing.categories import Categorizer
from fokusradar.processing.exclusions import ExclusionList
from fokusradar.storage.db import Database


@dataclass
class TrackerStats:
    """Zählwerte eines Laufs — für Statusausgabe und Tests."""

    ticks: int = 0
    window_events: int = 0
    activity_samples: int = 0
    idle_periods: int = 0
    excluded: int = 0
    smart_pauses: int = 0
    screenshots: int = 0


@dataclass
class _CurrentSession:
    event_id: int
    info: WindowInfo
    started_at: datetime
    last_seen_at: datetime = field(default_factory=timeutil.now_utc)


class Tracker:
    """Erfasst aktives Fenster und Aktivitätslevel in die lokale Datenbank."""

    def __init__(
        self,
        database: Database,
        config: Config,
        *,
        window_backend: WindowBackend | None = None,
        idle_backend: IdleBackend | None = None,
        input_counter: object | None = None,
        categorizer: Categorizer | None = None,
        exclusions: ExclusionList | None = None,
        screenshot_backend: ScreenshotBackend | None = None,
        ocr_backend: OcrBackend | None = None,
        on_event: Callable[[str], None] | None = None,
    ) -> None:
        self.db = database
        self.config = config
        self.window_backend = window_backend or create_window_backend()
        self.idle_backend = idle_backend or create_idle_backend()
        self.input_counter = input_counter or create_input_counter(
            config.capture.count_input_events
        )
        self.categorizer = categorizer or Categorizer.load(config.categories_path)
        self.exclusions = exclusions if exclusions is not None else database.exclusions()
        self.screenshot_backend = screenshot_backend or create_screenshot_backend(
            config.screenshots.enabled
        )
        self.ocr_backend = ocr_backend or create_ocr_backend(
            config.screenshots.enabled and config.screenshots.ocr,
            config.screenshots.ocr_languages,
        )
        self.stats = TrackerStats()
        self._on_event = on_event
        self._session: _CurrentSession | None = None
        self._idle_since: datetime | None = None
        self._last_activity_sample: datetime | None = None
        self._last_screenshot: datetime | None = None
        self._counting_inputs = False
        self._blocked_reason: str | None = None
        self._pause_processes = {
            name.casefold() for name in config.capture.pause_processes
        }

    # -- Lebenszyklus -------------------------------------------------------

    def start(self) -> None:
        """Vorbereiten: Reste früherer Läufe schließen, Zähler starten."""
        repaired = self.db.close_dangling_window_events()
        if repaired:
            self._notify(
                f"{repaired} offene Fenster-Sitzung(en) aus einem früheren Lauf abgeschlossen"
            )
        self._counting_inputs = bool(self.input_counter.start())

    def stop(self, now: datetime | None = None) -> None:
        """Laufende Nutzung sauber abschließen und Zähler stoppen."""
        moment = now or timeutil.now_utc()
        self._close_session(moment)
        self.input_counter.stop()
        self._counting_inputs = False

    # -- Erfassungsschritt --------------------------------------------------

    def tick(self, now: datetime | None = None) -> None:
        """Einen Erfassungsschritt ausführen."""
        moment = now or timeutil.now_utc()
        self.stats.ticks += 1

        idle_seconds = self.idle_backend.idle_seconds()
        threshold = self.config.capture.idle_threshold_seconds

        if idle_seconds is not None and idle_seconds >= threshold:
            self._handle_idle(moment, idle_seconds)
        else:
            self._idle_since = None
            self._handle_active(moment)

        self._maybe_sample_activity(moment, idle_seconds)
        self._maybe_take_screenshot(moment)

    def _handle_idle(self, now: datetime, idle_seconds: float) -> None:
        """Pause: laufende Nutzung rückwirkend beim letzten Input beenden."""
        if self._idle_since is None:
            self._idle_since = now - timedelta(seconds=idle_seconds)
            self.stats.idle_periods += 1
            if self._session is not None:
                self._notify(
                    f"Pause erkannt (seit {timeutil.format_duration(idle_seconds)} keine Eingabe)"
                )
            self._close_session(self._idle_since)

    def _handle_active(self, now: datetime) -> None:
        """Aktive Zeit: Fenster prüfen und Sitzung fortschreiben oder wechseln."""
        info = self.window_backend.snapshot()
        if info is None:
            # Kein Fenster ermittelbar (z. B. Sperrbildschirm): Sitzung beenden.
            self._close_session(now)
            self._blocked_reason = None
            return

        blocked = self._blocked_by(info)
        if blocked is not None:
            # Nichts speichern: weder Prozessname noch Titel noch Screenshot.
            self._close_session(now)
            if self._blocked_reason != blocked:
                self._blocked_reason = blocked
                self._notify(f"Erfassung ausgesetzt — {blocked}")
            return
        if self._blocked_reason is not None:
            self._blocked_reason = None
            self._notify("Erfassung läuft wieder")

        if not self.config.capture.store_window_titles:
            info = WindowInfo(process_name=info.process_name, window_title=None)

        session = self._session
        if session is not None and info.matches(session.info):
            session.last_seen_at = now
            self.db.touch_window_event(session.event_id, now)
            return

        self._close_session(now)
        category = self.categorizer.categorize(info.process_name, info.window_title)
        event_id = self.db.open_window_event(
            info,
            now,
            store_title=self.config.capture.store_window_titles,
            category=category,
        )
        self._session = _CurrentSession(
            event_id=event_id, info=info, started_at=now, last_seen_at=now
        )
        self.stats.window_events += 1
        self._notify(
            f"Fenster: {info.process_name} — {info.window_title or 'ohne Titel'} [{category}]"
        )

    def _close_session(self, at: datetime) -> None:
        session = self._session
        if session is None:
            return
        # Nie vor den Beginn zurückdatieren (Idle-Zeit kann älter sein).
        ended_at = max(at, session.started_at)
        self.db.close_window_event(session.event_id, ended_at)
        self._session = None

    def _maybe_sample_activity(self, now: datetime, idle_seconds: float | None) -> None:
        interval = self.config.capture.activity_interval_seconds
        last = self._last_activity_sample
        if last is not None and (now - last).total_seconds() < interval:
            return
        self._last_activity_sample = now
        input_events = self.input_counter.take() if self._counting_inputs else None
        self.db.record_activity(now, idle_seconds, input_events)
        self.stats.activity_samples += 1

    def _blocked_by(self, info: WindowInfo) -> str | None:
        """Grund, warum dieses Fenster nicht erfasst werden darf — oder ``None``.

        Geprüft wird ausschließlich im Arbeitsspeicher; nichts davon wird
        gespeichert.
        """
        if info.process_name.casefold() in self._pause_processes:
            self.stats.smart_pauses += 1
            return f"Smart Pause ({info.process_name})"
        rule = self.exclusions.matching_rule(info.process_name, info.window_title)
        if rule is not None:
            self.stats.excluded += 1
            return f"Ausschlussliste ({rule.label}-Muster {rule.pattern!r})"
        return None

    @property
    def blocked_reason(self) -> str | None:
        """Warum die Erfassung gerade ausgesetzt ist (für Status und Tray)."""
        return self._blocked_reason

    def _maybe_take_screenshot(self, now: datetime) -> None:
        """Aufnahme samt Texterkennung, wenn das Intervall abgelaufen ist."""
        settings = self.config.screenshots
        if not settings.enabled or not self.screenshot_backend.available():
            return
        if self._blocked_reason is not None or self._idle_since is not None:
            return  # während Ausschluss, Smart Pause und Pausen wird nichts aufgenommen
        if self._session is None:
            return  # nichts Erfassbares im Vordergrund
        last = self._last_screenshot
        if last is not None and (now - last).total_seconds() < settings.interval_seconds:
            return

        self._last_screenshot = now
        ziel = self.config.screenshot_dir / screenshot_filename(now)
        bild = self.screenshot_backend.capture(ziel)
        if bild is None:
            self._notify(
                "Screenshot fehlgeschlagen — "
                f"{self.screenshot_backend.unavailable_reason() or 'unbekannter Grund'}"
            )
            return

        text = clean_ocr_text(self.ocr_backend.text(bild), settings.text_max_length)
        geloescht = None
        pfad: str | None = str(bild)
        if settings.delete_image:
            try:
                bild.unlink()
                geloescht = now
                pfad = None
            except OSError as exc:  # pragma: no cover - Datei ist schon weg o. Ä.
                self._notify(f"Screenshot ließ sich nicht löschen: {exc}")

        self.db.record_screenshot(
            now, ocr_text=text, screenshot_path=pfad, deleted_at=geloescht
        )
        self.stats.screenshots += 1
        self._notify(
            "Screenshot: "
            + (f"{len(text)} Zeichen Text erkannt" if text else "kein Text erkannt")
            + (", Bild gelöscht" if geloescht else "")
        )

    # -- Dauerbetrieb -------------------------------------------------------

    def run(
        self,
        *,
        stop_event: threading.Event | None = None,
        max_ticks: int | None = None,
        duration_seconds: float | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> TrackerStats:
        """Erfassung laufen lassen, bis gestoppt wird.

        ``max_ticks`` und ``duration_seconds`` begrenzen den Lauf (praktisch für
        Tests und für ``fokusradar track --dauer``).
        """
        self.start()
        interval = self.config.capture.interval_seconds
        started = timeutil.now_utc()
        try:
            while True:
                self.tick()
                if max_ticks is not None and self.stats.ticks >= max_ticks:
                    break
                if duration_seconds is not None:
                    elapsed = (timeutil.now_utc() - started).total_seconds()
                    if elapsed >= duration_seconds:
                        break
                if stop_event is not None:
                    if stop_event.wait(interval):
                        break
                else:
                    sleeper(interval)
        finally:
            self.stop()
        return self.stats

    # -- Hilfen -------------------------------------------------------------

    def _notify(self, message: str) -> None:
        if self._on_event is not None:
            self._on_event(message)

    def backend_report(self) -> list[tuple[str, str]]:
        """Zustand der Backends als (Name, Beschreibung) für die Statusanzeige."""
        report = []
        for label, backend in (
            ("Fenster-Erfassung", self.window_backend),
            ("Idle-Erkennung", self.idle_backend),
            ("Eingabe-Zählung", self.input_counter),
            ("Screenshots", self.screenshot_backend),
            ("Texterkennung", self.ocr_backend),
        ):
            if backend.available():  # type: ignore[union-attr]
                report.append((label, f"aktiv ({backend.name})"))  # type: ignore[union-attr]
            else:
                reason = backend.unavailable_reason() or "nicht verfügbar"  # type: ignore[union-attr]
                report.append((label, f"inaktiv — {reason}"))
        return report
