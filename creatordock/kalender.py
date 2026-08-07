"""Content-Kalender: Redaktionsplan aus einem festen Wochenrhythmus.

Das Konzept sieht einen planbaren Rhythmus vor (z. B. 3× Teaser und 1× Paid-
Release pro Woche) und einen im Voraus gefüllten Kalender für die ersten
Wochen, statt spontan zu drehen. Genau das erzeugt :func:`planen`.
"""

from __future__ import annotations

from datetime import date, timedelta

from creatordock.store import Store, pruefe_datum

WOCHENTAGE = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
SLOT_STATUS = ("offen", "in Arbeit", "fertig", "veröffentlicht")

TYP_TEASER = "teaser"
TYP_PAID = "paid"
TYP_SFW = "sfw"

# Vorschlag aus dem Konzept: Teaser Mo/Mi/Fr, Paid-Release am Sonntag.
STANDARD_RHYTHMUS = {
    TYP_TEASER: {"tage": [0, 2, 4], "kanal": "X/Twitter"},
    TYP_PAID: {"tage": [6], "kanal": "OnlyFans"},
}

# Themenvorschläge, damit kein leerer Kalender entsteht.
THEMEN_VORSCHLAEGE = {
    TYP_TEASER: [
        "Standbild aus dem letzten Dreh (Wasserzeichen prüfen)",
        "Kurzclip 10–15 s, Cliffhanger auf das Paid-Release",
        "Frage an die Community / Umfrage",
        "Behind the Scenes: Setup, Licht, kein expliziter Inhalt",
    ],
    TYP_PAID: [
        "Hauptrelease der Woche",
        "Bundle aus zwei kürzeren Clips",
        "Custom-Request-Umsetzung",
    ],
    TYP_SFW: [
        "Lifestyle-Post für den SFW-Trichter",
        "Ankündigung ohne expliziten Inhalt",
    ],
}


def planen(
    store: Store,
    start: str,
    wochen: int = 6,
    rhythmus: dict | None = None,
    ersetzen: bool = False,
) -> list[dict]:
    """Legt Kalender-Slots für ``wochen`` Wochen ab ``start`` an.

    ``start`` wird auf den Montag der Startwoche zurückgesetzt, damit die
    Wochentage des Rhythmus stimmen. Bereits belegte Termine werden
    übersprungen, sofern ``ersetzen`` nicht gesetzt ist.
    """
    if wochen < 1 or wochen > 52:
        raise ValueError("Bitte zwischen 1 und 52 Wochen planen.")
    rhythmus = rhythmus or STANDARD_RHYTHMUS
    start_datum = date.fromisoformat(pruefe_datum(start, "Startdatum"))
    montag = start_datum - timedelta(days=start_datum.weekday())

    if ersetzen:
        ende = montag + timedelta(weeks=wochen)
        behalten = [
            s
            for s in store.sammlung("kalender")
            if not (montag.isoformat() <= s.get("datum", "") < ende.isoformat())
            or s.get("status") == "veröffentlicht"
        ]
        store.laden()["kalender"] = behalten

    belegt = {(s.get("datum"), s.get("typ")) for s in store.sammlung("kalender")}
    neu: list[dict] = []
    for woche in range(wochen):
        for typ, konfiguration in rhythmus.items():
            vorschlaege = THEMEN_VORSCHLAEGE.get(typ, ["Thema festlegen"])
            for lauf, wochentag in enumerate(konfiguration.get("tage", [])):
                tag = montag + timedelta(weeks=woche, days=int(wochentag))
                if tag < start_datum:
                    continue
                schluessel = (tag.isoformat(), typ)
                if schluessel in belegt:
                    continue
                belegt.add(schluessel)
                thema = vorschlaege[(woche + lauf) % len(vorschlaege)]
                neu.append(
                    store.anlegen(
                        "kalender",
                        {
                            "datum": tag.isoformat(),
                            "wochentag": WOCHENTAGE[tag.weekday()],
                            "typ": typ,
                            "kanal": konfiguration.get("kanal", ""),
                            "thema": thema,
                            "status": "offen",
                            "dreh_id": "",
                        },
                    )
                )
    return neu


def slot_aktualisieren(store: Store, kennung: str, **felder) -> dict:
    """Ändert Thema, Kanal, Status oder die Zuordnung zu einem Dreh."""
    slot = store.finden("kalender", kennung)
    if "status" in felder:
        status = felder["status"]
        if status not in SLOT_STATUS:
            raise ValueError(
                f"Unbekannter Status '{status}'. Möglich: {', '.join(SLOT_STATUS)}"
            )
        slot["status"] = status
    if "dreh_id" in felder and felder["dreh_id"]:
        store.finden("drehs", felder["dreh_id"])
        slot["dreh_id"] = felder["dreh_id"]
    elif "dreh_id" in felder:
        slot["dreh_id"] = ""
    for feld in ("thema", "kanal"):
        if feld in felder:
            slot[feld] = str(felder[feld] or "").strip()
    return slot


def uebersicht(store: Store, ab: str | None = None, bis: str | None = None) -> list[dict]:
    """Kalender-Slots im Zeitraum, chronologisch sortiert."""
    zeilen = sorted(store.sammlung("kalender"), key=lambda s: (s.get("datum", ""), s.get("typ", "")))
    if ab:
        grenze = pruefe_datum(ab, "Von")
        zeilen = [s for s in zeilen if s.get("datum", "") >= grenze]
    if bis:
        grenze = pruefe_datum(bis, "Bis")
        zeilen = [s for s in zeilen if s.get("datum", "") <= grenze]
    return zeilen


def naechste(store: Store, anzahl: int = 5, stichtag: str | None = None) -> list[dict]:
    """Die nächsten anstehenden, noch nicht veröffentlichten Slots."""
    heute = stichtag or date.today().isoformat()
    offen = [
        s
        for s in uebersicht(store, ab=heute)
        if s.get("status") != "veröffentlicht"
    ]
    return offen[:anzahl]


def auslastung(store: Store) -> dict:
    """Zählt Slots je Status und je Typ — Grundlage fürs Dashboard."""
    je_status = {status: 0 for status in SLOT_STATUS}
    je_typ: dict[str, int] = {}
    for slot in store.sammlung("kalender"):
        status = slot.get("status", "offen")
        if status in je_status:
            je_status[status] += 1
        typ = slot.get("typ", "?")
        je_typ[typ] = je_typ.get(typ, 0) + 1
    return {"je_status": je_status, "je_typ": je_typ, "gesamt": len(store.sammlung("kalender"))}
