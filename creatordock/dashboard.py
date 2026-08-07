"""Führt alle Bereiche zu einem Lagebild zusammen.

Die Warnliste ist der Kern: sie zeigt genau die Dinge, deren Übersehen teuer
oder rechtlich heikel wird — fehlende Freigaben, abgelaufene Nachweise,
überfällige Fristen, drohende Umsatzgrenzen.
"""

from __future__ import annotations

from datetime import date

from creatordock import drehs, fahrplan, finanzen, kalender, kanaele, persona
from creatordock import partnerinnen as partner_mod
from creatordock.store import Store


def lagebild(store: Store, stichtag: str | None = None) -> dict:
    heute = stichtag or date.today().isoformat()
    jahr = int(heute[:4])
    projekt = store.laden()["projekt"]

    partner_zeilen = partner_mod.uebersicht(store)
    dreh_zeilen = drehs.uebersicht(store)
    umsatz = finanzen.jahresumsatz(store, jahr)
    ku = finanzen.kleinunternehmer_status(umsatz, projekt.get("vorjahresumsatz", 0.0))
    euer = finanzen.euer(store, jahr)
    opsec = kanaele.opsec_status(store)

    return {
        "projekt": {
            "kuenstlername": projekt.get("kuenstlername", ""),
            "start": projekt.get("start", ""),
            "jahr": jahr,
        },
        "partnerinnen": {
            "gesamt": len(partner_zeilen),
            "freigegeben": sum(1 for p in partner_zeilen if p["freigegeben"]),
            "im_vetting": sum(
                1 for p in partner_zeilen if p["status"] == partner_mod.STATUS_VETTING
            ),
            "widerrufen": sum(
                1 for p in partner_zeilen if p["status"] == partner_mod.STATUS_WIDERRUFEN
            ),
        },
        "drehs": {
            "pipeline": drehs.pipeline(store),
            "gesperrt": sum(1 for d in dreh_zeilen if d["gesperrt"]),
            "blockiert": sum(
                1 for d in dreh_zeilen if d["status"] == "geplant" and not d["startklar"]
            ),
        },
        "kalender": kalender.auslastung(store),
        "naechste_slots": kalender.naechste(store, 5, stichtag=heute),
        "finanzen": {
            "einnahmen": euer["einnahmen"],
            "ausgaben": euer["ausgaben"],
            "gewinn": euer["gewinn"],
            "ruecklage": round(
                max(0.0, euer["gewinn"]) * float(projekt.get("ruecklage_satz", 0.25)), 2
            ),
            "ruecklage_satz": float(projekt.get("ruecklage_satz", 0.25)),
        },
        "kleinunternehmer": ku,
        "budget": finanzen.budget_uebersicht(store),
        "opsec": {
            "erledigt": opsec["setup_erledigt"],
            "gesamt": opsec["setup_gesamt"],
            "ohne_2fa": opsec["kanaele_ohne_2fa"],
        },
        "persona": persona.fortschritt(store),
        "fahrplan": fahrplan.kennzahlen(store, stichtag=heute),
        "warnungen": warnungen(store, stichtag=heute),
    }


def warnungen(store: Store, stichtag: str | None = None) -> list[dict]:
    """Sammelt alle offenen Risiken, sortiert nach Dringlichkeit."""
    heute = stichtag or date.today().isoformat()
    jahr = int(heute[:4])
    projekt = store.laden()["projekt"]
    meldungen: list[dict] = []

    def melden(stufe: str, bereich: str, text: str) -> None:
        meldungen.append({"stufe": stufe, "bereich": bereich, "text": text})

    # Partnerinnen: Widerrufe und abgelaufene Nachweise
    for zeile in partner_mod.uebersicht(store):
        if zeile["status"] == partner_mod.STATUS_WIDERRUFEN:
            melden(
                "kritisch",
                "Recht",
                f"{zeile['pseudonym']} hat widerrufen — betroffenes Material muss "
                "offline sein und darf nicht weiter verwertet werden.",
            )
        if zeile["sti_abgelaufen"]:
            melden(
                "warnung",
                "Gesundheit",
                f"STI-Nachweis von {zeile['pseudonym']} ist seit "
                f"{zeile['sti_gueltig_bis']} abgelaufen — vor dem nächsten Dreh erneuern.",
            )

    # Drehs: geplant, aber ohne vollständige Freigabe
    for dreh in drehs.uebersicht(store):
        if dreh["gesperrt"]:
            melden(
                "kritisch",
                "Recht",
                f"Dreh {dreh['id']} ({dreh['titel']}) ist gesperrt und darf nicht "
                "veröffentlicht werden.",
            )
        elif dreh["status"] == "geschnitten" and dreh["auflagen_offen"]:
            melden(
                "warnung",
                "Zusagen",
                f"Dreh {dreh['id']} ({dreh['titel']}) kann nicht veröffentlicht werden — "
                "offene Auflagen: "
                + "; ".join(a["text"] for a in dreh["auflagen_offen"]),
            )
        elif dreh["status"] == "geplant" and dreh["blockiert_durch"]:
            fehlend = "; ".join(
                f"{b['pseudonym']}: {', '.join(b['gruende'])}" for b in dreh["blockiert_durch"]
            )
            melden(
                "warnung",
                "Vetting",
                f"Dreh {dreh['id']} am {dreh['datum']} ist noch nicht freigegeben — {fehlend}.",
            )

    # Steuern und Umsatzgrenzen
    ku = finanzen.kleinunternehmer_status(
        finanzen.jahresumsatz(store, jahr), projekt.get("vorjahresumsatz", 0.0)
    )
    if not ku["anwendbar"]:
        for hinweis in ku["hinweise"]:
            melden("kritisch", "Steuern", hinweis)
    elif ku["warnung"]:
        for hinweis in ku["hinweise"]:
            melden("warnung", "Steuern", hinweis)

    # Fahrplan: überfällige Aufgaben
    for aufgabe in fahrplan.uebersicht(store, nur_offen=True, stichtag=heute):
        if aufgabe["ueberfaellig"]:
            melden(
                "warnung",
                aufgabe.get("bereich", "Fahrplan"),
                f"Überfällig seit {aufgabe['faellig']}: {aufgabe['titel']}",
            )

    # OPSEC
    opsec = kanaele.opsec_status(store)
    if opsec["kanaele_ohne_2fa"]:
        melden(
            "warnung",
            "Sicherheit",
            "Ohne Zwei-Faktor-Authentisierung: " + ", ".join(opsec["kanaele_ohne_2fa"]),
        )

    # Persona: ohne Künstlername und Nische läuft nichts anderes sinnvoll an
    identitaet = persona.fortschritt(store)
    if not identitaet["kuenstlername"]:
        melden(
            "warnung",
            "Persona",
            "Es ist noch kein Künstlername festgelegt — ohne ihn lassen sich "
            "weder Kanäle noch Wasserzeichen konsistent aufbauen.",
        )
    elif identitaet["offen"]:
        melden(
            "hinweis",
            "Persona",
            f"Identitätsaufbau zu {identitaet['anteil']} % fertig — offen: "
            + "; ".join(identitaet["offen"][:3])
            + ("; …" if len(identitaet["offen"]) > 3 else ""),
        )

    # Leerer Kalender
    if not kalender.naechste(store, 1, stichtag=heute):
        melden(
            "hinweis",
            "Marketing",
            "Der Content-Kalender ist ab heute leer — die nächsten Wochen einplanen.",
        )

    rang = {"kritisch": 0, "warnung": 1, "hinweis": 2}
    return sorted(meldungen, key=lambda m: rang.get(m["stufe"], 3))
