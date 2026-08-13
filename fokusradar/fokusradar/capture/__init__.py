"""Erfassungs-Schicht: aktives Fenster, Idle-Zeit, Eingabe-Frequenz."""

from fokusradar.capture.base import IdleBackend, WindowBackend, WindowInfo
from fokusradar.capture.idle import create_idle_backend
from fokusradar.capture.input_counter import InputCounter, create_input_counter
from fokusradar.capture.window import create_window_backend

__all__ = [
    "IdleBackend",
    "InputCounter",
    "WindowBackend",
    "WindowInfo",
    "create_idle_backend",
    "create_input_counter",
    "create_window_backend",
]
