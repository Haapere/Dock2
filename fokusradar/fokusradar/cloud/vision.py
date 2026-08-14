"""Bild-Analyse einzelner Screenshots über die Claude-API (Phase 6).

Das ist die **weitreichendste** Funktion von FokusRadar — und deshalb die am
festesten verriegelte. Bei allem anderen verlässt nur Verdichtetes das Gerät:
Zahlen, Prozessnamen, allenfalls erkannter Text. Hier geht ein **Bildschirmfoto**
hinaus, also alles, was in dem Moment zu sehen war.

Vier Schlösser, alle müssen offen sein:

1. ``[cloud] aktiv = true`` — ohne das gibt es überhaupt keine Verbindung.
2. ``[cloud] bilder_senden = true`` — ein eigener Schalter, Vorgabe aus.
3. Ein ausdrücklicher Aufruf von Hand (``fokusradar bild``). Die Erfassung
   schickt **nie** von sich aus ein Bild — anders als bei der Tagesanalyse gibt
   es hier keine Automatik.
4. Das Fenster darf nicht auf der Ausschlussliste stehen.

Vorher ansehen, was hinausginge, geht immer:

    fokusradar bild --zeigen

Zurück kommen Vorschläge zur Bedienung: was am Bildschirm Zeit kostet, welcher
Weg kürzer wäre, welche Einstellung sich lohnt.
"""

from __future__ import annotations

import base64
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Größer nimmt die API ein einzelnes Bild nicht an.
MAX_IMAGE_BYTES = 5 * 1024 * 1024

#: Von der API unterstützte Formate (Endung → media_type).
MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

#: Obergrenze der Bild-Token je Aufnahme bei den aktuellen Modellen.
MAX_IMAGE_TOKENS = 4784
#: So viele Pixel entsprechen ungefähr einem Token.
PIXELS_PER_TOKEN = 750


class ImageError(ValueError):
    """Die Aufnahme lässt sich nicht senden."""


@dataclass(frozen=True)
class ImageInfo:
    """Was über eine Aufnahme bekannt ist, bevor sie hinausgeht."""

    path: Path
    media_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None

    @property
    def estimated_tokens(self) -> int:
        """Grobe Schätzung der Bild-Token (zur Kostenvorschau)."""
        if not self.width or not self.height:
            return MAX_IMAGE_TOKENS
        return min(MAX_IMAGE_TOKENS, max(1, self.width * self.height // PIXELS_PER_TOKEN))

    @property
    def size_text(self) -> str:
        kb = self.size_bytes / 1024
        masse = f", {self.width}×{self.height} Pixel" if self.width and self.height else ""
        return f"{kb:.0f} KB{masse}"


def inspect_image(path: Path) -> ImageInfo:
    """Aufnahme prüfen, ohne sie zu senden."""
    path = Path(path).expanduser()
    if not path.is_file():
        raise ImageError(f"Keine Aufnahme unter {path}")
    media_type = MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        raise ImageError(
            f"Format {path.suffix or '(ohne Endung)'} wird nicht unterstützt; "
            f"möglich sind {', '.join(sorted(MEDIA_TYPES))}"
        )
    # Erst die Größe erfragen, dann lesen: eine versehentlich mitgegebene
    # Riesendatei soll nicht zuerst im Arbeitsspeicher landen.
    groesse = path.stat().st_size
    if groesse == 0:
        raise ImageError(f"Die Datei {path} ist leer")
    if groesse > MAX_IMAGE_BYTES:
        raise ImageError(
            f"Die Aufnahme ist {groesse / 1024 / 1024:.1f} MB groß; "
            f"die API nimmt höchstens {MAX_IMAGE_BYTES // 1024 // 1024} MB je Bild. "
            "Kleiner speichern oder verkleinern."
        )
    with path.open("rb") as datei:
        kopf = datei.read(24)  # für die PNG-Maße reichen die ersten 24 Bytes
    breite, hoehe = png_dimensions(kopf)
    return ImageInfo(
        path=path,
        media_type=media_type,
        size_bytes=groesse,
        width=breite,
        height=hoehe,
    )


def png_dimensions(data: bytes) -> tuple[int | None, int | None]:
    """Maße aus dem PNG-Kopf lesen — ohne Zusatzpaket.

    Andere Formate (JPEG, WebP) ergeben ``(None, None)``; dann wird für die
    Kostenschätzung der ungünstigste Fall angenommen.
    """
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None, None
    breite, hoehe = struct.unpack(">II", data[16:24])
    return int(breite), int(hoehe)


def encode_image(info: ImageInfo) -> str:
    """Aufnahme als base64 kodieren (ohne Zeilenumbrüche, wie die API es will)."""
    return base64.standard_b64encode(info.path.read_bytes()).decode("ascii")


def build_question(context: str | None = None) -> str:
    """Der Text, der neben dem Bild hinausgeht.

    Steht eigens hier, damit ``fokusradar bild --zeigen`` genau ihn zeigen kann
    und nicht eine Nachbildung davon.
    """
    frage = "Hier ist ein Bildschirmfoto meines Arbeitsplatzes."
    if context:
        frage += f"\nDazu bekannt: {context}"
    return frage + (
        "\n\nSieh dir an, wie hier gearbeitet wird, und gib mir konkrete "
        "Verbesserungsvorschläge zur Bedienung."
    )


def build_image_content(info: ImageInfo, context: str | None = None) -> list[dict[str, Any]]:
    """Inhalt der Nachricht: erst das Bild, dann die Frage."""
    return [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": info.media_type,
                "data": encode_image(info),
            },
        },
        {"type": "text", "text": build_question(context)},
    ]


VISION_SYSTEM_PROMPT = """\
Du siehst ein einzelnes Bildschirmfoto vom Arbeitsplatz einer Person, die ihre \
eigene Arbeitsweise verbessern möchte. Sie hat dieses Bild bewusst und einzeln \
geschickt.

Deine Aufgabe: konkrete Vorschläge zur **Bedienung und zum Arbeitsablauf**.
Achte auf:
- Fenster- und Bildschirmaufteilung (überlappende Fenster, ungenutzte Fläche,
  ständiges Wechseln zwischen zwei Programmen)
- offensichtliche Handarbeit, für die es einen kürzeren Weg gibt (Tastenkürzel,
  Vorlage, Filter, Funktion des Programms)
- Zahl der offenen Tabs, Fenster und Benachrichtigungen als Quelle von Ablenkung
- Werkzeuge, die für die sichtbare Aufgabe unpassend wirken

Regeln:
- Beschreibe **nicht**, was auf dem Bild steht. Inhalte (Namen, Beträge, Texte,
  Adressen, Code) gibst du niemals wieder — auch nicht als Beispiel oder Zitat.
  Sprich nur über Programme, Fenster, Aufteilung und Bedienschritte.
- Jeder Vorschlag ist umsetzbar und nennt den ersten Schritt.
- Keine Vermutungen über die Person, ihre Leistung oder ihren Zustand.
- Höchstens vier Vorschläge, deutsch, per Du, ohne Floskeln.
- Fällt dir nichts Substanzielles auf, gib eine leere Liste zurück statt
  Selbstverständlichkeiten.
"""

VISION_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "vorschlaege": {
            "type": "array",
            "description": "Verbesserungsvorschläge zur Bedienung, höchstens vier.",
            "items": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Der Vorschlag, ein bis zwei Sätze, mit erstem Schritt.",
                    },
                    "kategorie": {
                        "type": "string",
                        "enum": ["fenster", "abkuerzung", "ablenkung", "werkzeug"],
                        "description": "Worum es geht.",
                    },
                },
                "required": ["text", "kategorie"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["vorschlaege"],
    "additionalProperties": False,
}
