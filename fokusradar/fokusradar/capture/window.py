"""Erfassung des aktiven Fensters.

Primärsystem ist Windows; dort wird ausschließlich die Windows-API über
``ctypes`` genutzt, sodass für Phase 1 keine Zusatzpakete nötig sind.
Für Entwicklung und Tests unter Linux gibt es ein X11-Backend auf Basis von
``xdotool``/``xprop``.

Erfasst werden nur Prozessname und Fenstertitel — keine Tastatureingaben und
keine Fensterinhalte.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from fokusradar.capture.base import NullWindowBackend, WindowBackend, WindowInfo

_TITLE_MAX_LENGTH = 500


def _clean_title(title: str | None) -> str | None:
    """Titel normalisieren: Leerzeichen kürzen, sehr lange Titel beschneiden."""
    if title is None:
        return None
    cleaned = " ".join(title.split())
    if not cleaned:
        return None
    if len(cleaned) > _TITLE_MAX_LENGTH:
        cleaned = cleaned[: _TITLE_MAX_LENGTH - 1] + "…"
    return cleaned


class WindowsWindowBackend:
    """Aktives Fenster über die Win32-API (``user32``/``kernel32``)."""

    name = "windows"

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def __init__(self) -> None:
        self._reason: str | None = None
        self._process_names: dict[int, str] = {}
        self._user32 = None
        self._kernel32 = None
        if sys.platform != "win32":
            self._reason = "läuft nur unter Windows"
            return
        try:  # pragma: no cover - nur unter Windows ausführbar
            import ctypes
            from ctypes import wintypes

            self._ctypes = ctypes
            self._wintypes = wintypes
            self._user32 = ctypes.WinDLL("user32", use_last_error=True)
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._user32.GetForegroundWindow.restype = wintypes.HWND
            self._user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            self._user32.GetWindowTextW.argtypes = [
                wintypes.HWND,
                wintypes.LPWSTR,
                ctypes.c_int,
            ]
            self._user32.GetWindowThreadProcessId.argtypes = [
                wintypes.HWND,
                ctypes.POINTER(wintypes.DWORD),
            ]
            self._kernel32.OpenProcess.restype = wintypes.HANDLE
            self._kernel32.QueryFullProcessImageNameW.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.LPWSTR,
                ctypes.POINTER(wintypes.DWORD),
            ]
        except (ImportError, OSError, AttributeError) as exc:  # pragma: no cover
            self._reason = f"Win32-API nicht erreichbar: {exc}"
            self._user32 = None

    def available(self) -> bool:
        return self._user32 is not None

    def unavailable_reason(self) -> str | None:
        return self._reason

    def snapshot(self) -> WindowInfo | None:  # pragma: no cover - nur Windows
        if self._user32 is None:
            return None
        ctypes = self._ctypes
        wintypes = self._wintypes

        hwnd = self._user32.GetForegroundWindow()
        if not hwnd:
            return None

        length = self._user32.GetWindowTextLengthW(hwnd)
        title = None
        if length > 0:
            buffer = ctypes.create_unicode_buffer(length + 1)
            if self._user32.GetWindowTextW(hwnd, buffer, length + 1):
                title = buffer.value

        pid = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = self._process_name(int(pid.value))
        if process_name is None:
            return None
        return WindowInfo(process_name=process_name, window_title=_clean_title(title))

    def _process_name(self, pid: int) -> str | None:  # pragma: no cover - nur Windows
        if pid <= 0:
            return None
        cached = self._process_names.get(pid)
        if cached is not None:
            return cached

        ctypes = self._ctypes
        wintypes = self._wintypes
        handle = self._kernel32.OpenProcess(
            self._PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return "unbekannt"
        try:
            size = wintypes.DWORD(1024)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not self._kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                return "unbekannt"
            name = Path(buffer.value).name or "unbekannt"
        finally:
            self._kernel32.CloseHandle(handle)

        # PIDs werden wiederverwendet; der Cache bleibt daher klein und wird
        # bei Bedarf komplett verworfen.
        if len(self._process_names) > 512:
            self._process_names.clear()
        self._process_names[pid] = name
        return name


class X11WindowBackend:
    """Aktives Fenster unter X11 — für Entwicklung und Tests unter Linux.

    Nutzt ``xdotool``, falls vorhanden, sonst ``xprop``. Unter Wayland liefern
    beide Werkzeuge in der Regel nichts; dann bleibt das Backend inaktiv.
    """

    name = "x11"

    def __init__(self, *, display: str | None = None) -> None:
        self._reason: str | None = None
        self._tool: str | None = None
        if display is None:
            display = os.environ.get("DISPLAY")
        if not display:
            self._reason = "keine X11-Anzeige gefunden (DISPLAY ist leer)"
            return
        if shutil.which("xdotool"):
            self._tool = "xdotool"
        elif shutil.which("xprop"):
            self._tool = "xprop"
        else:
            self._reason = "weder xdotool noch xprop installiert"

    def available(self) -> bool:
        return self._tool is not None

    def unavailable_reason(self) -> str | None:
        return self._reason

    def snapshot(self) -> WindowInfo | None:
        if self._tool == "xdotool":
            return self._snapshot_xdotool()
        if self._tool == "xprop":
            return self._snapshot_xprop()
        return None

    @staticmethod
    def _run(command: list[str]) -> str | None:
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=5, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        return completed.stdout

    def _snapshot_xdotool(self) -> WindowInfo | None:
        output = self._run(
            ["xdotool", "getactivewindow", "getwindowpid", "getwindowname"]
        )
        if not output:
            return None
        lines = output.splitlines()
        if not lines:
            return None
        pid_text = lines[0].strip()
        title = "\n".join(lines[1:]) if len(lines) > 1 else None
        process_name = _process_name_from_proc(pid_text)
        if process_name is None:
            return None
        return WindowInfo(process_name=process_name, window_title=_clean_title(title))

    def _snapshot_xprop(self) -> WindowInfo | None:
        root = self._run(["xprop", "-root", "_NET_ACTIVE_WINDOW"])
        if not root or "0x" not in root:
            return None
        window_id = root.rsplit("0x", 1)[-1].strip()
        details = self._run(
            ["xprop", "-id", f"0x{window_id}", "_NET_WM_PID", "_NET_WM_NAME"]
        )
        if not details:
            return None
        pid_text: str | None = None
        title: str | None = None
        for line in details.splitlines():
            if line.startswith("_NET_WM_PID") and "=" in line:
                pid_text = line.split("=", 1)[1].strip()
            elif line.startswith("_NET_WM_NAME") and "=" in line:
                title = line.split("=", 1)[1].strip().strip('"')
        process_name = _process_name_from_proc(pid_text)
        if process_name is None:
            return None
        return WindowInfo(process_name=process_name, window_title=_clean_title(title))


def _process_name_from_proc(pid_text: str | None) -> str | None:
    """Prozessnamen zu einer PID über ``/proc`` ermitteln."""
    if not pid_text or not pid_text.isdigit():
        return None
    try:
        return Path(f"/proc/{pid_text}/comm").read_text(encoding="utf-8").strip() or None
    except OSError:
        return "unbekannt"


def create_window_backend() -> WindowBackend:
    """Passendes Fenster-Backend für dieses System auswählen."""
    if sys.platform == "win32":
        backend = WindowsWindowBackend()
        if backend.available():
            return backend
        return NullWindowBackend(backend.unavailable_reason() or "Win32-API nicht nutzbar")
    if sys.platform.startswith("linux"):
        backend = X11WindowBackend()
        if backend.available():
            return backend
        return NullWindowBackend(backend.unavailable_reason() or "kein X11-Backend")
    return NullWindowBackend(
        f"für {sys.platform} gibt es in Phase 1 noch kein Fenster-Backend"
    )
