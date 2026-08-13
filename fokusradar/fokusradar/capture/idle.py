"""Idle-Erkennung: Sekunden seit der letzten Maus-/Tastatureingabe.

Gemessen wird ausschließlich der *Zeitpunkt* der letzten Eingabe — welche Taste
gedrückt wurde, erfährt FokusRadar nicht.

* Windows: ``GetLastInputInfo`` (Win32-API über ``ctypes``)
* Linux/X11: XScreenSaver-Erweiterung, ersatzweise ``xprintidle``
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from fokusradar.capture.base import IdleBackend, NullIdleBackend


class WindowsIdleBackend:
    """Idle-Zeit über ``GetLastInputInfo``."""

    name = "windows"

    def __init__(self) -> None:
        self._reason: str | None = None
        self._user32 = None
        if sys.platform != "win32":
            self._reason = "läuft nur unter Windows"
            return
        try:  # pragma: no cover - nur unter Windows ausführbar
            import ctypes
            from ctypes import wintypes

            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

            self._ctypes = ctypes
            self._struct = LASTINPUTINFO
            self._user32 = ctypes.WinDLL("user32", use_last_error=True)
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
            self._user32.GetLastInputInfo.restype = wintypes.BOOL
            self._kernel32.GetTickCount.restype = wintypes.DWORD
        except (ImportError, OSError, AttributeError) as exc:  # pragma: no cover
            self._reason = f"Win32-API nicht erreichbar: {exc}"
            self._user32 = None

    def available(self) -> bool:
        return self._user32 is not None

    def unavailable_reason(self) -> str | None:
        return self._reason

    def idle_seconds(self) -> float | None:  # pragma: no cover - nur Windows
        if self._user32 is None:
            return None
        info = self._struct()
        info.cbSize = self._ctypes.sizeof(self._struct)
        if not self._user32.GetLastInputInfo(self._ctypes.byref(info)):
            return None
        # GetTickCount läuft nach ~49 Tagen über; die Maskierung auf 32 Bit
        # liefert auch über den Überlauf hinweg die richtige Differenz.
        elapsed_ms = (self._kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF
        return elapsed_ms / 1000.0


class X11IdleBackend:
    """Idle-Zeit unter X11 über die XScreenSaver-Erweiterung."""

    name = "x11"

    def __init__(self, *, display: str | None = None) -> None:
        self._reason: str | None = None
        self._query = None
        self._display_ptr = None
        self._info_ptr = None
        self._fallback_tool: str | None = None

        if display is None:
            display = os.environ.get("DISPLAY")
        if not display:
            self._reason = "keine X11-Anzeige gefunden (DISPLAY ist leer)"
            return
        if not self._setup_xss():
            if shutil.which("xprintidle"):
                self._fallback_tool = "xprintidle"
                self._reason = None
            elif self._reason is None:
                self._reason = "XScreenSaver nicht verfügbar und xprintidle fehlt"

    def _setup_xss(self) -> bool:
        try:
            import ctypes
            import ctypes.util

            class XScreenSaverInfo(ctypes.Structure):
                _fields_ = [
                    ("window", ctypes.c_ulong),
                    ("state", ctypes.c_int),
                    ("kind", ctypes.c_int),
                    ("since", ctypes.c_ulong),
                    ("idle", ctypes.c_ulong),
                    ("event_mask", ctypes.c_ulong),
                ]

            x11_name = ctypes.util.find_library("X11")
            xss_name = ctypes.util.find_library("Xss")
            if not x11_name or not xss_name:
                self._reason = "libX11/libXss nicht gefunden"
                return False
            x11 = ctypes.cdll.LoadLibrary(x11_name)
            xss = ctypes.cdll.LoadLibrary(xss_name)
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            x11.XDefaultRootWindow.restype = ctypes.c_ulong
            xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(XScreenSaverInfo)
            xss.XScreenSaverQueryInfo.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.POINTER(XScreenSaverInfo),
            ]

            display_ptr = x11.XOpenDisplay(None)
            if not display_ptr:
                self._reason = "X11-Anzeige lässt sich nicht öffnen"
                return False
            self._display_ptr = display_ptr
            self._root = x11.XDefaultRootWindow(ctypes.c_void_p(display_ptr))
            self._info_ptr = xss.XScreenSaverAllocInfo()
            self._query = xss.XScreenSaverQueryInfo
            return True
        except (ImportError, OSError, AttributeError) as exc:
            self._reason = f"XScreenSaver nicht nutzbar: {exc}"
            return False

    def available(self) -> bool:
        return self._query is not None or self._fallback_tool is not None

    def unavailable_reason(self) -> str | None:
        return self._reason

    def idle_seconds(self) -> float | None:
        if self._query is not None:
            import ctypes

            if not self._query(
                ctypes.c_void_p(self._display_ptr), self._root, self._info_ptr
            ):
                return None
            return self._info_ptr.contents.idle / 1000.0
        if self._fallback_tool:
            try:
                completed = subprocess.run(
                    [self._fallback_tool],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                return None
            output = completed.stdout.strip()
            if completed.returncode != 0 or not output.isdigit():
                return None
            return int(output) / 1000.0
        return None


def create_idle_backend() -> IdleBackend:
    """Passendes Idle-Backend für dieses System auswählen."""
    if sys.platform == "win32":
        backend = WindowsIdleBackend()
        if backend.available():
            return backend
        return NullIdleBackend(backend.unavailable_reason() or "Win32-API nicht nutzbar")
    if sys.platform.startswith("linux"):
        backend = X11IdleBackend()
        if backend.available():
            return backend
        return NullIdleBackend(backend.unavailable_reason() or "kein X11-Backend")
    return NullIdleBackend(
        f"für {sys.platform} gibt es in Phase 1 noch keine Idle-Erkennung"
    )
