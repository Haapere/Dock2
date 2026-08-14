"""Gegenstelle für den Sync des Android-Begleiters.

Das Handy schickt einmal am Tag (oder auf Knopfdruck) den Stand seiner
``UsageStatsManager``-Zahlen an das Dashboard:

.. code-block:: json

    {
      "geraet": "Pixel-7",
      "tage": [
        {
          "datum": "2026-08-14",
          "apps": [
            {"paket": "com.instagram.android", "name": "Instagram",
             "sekunden": 1830, "oeffnungen": 24}
          ]
        }
      ]
    }

Was hier hereinkommt, sind **nur Zahlen je App** — keine Inhalte, keine
Benachrichtigungen, keine Bildschirminhalte. Genau wie am Rechner gilt: das
Gerät verlässt nichts davon, der Sync läuft im Heimnetz von Handy zu Rechner.

Der Zugang hängt an einem gemeinsamen Geheimnis aus ``[android] token``. Ohne
``[android] aktiv = true`` gibt es den Endpunkt gar nicht — das Dashboard
antwortet dann mit 404, als wäre nie einer eingebaut worden.
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from fokusradar import timeutil

#: So viele Tage nimmt eine einzelne Übertragung höchstens mit.
MAX_DAYS = 62
#: So viele Apps je Tag werden übernommen (längste zuerst, der Rest fällt weg).
MAX_APPS_PER_DAY = 500
#: Längenbegrenzungen, damit ein fehlerhafter Client die Datenbank nicht flutet.
MAX_DEVICE_LENGTH = 64
MAX_PACKAGE_LENGTH = 255
MAX_LABEL_LENGTH = 128


class SyncError(ValueError):
    """Die Übertragung war nicht verwertbar.

    ``status`` ist der passende HTTP-Code; das Dashboard reicht ihn durch.
    """

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


# -- Gemeinsames Geheimnis ---------------------------------------------------


def generate_token() -> str:
    """Neues Geheimnis für die Kopplung erzeugen."""
    return secrets.token_urlsafe(24)


def token_from_header(header: str | None) -> str:
    """Token aus einem ``Authorization``-Kopf lesen (``Bearer <token>``)."""
    if not header:
        return ""
    wert = header.strip()
    if wert.lower().startswith("bearer "):
        return wert[7:].strip()
    return wert


def check_token(expected: str, presented: str | None) -> bool:
    """Token vergleichen — in konstanter Zeit, ohne Frühabbruch."""
    if not expected:
        return False
    return hmac.compare_digest(expected, (presented or "").strip())


# -- Übertragung lesen -------------------------------------------------------


@dataclass(frozen=True)
class SyncDay:
    """Ein Tag aus der Übertragung."""

    day: date
    entries: list[dict[str, Any]] = field(default_factory=list)

    @property
    def seconds(self) -> int:
        return sum(int(eintrag["seconds"]) for eintrag in self.entries)


@dataclass(frozen=True)
class SyncRequest:
    """Eine geprüfte Übertragung."""

    device: str
    days: list[SyncDay] = field(default_factory=list)

    @property
    def app_count(self) -> int:
        return sum(len(tag.entries) for tag in self.days)


def parse_payload(raw: Any) -> SyncRequest:
    """JSON der Übertragung prüfen und in ein ``SyncRequest`` überführen.

    Wirft :class:`SyncError`, sobald etwas nicht stimmt — lieber eine klare
    Fehlermeldung ans Handy als halb übernommene Zahlen in der Datenbank.
    """
    if not isinstance(raw, dict):
        raise SyncError("Erwartet wird ein JSON-Objekt")

    geraet = _text(raw.get("geraet"), "geraet", MAX_DEVICE_LENGTH)
    if not geraet:
        raise SyncError("'geraet' fehlt oder ist leer")

    tage_roh = raw.get("tage")
    if not isinstance(tage_roh, list) or not tage_roh:
        raise SyncError("'tage' fehlt oder ist keine nicht-leere Liste")
    if len(tage_roh) > MAX_DAYS:
        raise SyncError(f"Höchstens {MAX_DAYS} Tage je Übertragung")

    tage: list[SyncDay] = []
    for eintrag in tage_roh:
        tage.append(_parse_day(eintrag))
    return SyncRequest(device=geraet, days=tage)


def _parse_day(raw: Any) -> SyncDay:
    if not isinstance(raw, dict):
        raise SyncError("Jeder Eintrag in 'tage' muss ein Objekt sein")
    datum_roh = raw.get("datum")
    if not isinstance(datum_roh, str):
        raise SyncError("'datum' fehlt oder ist kein Text (erwartet JJJJ-MM-TT)")
    try:
        tag = date.fromisoformat(datum_roh.strip())
    except ValueError as exc:
        raise SyncError(f"'datum' ist kein gültiges Datum: {datum_roh!r}") from exc

    apps_roh = raw.get("apps", [])
    if not isinstance(apps_roh, list):
        raise SyncError(f"'apps' für {tag} muss eine Liste sein")

    apps: list[dict[str, Any]] = []
    for app in apps_roh:
        eintrag = _parse_app(app, tag)
        if eintrag is not None:
            apps.append(eintrag)

    # Die längsten Nutzungen sind die interessanten; der lange Schwanz aus
    # Systemdiensten mit wenigen Sekunden bringt keine Erkenntnis.
    apps.sort(key=lambda eintrag: -int(eintrag["seconds"]))
    return SyncDay(day=tag, entries=apps[:MAX_APPS_PER_DAY])


def _parse_app(raw: Any, tag: date) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        raise SyncError(f"Jeder Eintrag in 'apps' ({tag}) muss ein Objekt sein")
    paket = _text(raw.get("paket"), "paket", MAX_PACKAGE_LENGTH)
    if not paket:
        return None
    sekunden = _count(raw.get("sekunden"), "sekunden")
    oeffnungen = _count(raw.get("oeffnungen"), "oeffnungen")
    if sekunden <= 0 and oeffnungen <= 0:
        return None  # ungenutzte App — die muss nicht in die Datenbank
    return {
        "package": paket,
        "label": _text(raw.get("name"), "name", MAX_LABEL_LENGTH) or None,
        "seconds": sekunden,
        "opens": oeffnungen,
    }


def _text(value: Any, feld: str, max_length: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SyncError(f"'{feld}' muss ein Text sein, gefunden: {type(value).__name__}")
    return value.strip()[:max_length]


def _count(value: Any, feld: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SyncError(f"'{feld}' muss eine Zahl sein, gefunden: {value!r}")
    return max(0, int(value))


# -- Übernehmen --------------------------------------------------------------


def apply_sync(
    database,
    request: SyncRequest,
    *,
    categorizer=None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Geprüfte Übertragung in die Datenbank schreiben.

    Ein Tag wird immer vollständig ersetzt: das Handy schickt den Stand des
    ganzen Tages, nicht die Differenz zum letzten Sync.
    """
    zeitpunkt = now or timeutil.now_utc()
    tage: list[dict[str, Any]] = []
    gesamt = 0
    for tag in request.days:
        anzahl = database.record_android_usage(
            tag.day,
            request.device,
            tag.entries,
            synced_at=zeitpunkt,
            categorizer=categorizer,
        )
        gesamt += anzahl
        tage.append(
            {
                "datum": tag.day.isoformat(),
                "apps": anzahl,
                "sekunden": tag.seconds,
            }
        )
    return {
        "status": "ok",
        "geraet": request.device,
        "gespeichert": gesamt,
        "tage": tage,
        "empfangen_am": timeutil.isoformat(zeitpunkt),
    }
