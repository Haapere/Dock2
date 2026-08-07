"""Fahrplan: die konkreten nächsten Schritte als Aufgabenliste mit Fristen."""

from __future__ import annotations

from datetime import date

from creatordock.store import Store, pruefe_datum

STATUS_WERTE = ("offen", "laufend", "erledigt", "entfällt")
PRIORITAETEN = ("hoch", "mittel", "niedrig")
BEREICHE = ("Recht", "Steuern", "Ausrüstung", "Persona", "Produktion", "Marketing")


def anlegen(
    store: Store,
    titel: str,
    bereich: str = "Produktion",
    faellig: str = "",
    prioritaet: str = "mittel",
    notiz: str = "",
) -> dict:
    titel = str(titel or "").strip()
    if not titel:
        raise ValueError("Bitte einen Titel für die Aufgabe angeben.")
    if prioritaet not in PRIORITAETEN:
        raise ValueError(f"Unbekannte Priorität '{prioritaet}'.")
    eintrag = {
        "titel": titel,
        "bereich": bereich if bereich in BEREICHE else "Produktion",
        "faellig": pruefe_datum(faellig, "Fälligkeit") if faellig else "",
        "prioritaet": prioritaet,
        "status": "offen",
        "notiz": str(notiz or "").strip(),
    }
    return store.anlegen("fahrplan", eintrag)


def status_setzen(store: Store, kennung: str, status: str) -> dict:
    if status not in STATUS_WERTE:
        raise ValueError(
            f"Unbekannter Status '{status}'. Möglich: {', '.join(STATUS_WERTE)}"
        )
    aufgabe = store.finden("fahrplan", kennung)
    aufgabe["status"] = status
    if status == "erledigt":
        aufgabe["erledigt_am"] = date.today().isoformat()
    else:
        aufgabe.pop("erledigt_am", None)
    return aufgabe


def uebersicht(store: Store, nur_offen: bool = False, stichtag: str | None = None) -> list[dict]:
    """Aufgaben sortiert nach Priorität und Fälligkeit, mit Überfällig-Kennzeichen."""
    heute = stichtag or date.today().isoformat()
    rang = {p: i for i, p in enumerate(PRIORITAETEN)}
    zeilen = []
    for aufgabe in store.sammlung("fahrplan"):
        if nur_offen and aufgabe.get("status") in ("erledigt", "entfällt"):
            continue
        zeile = dict(aufgabe)
        faellig = aufgabe.get("faellig", "")
        zeile["ueberfaellig"] = bool(
            faellig and faellig < heute and aufgabe.get("status") not in ("erledigt", "entfällt")
        )
        zeilen.append(zeile)
    return sorted(
        zeilen,
        key=lambda a: (
            not a["ueberfaellig"],
            rang.get(a.get("prioritaet", "mittel"), 1),
            a.get("faellig") or "9999-12-31",
        ),
    )


def kennzahlen(store: Store, stichtag: str | None = None) -> dict:
    alle = uebersicht(store, stichtag=stichtag)
    return {
        "gesamt": len(alle),
        "offen": sum(1 for a in alle if a.get("status") == "offen"),
        "laufend": sum(1 for a in alle if a.get("status") == "laufend"),
        "erledigt": sum(1 for a in alle if a.get("status") == "erledigt"),
        "ueberfaellig": sum(1 for a in alle if a["ueberfaellig"]),
    }
