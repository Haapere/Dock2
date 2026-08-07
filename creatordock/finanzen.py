"""Einnahmen-Überschuss-Rechnung, Steuerrücklage und Kleinunternehmer-Monitor.

Rechnet ausschließlich mit den erfassten Buchungen — nichts wird geschätzt.
Die Kleinunternehmer-Prüfung bildet § 19 UStG in der seit 2025 geltenden
Fassung ab: maßgeblich sind **zwei** Grenzen, nicht nur eine.

    * Vorjahresumsatz  ≤  25.000 €
    * laufender Umsatz ≤ 100.000 €

Wird die obere Grenze im laufenden Jahr überschritten, endet die
Kleinunternehmer-Eigenschaft sofort ab diesem Umsatz — ab dann ist
Umsatzsteuer auszuweisen. Das ist der Punkt, an dem die App warnt.

Keine Steuerberatung: die Rücklage ist ein Richtwert, kein Steuerbescheid.
"""

from __future__ import annotations

from collections import OrderedDict

from creatordock.store import Store, pruefe_datum

GRENZE_VORJAHR = 25_000.0
GRENZE_LAUFEND = 100_000.0
WARNSCHWELLE = 0.8  # ab 80 % einer Grenze wird gewarnt

EINNAHME_KATEGORIEN = (
    "Einnahme Plattform",
    "Einnahme Sonstige",
)
AUSGABE_KATEGORIEN = (
    "Ausrüstung",
    "Gage/Model",
    "Software/Abos",
    "Gebühren",
    "Reise",
    "Werbung",
    "Sonstige Ausgabe",
)
KATEGORIEN = EINNAHME_KATEGORIEN + AUSGABE_KATEGORIEN


def buchen(
    store: Store,
    datum: str,
    beschreibung: str,
    kategorie: str,
    einnahme: float = 0.0,
    ausgabe: float = 0.0,
    beleg: str = "",
) -> dict:
    """Erfasst eine Buchung (Einnahme oder Ausgabe, nicht beides)."""
    if kategorie not in KATEGORIEN:
        raise ValueError(
            f"Unbekannte Kategorie '{kategorie}'. Möglich: {', '.join(KATEGORIEN)}"
        )
    einnahme = _betrag(einnahme, "Einnahme")
    ausgabe = _betrag(ausgabe, "Ausgabe")
    if einnahme and ausgabe:
        raise ValueError("Bitte entweder eine Einnahme oder eine Ausgabe erfassen.")
    if not einnahme and not ausgabe:
        raise ValueError("Betrag fehlt — Einnahme oder Ausgabe muss größer als 0 sein.")
    if einnahme and kategorie not in EINNAHME_KATEGORIEN:
        raise ValueError(f"'{kategorie}' ist eine Ausgabe-Kategorie.")
    if ausgabe and kategorie not in AUSGABE_KATEGORIEN:
        raise ValueError(f"'{kategorie}' ist eine Einnahme-Kategorie.")

    eintrag = {
        "datum": pruefe_datum(datum, "Buchungsdatum"),
        "beschreibung": str(beschreibung or "").strip() or "Ohne Beschreibung",
        "kategorie": kategorie,
        "einnahme": einnahme,
        "ausgabe": ausgabe,
        "beleg": str(beleg or "").strip(),
    }
    return store.anlegen("buchungen", eintrag)


def journal(store: Store, jahr: int | None = None) -> list[dict]:
    """Buchungen chronologisch mit fortlaufendem Saldo."""
    zeilen = []
    saldo = 0.0
    for buchung in sorted(store.sammlung("buchungen"), key=lambda b: b.get("datum", "")):
        if jahr is not None and not str(buchung.get("datum", "")).startswith(str(jahr)):
            continue
        saldo += float(buchung.get("einnahme", 0)) - float(buchung.get("ausgabe", 0))
        zeile = dict(buchung)
        zeile["saldo"] = round(saldo, 2)
        zeilen.append(zeile)
    return zeilen


def euer(store: Store, jahr: int | None = None) -> dict:
    """Einnahmen-Überschuss-Rechnung: Summen je Kategorie und Ergebnis."""
    einnahmen = 0.0
    ausgaben = 0.0
    je_kategorie: dict[str, float] = {}
    for buchung in store.sammlung("buchungen"):
        if jahr is not None and not str(buchung.get("datum", "")).startswith(str(jahr)):
            continue
        e = float(buchung.get("einnahme", 0))
        a = float(buchung.get("ausgabe", 0))
        einnahmen += e
        ausgaben += a
        kategorie = buchung.get("kategorie", "Sonstige Ausgabe")
        je_kategorie[kategorie] = round(je_kategorie.get(kategorie, 0.0) + e + a, 2)
    return {
        "jahr": jahr,
        "einnahmen": round(einnahmen, 2),
        "ausgaben": round(ausgaben, 2),
        "gewinn": round(einnahmen - ausgaben, 2),
        "je_kategorie": dict(sorted(je_kategorie.items(), key=lambda kv: -kv[1])),
        "buchungen": sum(
            1
            for b in store.sammlung("buchungen")
            if jahr is None or str(b.get("datum", "")).startswith(str(jahr))
        ),
    }


def monatsuebersicht(store: Store, jahr: int, ruecklage_satz: float = 0.25) -> list[dict]:
    """Umsatz, Gewinn und Steuerrücklage je Monat, mit kumuliertem Umsatz."""
    monate: OrderedDict[str, dict] = OrderedDict()
    for monat in range(1, 13):
        schluessel = f"{jahr}-{monat:02d}"
        monate[schluessel] = {"monat": schluessel, "umsatz": 0.0, "ausgaben": 0.0}

    for buchung in store.sammlung("buchungen"):
        datum = str(buchung.get("datum", ""))
        schluessel = datum[:7]
        if schluessel not in monate:
            continue
        monate[schluessel]["umsatz"] += float(buchung.get("einnahme", 0))
        monate[schluessel]["ausgaben"] += float(buchung.get("ausgabe", 0))

    satz = max(0.0, min(1.0, float(ruecklage_satz)))
    kumuliert = 0.0
    zeilen = []
    for eintrag in monate.values():
        umsatz = round(eintrag["umsatz"], 2)
        gewinn = round(umsatz - eintrag["ausgaben"], 2)
        kumuliert = round(kumuliert + umsatz, 2)
        zeilen.append(
            {
                "monat": eintrag["monat"],
                "umsatz": umsatz,
                "ausgaben": round(eintrag["ausgaben"], 2),
                "gewinn": gewinn,
                "ruecklage_satz": satz,
                "ruecklage": round(max(0.0, gewinn) * satz, 2),
                "umsatz_kumuliert": kumuliert,
                "bis_grenze_laufend": round(GRENZE_LAUFEND - kumuliert, 2),
            }
        )
    return zeilen


def jahresumsatz(store: Store, jahr: int) -> float:
    """Summe aller Einnahmen eines Kalenderjahres."""
    return round(
        sum(
            float(b.get("einnahme", 0))
            for b in store.sammlung("buchungen")
            if str(b.get("datum", "")).startswith(str(jahr))
        ),
        2,
    )


def kleinunternehmer_status(
    laufender_umsatz: float, vorjahresumsatz: float = 0.0
) -> dict:
    """Prüft beide Grenzen des § 19 UStG und formuliert die Konsequenz."""
    laufend = round(float(laufender_umsatz), 2)
    vorjahr = round(float(vorjahresumsatz), 2)

    vorjahr_ok = vorjahr <= GRENZE_VORJAHR
    laufend_ok = laufend <= GRENZE_LAUFEND
    anwendbar = vorjahr_ok and laufend_ok

    hinweise: list[str] = []
    if not laufend_ok:
        hinweise.append(
            f"Die Obergrenze von {GRENZE_LAUFEND:,.0f} € ist im laufenden Jahr "
            "überschritten. Die Kleinunternehmerregelung endet ab diesem Umsatz "
            "sofort — ab jetzt Umsatzsteuer ausweisen und voranmelden."
            .replace(",", ".")
        )
    elif laufend >= GRENZE_LAUFEND * WARNSCHWELLE:
        hinweise.append(
            f"Noch {GRENZE_LAUFEND - laufend:,.0f} € bis zur Obergrenze von "
            f"{GRENZE_LAUFEND:,.0f} €. Ab dem Überschreiten gilt die Regelung "
            "sofort nicht mehr.".replace(",", ".")
        )
    if not vorjahr_ok:
        hinweise.append(
            f"Der Vorjahresumsatz lag über {GRENZE_VORJAHR:,.0f} € — für dieses "
            "Jahr ist die Kleinunternehmerregelung damit ausgeschlossen."
            .replace(",", ".")
        )
    elif laufend >= GRENZE_VORJAHR * WARNSCHWELLE and laufend_ok:
        hinweise.append(
            f"Der laufende Umsatz nähert sich {GRENZE_VORJAHR:,.0f} €. Wird diese "
            "Grenze dieses Jahr überschritten, entfällt die Kleinunternehmer-"
            "Eigenschaft ab dem 1. Januar des Folgejahres.".replace(",", ".")
        )
    if not hinweise:
        hinweise.append("Beide Grenzen sind eingehalten — keine Umsatzsteuerpflicht.")

    return {
        "anwendbar": anwendbar,
        "laufender_umsatz": laufend,
        "vorjahresumsatz": vorjahr,
        "grenze_vorjahr": GRENZE_VORJAHR,
        "grenze_laufend": GRENZE_LAUFEND,
        "bis_grenze_vorjahr": round(GRENZE_VORJAHR - laufend, 2),
        "bis_grenze_laufend": round(GRENZE_LAUFEND - laufend, 2),
        "warnung": not anwendbar or laufend >= GRENZE_VORJAHR * WARNSCHWELLE,
        "hinweise": hinweise,
    }


# --- Budget (geplante Anschaffungen) --------------------------------------

def budget_posten(
    store: Store, position: str, empfehlung: str = "", von: float = 0.0, bis: float = 0.0
) -> dict:
    eintrag = {
        "position": str(position or "").strip(),
        "empfehlung": str(empfehlung or "").strip(),
        "preis_von": _betrag(von, "Preis von"),
        "preis_bis": _betrag(bis, "Preis bis"),
        "beschafft": False,
    }
    if not eintrag["position"]:
        raise ValueError("Bitte eine Position angeben.")
    return store.anlegen("budget", eintrag)


def budget_uebersicht(store: Store) -> dict:
    posten = store.sammlung("budget")
    offen = [p for p in posten if not p.get("beschafft")]
    return {
        "posten": posten,
        "summe_von": round(sum(float(p.get("preis_von", 0)) for p in posten), 2),
        "summe_bis": round(sum(float(p.get("preis_bis", 0)) for p in posten), 2),
        "offen_von": round(sum(float(p.get("preis_von", 0)) for p in offen), 2),
        "offen_bis": round(sum(float(p.get("preis_bis", 0)) for p in offen), 2),
        "offen_anzahl": len(offen),
    }


def _betrag(wert, feld: str) -> float:
    try:
        zahl = round(float(wert or 0), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{feld} '{wert}' ist keine Zahl.") from exc
    if zahl < 0:
        raise ValueError(f"{feld} darf nicht negativ sein.")
    return zahl
