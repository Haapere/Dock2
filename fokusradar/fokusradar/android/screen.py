"""Bildschirm-Aufnahmen vom Handy entgegennehmen (Phase 6).

Der Begleiter kann — wenn man es einschaltet — in großen Abständen ein Bild des
Handy-Bildschirms aufnehmen und ins Heimnetz schicken. Hier passiert damit
genau das, was am Rechner auch mit einem Screenshot passiert (Phase 3):

1. Ausschlussliste prüfen. Passt die App darauf, wird das Bild **verworfen**,
   ohne es anzusehen und ohne etwas zu speichern.
2. Text lokal erkennen (Tesseract) — auf dem Rechner, nicht in der Cloud.
3. Nur den Text speichern und das Bild löschen, wenn ``bild_loeschen`` gilt.

Das Bild liegt dabei höchstens für die Dauer der Texterkennung auf der Platte,
und es geht **nie** ins Internet. Ohne ``[screenshots] aktiv = true`` nimmt der
Rechner überhaupt nichts an: wer am Rechner keine Screenshots will, bekommt
auch keine vom Handy untergeschoben.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fokusradar import timeutil
from fokusradar.android.sync import SyncError
from fokusradar.capture.screenshots import clean_ocr_text, screenshot_filename

#: Größer nimmt der Rechner eine einzelne Aufnahme nicht an.
MAX_IMAGE_BYTES = 12 * 1024 * 1024

#: Erkennungsmerkmale der akzeptierten Formate (Dateianfang → Endung).
MAGIC_BYTES = {
    b"\x89PNG\r\n\x1a\n": ".png",
    b"\xff\xd8\xff": ".jpg",
}


@dataclass(frozen=True)
class ScreenCapture:
    """Eine geprüfte Aufnahme, noch nicht auf der Platte."""

    device: str
    package: str
    label: str | None
    data: bytes
    suffix: str

    @property
    def size_kb(self) -> float:
        return len(self.data) / 1024


def parse_capture(
    data: bytes, *, device: str, package: str, label: str | None = None
) -> ScreenCapture:
    """Rohdaten prüfen, bevor sie irgendwo landen."""
    geraet = (device or "").strip()[:64]
    if not geraet:
        raise SyncError("Der Kopf 'X-FokusRadar-Geraet' fehlt")
    paket = (package or "").strip()[:255]
    if not paket:
        raise SyncError("Der Kopf 'X-FokusRadar-Paket' fehlt")
    if not data:
        raise SyncError("Der Rumpf ist leer — erwartet wird ein Bild")
    if len(data) > MAX_IMAGE_BYTES:
        raise SyncError(
            f"Die Aufnahme ist {len(data) / 1024 / 1024:.1f} MB groß; "
            f"höchstens {MAX_IMAGE_BYTES // 1024 // 1024} MB werden angenommen",
            status=413,
        )
    endung = _suffix_for(data)
    if endung is None:
        raise SyncError("Der Rumpf ist kein PNG und kein JPEG")
    return ScreenCapture(
        device=geraet,
        package=paket,
        label=(label or "").strip()[:128] or None,
        data=data,
        suffix=endung,
    )


def _suffix_for(data: bytes) -> str | None:
    for magic, endung in MAGIC_BYTES.items():
        if data.startswith(magic):
            return endung
    return None


def store_capture(
    database,
    config,
    capture: ScreenCapture,
    *,
    ocr_backend=None,
    exclusions=None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Aufnahme verarbeiten: prüfen, Text erkennen, Bild löschen.

    Das Bild wird erst geschrieben, wenn feststeht, dass es überhaupt verarbeitet
    werden darf — was die Ausschlussliste betrifft, berührt es die Platte nie.
    """
    zeitpunkt = now or timeutil.now_utc()

    if exclusions is not None:
        regel = exclusions.matching_rule(capture.package, capture.label)
        if regel is not None:
            # Nichts speichern, nichts schreiben, nichts ansehen.
            return {
                "status": "ausgeschlossen",
                "grund": f"{regel.label}-Muster {regel.pattern!r}",
                "gespeichert": False,
            }

    einstellungen = config.screenshots
    ziel = config.screenshot_dir / _dateiname(capture, zeitpunkt)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(capture.data)

    text = None
    if ocr_backend is not None:
        text = clean_ocr_text(ocr_backend.text(ziel), einstellungen.text_max_length)

    geloescht = None
    pfad: str | None = str(ziel)
    if einstellungen.delete_image:
        try:
            ziel.unlink()
            geloescht = zeitpunkt
            pfad = None
        except OSError:  # pragma: no cover - Datei ist schon weg o. Ä.
            pass

    eintrag = database.record_screenshot(
        zeitpunkt,
        ocr_text=text,
        screenshot_path=pfad,
        deleted_at=geloescht,
        device=capture.device,
        context=capture.package,
    )
    return {
        "status": "ok",
        "gespeichert": True,
        "id": eintrag,
        "zeichen": len(text or ""),
        "bild": "gelöscht" if geloescht else pfad,
        "empfangen_am": timeutil.isoformat(zeitpunkt),
    }


def _dateiname(capture: ScreenCapture, at: datetime) -> str:
    """Dateiname der Aufnahme: Zeitpunkt plus Gerät, damit nichts kollidiert."""
    basis = screenshot_filename(at).removesuffix(".png")
    sicher = "".join(z if z.isalnum() or z in "-_" else "-" for z in capture.device)
    return f"{basis}_{sicher}{capture.suffix}"
