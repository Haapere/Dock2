"""Gemeinsame Typen der Erfassungs-Schicht.

Die Erfassung ist hinter schmalen Schnittstellen gekapselt: Der Tracker kennt
nur ``WindowBackend`` und ``IdleBackend``. Dadurch läuft dieselbe Logik unter
Windows (pywin32/ctypes), unter Linux (X11) und in Tests mit Attrappen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class WindowInfo:
    """Momentaufnahme des aktiven Fensters."""

    process_name: str
    window_title: str | None = None

    def matches(self, other: "WindowInfo | None") -> bool:
        """Beschreiben beide Aufnahmen dasselbe Fenster?"""
        if other is None:
            return False
        return (
            self.process_name == other.process_name
            and self.window_title == other.window_title
        )


@runtime_checkable
class WindowBackend(Protocol):
    """Liefert das gerade aktive Fenster."""

    name: str

    def available(self) -> bool:
        """Kann dieses Backend auf diesem System erfassen?"""

    def unavailable_reason(self) -> str | None:
        """Klartext-Begründung, falls nicht verfügbar."""

    def snapshot(self) -> WindowInfo | None:
        """Aktives Fenster; ``None``, wenn gerade keins ermittelbar ist."""


@runtime_checkable
class IdleBackend(Protocol):
    """Liefert die Zeit seit der letzten Maus-/Tastatureingabe."""

    name: str

    def available(self) -> bool:
        """Kann dieses Backend auf diesem System messen?"""

    def unavailable_reason(self) -> str | None:
        """Klartext-Begründung, falls nicht verfügbar."""

    def idle_seconds(self) -> float | None:
        """Sekunden ohne Eingabe; ``None``, wenn nicht messbar."""


class _Unavailable:
    """Gemeinsame Basis für Attrappen ohne Erfassungsmöglichkeit."""

    name = "keins"

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def available(self) -> bool:
        return False

    def unavailable_reason(self) -> str | None:
        return self._reason


class NullWindowBackend(_Unavailable):
    """Platzhalter, wenn kein Fenster-Backend nutzbar ist."""

    def snapshot(self) -> WindowInfo | None:
        return None


class NullIdleBackend(_Unavailable):
    """Platzhalter, wenn keine Idle-Messung möglich ist."""

    def idle_seconds(self) -> float | None:
        return None
