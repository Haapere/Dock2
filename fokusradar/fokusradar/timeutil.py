"""Zeit-Hilfsfunktionen.

Konvention: In der Datenbank stehen alle Zeitstempel als ISO-8601 in **UTC**
(``2026-08-13T20:15:03+00:00``). Für Anzeige und Tagesgruppierung wird in die
lokale Zeitzone umgerechnet — so bleiben Sortierung und Vergleiche in SQL auch
über Sommerzeit-Wechsel hinweg korrekt.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone


def now_utc() -> datetime:
    """Aktueller Zeitpunkt als zeitzonenbewusster UTC-Wert."""
    return datetime.now(timezone.utc)


def to_utc(moment: datetime) -> datetime:
    """Beliebigen Zeitstempel nach UTC bringen (naive Werte gelten als lokal)."""
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment.astimezone(timezone.utc)


def to_local(moment: datetime) -> datetime:
    """Zeitstempel in die lokale Zeitzone umrechnen."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc).astimezone()
    return moment.astimezone()


def isoformat(moment: datetime) -> str:
    """Zeitstempel im DB-Format (UTC, ISO-8601, Sekundenauflösung)."""
    return to_utc(moment).replace(microsecond=0).isoformat()


def parse(value: str) -> datetime:
    """DB-Zeitstempel zurück in ein ``datetime`` (UTC) wandeln."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def local_day_bounds(day: date) -> tuple[str, str]:
    """UTC-Grenzen (einschließlich/ausschließlich) eines lokalen Kalendertages."""
    start_local = datetime.combine(day, time.min).astimezone()
    end_local = datetime.combine(day + timedelta(days=1), time.min).astimezone()
    return isoformat(start_local), isoformat(end_local)


def parse_day(value: str, today: date | None = None) -> date:
    """Tagesangabe der Kommandozeile lesen: ``heute``/``today``, ``gestern``/
    ``yesterday``, ``-2`` (vor zwei Tagen) oder ``YYYY-MM-DD``."""
    reference = today or datetime.now().astimezone().date()
    text = value.strip().lower()
    if text in {"heute", "today"}:
        return reference
    if text in {"gestern", "yesterday"}:
        return reference - timedelta(days=1)
    if text.startswith("-") and text[1:].isdigit():
        return reference - timedelta(days=int(text[1:]))
    try:
        return date.fromisoformat(text)
    except ValueError as exc:  # pragma: no cover - Argparse zeigt die Meldung
        raise ValueError(
            f"Unverständliche Tagesangabe: {value!r} "
            "(erwartet: heute, gestern, -3 oder JJJJ-MM-TT)"
        ) from exc


def format_duration(seconds: float) -> str:
    """Sekunden als kompakte Dauer, z. B. ``1h 05m`` oder ``42s``."""
    total = int(round(seconds))
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"
