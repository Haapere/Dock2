"""Screenshots und lokale Texterkennung.

Beides ist optional und standardmäßig **aus**. Eingeschaltet wird es über
``[screenshots] aktiv = true``; nötig sind dann ``mss`` (Aufnahme) und für die
Texterkennung ``pytesseract`` samt installiertem Tesseract.

Ablauf einer Aufnahme (siehe ``fokusradar.agent``):

1. Bild aufnehmen — aber nur, wenn die Erfassung gerade erlaubt ist
   (keine Ausschlussliste, keine Smart Pause).
2. Text lokal erkennen.
3. Text speichern und das Bild löschen, sofern ``bild_loeschen`` gesetzt ist.

Wie bei der Fenster-Erfassung stecken beide Schritte hinter schmalen
Schnittstellen, damit die Kette ohne Bildschirm testbar bleibt.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from fokusradar import timeutil


@runtime_checkable
class ScreenshotBackend(Protocol):
    """Nimmt den Bildschirminhalt auf."""

    name: str

    def available(self) -> bool: ...

    def unavailable_reason(self) -> str | None: ...

    def capture(self, target: Path) -> Path | None:
        """Aufnahme unter ``target`` ablegen; ``None`` bei Misserfolg."""


@runtime_checkable
class OcrBackend(Protocol):
    """Erkennt Text in einer Aufnahme — vollständig lokal."""

    name: str

    def available(self) -> bool: ...

    def unavailable_reason(self) -> str | None: ...

    def text(self, image: Path) -> str | None: ...


class MssScreenshotBackend:
    """Aufnahme über ``mss`` (alle Bildschirme als ein Bild)."""

    name = "mss"

    def __init__(self) -> None:
        self._reason: str | None = None
        self._mss = None
        try:
            import mss  # noqa: F401

            self._mss = mss
        except Exception as exc:  # pragma: no cover - hängt an der Installation
            self._reason = f"mss nicht nutzbar: {exc}"

    def available(self) -> bool:
        return self._mss is not None

    def unavailable_reason(self) -> str | None:
        return self._reason

    def capture(self, target: Path) -> Path | None:  # pragma: no cover - braucht Bildschirm
        if self._mss is None:
            return None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with self._mss.mss() as aufnahme:
                bild = aufnahme.grab(aufnahme.monitors[0])
                self._mss.tools.to_png(bild.rgb, bild.size, output=str(target))
            return target
        except Exception as exc:
            self._reason = f"Aufnahme fehlgeschlagen: {exc}"
            return None


class TesseractOcrBackend:
    """Texterkennung über ``pytesseract``/Tesseract — ohne Netzwerk."""

    name = "tesseract"

    def __init__(self, languages: str = "deu+eng") -> None:
        self.languages = languages
        self._reason: str | None = None
        self._pytesseract = None
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            self._pytesseract = pytesseract
        except ImportError as exc:  # pragma: no cover
            self._reason = f"pytesseract nicht installiert: {exc}"
        except Exception as exc:  # pragma: no cover - Tesseract fehlt im System
            self._reason = f"Tesseract nicht gefunden: {exc}"

    def available(self) -> bool:
        return self._pytesseract is not None

    def unavailable_reason(self) -> str | None:
        return self._reason

    def text(self, image: Path) -> str | None:  # pragma: no cover - braucht Tesseract
        if self._pytesseract is None:
            return None
        try:
            return self._pytesseract.image_to_string(str(image), lang=self.languages)
        except Exception as exc:
            self._reason = f"Texterkennung fehlgeschlagen: {exc}"
            return None


class _Unavailable:
    """Platzhalter, wenn eine Stufe nicht zur Verfügung steht."""

    name = "keins"

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def available(self) -> bool:
        return False

    def unavailable_reason(self) -> str | None:
        return self._reason


class NullScreenshotBackend(_Unavailable):
    def capture(self, target: Path) -> Path | None:
        return None


class NullOcrBackend(_Unavailable):
    def text(self, image: Path) -> str | None:
        return None


def create_screenshot_backend(enabled: bool = True) -> ScreenshotBackend:
    """Aufnahme-Backend erzeugen."""
    if not enabled:
        return NullScreenshotBackend("in der Konfiguration abgeschaltet")
    backend = MssScreenshotBackend()
    if backend.available():
        return backend
    return NullScreenshotBackend(backend.unavailable_reason() or "mss nicht installiert")


def create_ocr_backend(enabled: bool = True, languages: str = "deu+eng") -> OcrBackend:
    """OCR-Backend erzeugen."""
    if not enabled:
        return NullOcrBackend("in der Konfiguration abgeschaltet")
    backend = TesseractOcrBackend(languages)
    if backend.available():
        return backend
    return NullOcrBackend(backend.unavailable_reason() or "Tesseract nicht verfügbar")


def screenshot_filename(at: datetime) -> str:
    """Dateiname einer Aufnahme — Ortszeit, damit er sich lesen lässt."""
    return timeutil.to_local(at).strftime("%Y-%m-%d_%H-%M-%S.png")


def clean_ocr_text(text: str | None, max_length: int = 4000) -> str | None:
    """Erkannten Text aufräumen: Leerzeilen raus, Länge begrenzen."""
    if not text:
        return None
    zeilen = [" ".join(zeile.split()) for zeile in text.splitlines()]
    zusammen = "\n".join(zeile for zeile in zeilen if zeile)
    if not zusammen:
        return None
    if len(zusammen) > max_length:
        zusammen = zusammen[: max_length - 1] + "…"
    return zusammen
