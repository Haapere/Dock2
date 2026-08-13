"""Tests der Erfassungs-Backends, soweit sie ohne Bildschirm prüfbar sind."""

from __future__ import annotations

import os

import pytest

from fokusradar.capture.base import WindowInfo
from fokusradar.capture.idle import X11IdleBackend, create_idle_backend
from fokusradar.capture.input_counter import NullInputCounter, create_input_counter
from fokusradar.capture.window import (
    X11WindowBackend,
    _clean_title,
    _process_name_from_proc,
    create_window_backend,
)


def test_windowinfo_vergleicht_prozess_und_titel():
    info = WindowInfo("code.exe", "main.py")
    assert info.matches(WindowInfo("code.exe", "main.py"))
    assert not info.matches(WindowInfo("code.exe", "test.py"))
    assert not info.matches(WindowInfo("firefox.exe", "main.py"))
    assert not info.matches(None)


def test_titel_wird_normalisiert():
    assert _clean_title("  main.py   —   Editor ") == "main.py — Editor"
    assert _clean_title("   ") is None
    assert _clean_title(None) is None
    lang = _clean_title("x" * 800)
    assert len(lang) == 500 and lang.endswith("…")


def test_prozessname_aus_proc():
    eigene_pid = str(os.getpid())
    assert _process_name_from_proc(eigene_pid)  # z. B. "python3"
    assert _process_name_from_proc("keine-zahl") is None
    assert _process_name_from_proc(None) is None
    assert _process_name_from_proc("999999999") == "unbekannt"


def test_ohne_display_bleiben_die_x11_backends_inaktiv(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)

    fenster = X11WindowBackend()
    assert not fenster.available()
    assert "DISPLAY" in (fenster.unavailable_reason() or "")
    assert fenster.snapshot() is None

    idle = X11IdleBackend()
    assert not idle.available()
    assert idle.idle_seconds() is None


@pytest.mark.skipif(os.name == "nt", reason="prüft die Auswahl unter Linux")
def test_backend_auswahl_liefert_immer_ein_objekt(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    fenster = create_window_backend()
    idle = create_idle_backend()

    # Ohne Anzeige sind es Attrappen — aber die Schnittstelle stimmt.
    assert fenster.snapshot() is None
    assert idle.idle_seconds() is None
    assert fenster.unavailable_reason()
    assert idle.unavailable_reason()


def test_eingabe_zaehlung_laesst_sich_abschalten():
    zaehler = create_input_counter(False)
    assert isinstance(zaehler, NullInputCounter)
    assert not zaehler.available()
    assert zaehler.start() is False
    assert zaehler.take() is None
    assert "abgeschaltet" in (zaehler.unavailable_reason() or "")
