"""Datenhaltung: eine JSON-Datei in einem lokalen, privaten Datenordner.

Bewusste Entscheidungen zum Datenschutz:

* Der Datenordner liegt **außerhalb** des Projektordners (Standard:
  ``~/CreatorDock-Daten``), damit personenbezogene Daten nie versehentlich in
  ein Git-Repository geraten.
* Ordner und Datei werden mit engen Rechten angelegt (0700 / 0600), soweit das
  Betriebssystem das unterstützt.
* Gespeichert werden ausschließlich **Pseudonyme und Bestätigungen** — keine
  Ausweiskopien, keine Klarnamen, keine Testbefunde. Für solche Dokumente hält
  jeder Datensatz nur ein Aktenzeichen, das auf die verschlüsselte Ablage
  außerhalb der App verweist (siehe ``ABLAGE_HINWEIS``).
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import date, datetime
from pathlib import Path

ENV_DATENORDNER = "CREATORDOCK_DATEN"
DATEINAME = "daten.json"
SCHEMA_VERSION = 1

ABLAGE_HINWEIS = (
    "Ausweiskopien, unterschriebene Model-Releases und STI-Nachweise gehören "
    "NICHT in diese App. Lege sie in einem verschlüsselten Ordner ab "
    "(VeraCrypt-Container, BitLocker, FileVault oder LUKS) und trage hier nur "
    "das Aktenzeichen ein, unter dem du sie dort wiederfindest."
)

# Sammlungen der Datenbank. Reihenfolge = Reihenfolge in der JSON-Datei.
SAMMLUNGEN = (
    "partnerinnen",
    "drehs",
    "kanaele",
    "buchungen",
    "budget",
    "kalender",
    "fahrplan",
    "namenskandidaten",
)

# Präfix der laufenden Nummer je Sammlung.
_PRAEFIX = {
    "partnerinnen": "P",
    "drehs": "D",
    "kanaele": "K",
    "buchungen": "B",
    "budget": "E",
    "kalender": "S",
    "fahrplan": "A",
    "namenskandidaten": "N",
}


def leere_datenbank() -> dict:
    """Liefert eine frische, leere Datenbank-Struktur."""
    db: dict = {
        "version": SCHEMA_VERSION,
        "projekt": {
            "kuenstlername": "",
            "start": date.today().isoformat(),
            "kleinunternehmer": True,
            "ruecklage_satz": 0.25,
            "vorjahresumsatz": 0.0,
            "notizen": "",
        },
    }
    for name in SAMMLUNGEN:
        db[name] = []
    return db


def datenordner(pfad: str | os.PathLike[str] | None = None) -> Path:
    """Ermittelt den Datenordner (Argument > Umgebungsvariable > Standard)."""
    if pfad:
        return Path(pfad).expanduser().resolve()
    aus_umgebung = os.environ.get(ENV_DATENORDNER)
    if aus_umgebung:
        return Path(aus_umgebung).expanduser().resolve()
    return Path.home() / "CreatorDock-Daten"


class Store:
    """Lädt und speichert die Projektdatenbank als eine JSON-Datei."""

    def __init__(self, ordner: str | os.PathLike[str] | None = None) -> None:
        self.ordner = datenordner(ordner)
        self.datei = self.ordner / DATEINAME
        self._db: dict | None = None

    # --- Laden / Speichern ------------------------------------------------

    @property
    def existiert(self) -> bool:
        return self.datei.is_file()

    def laden(self) -> dict:
        """Liest die Datenbank; legt sie beim ersten Zugriff leer an."""
        if self._db is not None:
            return self._db
        if not self.datei.is_file():
            self._db = leere_datenbank()
            return self._db
        try:
            roh = json.loads(self.datei.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Die Datei {self.datei} ist beschädigt und konnte nicht gelesen "
                f"werden ({exc}). Die letzte Sicherung liegt daneben als "
                f"{DATEINAME}.bak."
            ) from exc
        self._db = self._migrieren(roh)
        return self._db

    def speichern(self, db: dict | None = None) -> Path:
        """Schreibt die Datenbank atomar und legt vorher eine Sicherung an."""
        if db is not None:
            self._db = db
        if self._db is None:
            self.laden()  # frischer Store: leere Datenbank anlegen und schreiben
        self._db["gespeichert_am"] = datetime.now().isoformat(timespec="seconds")

        self.ordner.mkdir(parents=True, exist_ok=True)
        _rechte_setzen(self.ordner, 0o700)
        if self.datei.is_file():
            shutil.copy2(self.datei, self.datei.with_suffix(".json.bak"))

        temp = self.datei.with_suffix(".json.tmp")
        temp.write_text(
            json.dumps(self._db, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _rechte_setzen(temp, 0o600)
        temp.replace(self.datei)
        return self.datei

    def zuruecksetzen(self) -> dict:
        """Verwirft den Speicherinhalt und lädt beim nächsten Zugriff neu."""
        self._db = None
        return self.laden()

    @staticmethod
    def _migrieren(roh: dict) -> dict:
        """Ergänzt fehlende Felder, damit ältere Dateien weiter funktionieren."""
        db = leere_datenbank()
        db["projekt"].update(roh.get("projekt", {}))
        for name in SAMMLUNGEN:
            eintraege = roh.get(name)
            if isinstance(eintraege, list):
                db[name] = eintraege
        db["version"] = SCHEMA_VERSION
        if "gespeichert_am" in roh:
            db["gespeichert_am"] = roh["gespeichert_am"]
        return db

    # --- Sammlungen -------------------------------------------------------

    def sammlung(self, name: str) -> list[dict]:
        if name not in SAMMLUNGEN:
            raise ValueError(f"Unbekannte Sammlung: {name}")
        return self.laden()[name]

    def neue_id(self, sammlung: str) -> str:
        """Vergibt die nächste freie ID, z. B. ``P3`` für die dritte Partnerin."""
        praefix = _PRAEFIX[sammlung]
        hoechste = 0
        for eintrag in self.sammlung(sammlung):
            kennung = str(eintrag.get("id", ""))
            if kennung.startswith(praefix) and kennung[len(praefix):].isdigit():
                hoechste = max(hoechste, int(kennung[len(praefix):]))
        return f"{praefix}{hoechste + 1}"

    def finden(self, sammlung: str, kennung: str) -> dict:
        for eintrag in self.sammlung(sammlung):
            if eintrag.get("id") == kennung:
                return eintrag
        raise KeyError(f"{kennung} wurde in '{sammlung}' nicht gefunden.")

    def anlegen(self, sammlung: str, eintrag: dict) -> dict:
        eintrag = dict(eintrag)
        eintrag["id"] = self.neue_id(sammlung)
        eintrag.setdefault("angelegt_am", date.today().isoformat())
        self.sammlung(sammlung).append(eintrag)
        return eintrag

    def loeschen(self, sammlung: str, kennung: str) -> dict:
        eintraege = self.sammlung(sammlung)
        for i, eintrag in enumerate(eintraege):
            if eintrag.get("id") == kennung:
                return eintraege.pop(i)
        raise KeyError(f"{kennung} wurde in '{sammlung}' nicht gefunden.")


def _rechte_setzen(pfad: Path, modus: int) -> None:
    """Setzt Dateirechte, ignoriert Systeme ohne POSIX-Rechte (Windows)."""
    try:
        pfad.chmod(modus)
    except (OSError, NotImplementedError):
        pass


def heute() -> str:
    return date.today().isoformat()


def pruefe_datum(wert: str, feld: str = "Datum") -> str:
    """Validiert ein ISO-Datum (JJJJ-MM-TT) und gibt es normalisiert zurück."""
    text = str(wert or "").strip()
    if not text:
        raise ValueError(f"{feld} fehlt (Format JJJJ-MM-TT).")
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError as exc:
        raise ValueError(f"{feld} '{wert}' ist kein gültiges Datum (JJJJ-MM-TT).") from exc
