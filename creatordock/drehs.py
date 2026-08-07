"""Drehplanung und Produktions-Pipeline.

Ein Dreh durchläuft ``geplant → gedreht → geschnitten → veröffentlicht``.
Der Übergang von "geplant" auf jeden weiteren Status ist an die Freigabe
**aller** beteiligten Partnerinnen gebunden (Solo-Drehs ohne Partnerinnen
laufen ohne diese Prüfung). Ein gesperrter Dreh — etwa nach einem Widerruf —
lässt sich gar nicht mehr weiterschalten.
"""

from __future__ import annotations

from datetime import date

from creatordock import partnerinnen as partner_mod
from creatordock.store import Store, pruefe_datum

STATUS_REIHENFOLGE = ("geplant", "gedreht", "geschnitten", "veröffentlicht")
PLATTFORMEN = ("OnlyFans", "Fansly", "Pornhub", "X/Twitter", "Reddit")


def anlegen(
    store: Store,
    datum: str,
    titel: str = "",
    partner_ids: list[str] | None = None,
    plattformen: list[str] | None = None,
    notizen: str = "",
) -> dict:
    """Plant einen Dreh. Partnerinnen müssen bereits erfasst sein."""
    partner_ids = list(partner_ids or [])
    for kennung in partner_ids:
        store.finden("partnerinnen", kennung)  # wirft KeyError bei Tippfehlern

    eintrag = {
        "datum": pruefe_datum(datum, "Drehdatum"),
        "titel": str(titel or "").strip() or "Ohne Titel",
        "partner_ids": partner_ids,
        "plattformen": list(plattformen or []),
        "status": "geplant",
        "gesperrt": False,
        "notizen": str(notizen or "").strip(),
    }
    return store.anlegen("drehs", eintrag)


def status_setzen(store: Store, kennung: str, neuer_status: str) -> dict:
    """Schaltet den Produktionsstatus weiter — nach Prüfung der Freigaben."""
    if neuer_status not in STATUS_REIHENFOLGE:
        raise ValueError(
            f"Unbekannter Status '{neuer_status}'. Möglich: "
            f"{', '.join(STATUS_REIHENFOLGE)}"
        )
    dreh = store.finden("drehs", kennung)

    if neuer_status != "geplant":
        if dreh.get("gesperrt"):
            raise ValueError(
                f"Dreh {kennung} ist gesperrt (Widerruf einer Partnerin) und darf "
                "nicht weiterbearbeitet oder veröffentlicht werden."
            )
        fehlend = blockierende_partnerinnen(store, dreh)
        if fehlend:
            raise ValueError(
                "Freigabe fehlt für: "
                + "; ".join(f"{p} ({', '.join(gruende)})" for p, gruende in fehlend)
            )

    dreh["status"] = neuer_status
    if neuer_status == "veröffentlicht":
        dreh["veroeffentlicht_am"] = date.today().isoformat()
    return dreh


def blockierende_partnerinnen(store: Store, dreh: dict) -> list[tuple[str, list[str]]]:
    """Listet Partnerinnen, deren Vetting den Dreh blockiert, mit Begründung."""
    blockierend: list[tuple[str, list[str]]] = []
    for kennung in dreh.get("partner_ids", []):
        try:
            partnerin = store.finden("partnerinnen", kennung)
        except KeyError:
            blockierend.append((kennung, ["Datensatz fehlt"]))
            continue
        gruende: list[str] = []
        if partnerin.get("status") == partner_mod.STATUS_WIDERRUFEN:
            gruende.append("hat widerrufen")
        elif partnerin.get("status") == partner_mod.STATUS_ABGELEHNT:
            gruende.append("abgelehnt")
        gruende.extend(partner_mod.offene_gates(partnerin))
        if partner_mod.sti_abgelaufen(partnerin):
            gruende.append("STI-Nachweis abgelaufen")
        if gruende:
            blockierend.append((partnerin.get("pseudonym", kennung), gruende))
    return blockierend


def sperren(store: Store, kennung: str, gesperrt: bool = True) -> dict:
    dreh = store.finden("drehs", kennung)
    dreh["gesperrt"] = bool(gesperrt)
    return dreh


def uebersicht(store: Store) -> list[dict]:
    """Alle Drehs mit aufgelösten Pseudonymen und Freigabe-Status."""
    namen = {p["id"]: p.get("pseudonym", p["id"]) for p in store.sammlung("partnerinnen")}
    zeilen = []
    for dreh in sorted(store.sammlung("drehs"), key=lambda d: d.get("datum", "")):
        blockierend = blockierende_partnerinnen(store, dreh)
        zeilen.append(
            {
                "id": dreh["id"],
                "datum": dreh.get("datum", ""),
                "titel": dreh.get("titel", ""),
                "partner": [namen.get(k, k) for k in dreh.get("partner_ids", [])],
                "partner_ids": dreh.get("partner_ids", []),
                "plattformen": dreh.get("plattformen", []),
                "status": dreh.get("status", "geplant"),
                "gesperrt": bool(dreh.get("gesperrt")),
                "startklar": not blockierend and not dreh.get("gesperrt"),
                "blockiert_durch": [
                    {"pseudonym": p, "gruende": g} for p, g in blockierend
                ],
                "notizen": dreh.get("notizen", ""),
            }
        )
    return zeilen


def pipeline(store: Store) -> dict[str, int]:
    """Zählt die Drehs je Produktionsstatus."""
    zaehler = {status: 0 for status in STATUS_REIHENFOLGE}
    for dreh in store.sammlung("drehs"):
        status = dreh.get("status", "geplant")
        if status in zaehler:
            zaehler[status] += 1
    return zaehler
