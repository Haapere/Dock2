"""Das Angebot an Dreh-Partnerinnen — und seine Durchsetzung.

Der Vertrag regelt, was rechtlich gilt. Dieses Modul regelt, was du
**anbietest**: gesichtslos drehen, Sichtungsrecht vor Veröffentlichung,
Begleitperson am Set, Abbruch jederzeit. Das ist das, was eine Partnerin
überhaupt erst zusagen lässt — und im Konzept stand es nur als Fließtext.

Zwei Ebenen:

* **Standardangebot** — was du jeder Partnerin zusagst, einmal konfiguriert.
* **Vereinbarung** — was eine einzelne Partnerin daraus gewählt hat. Sie
  überschreibt den Standard punktuell.

Der entscheidende Teil ist die Durchsetzung: aus der Vereinbarung entstehen
**Auflagen**. Hat eine Partnerin "ohne Gesicht" gewählt, lässt sich ihr Dreh
nicht auf "veröffentlicht" setzen, solange nicht bestätigt ist, dass das
Gesicht unkenntlich ist. Aus einem Versprechen wird so eine Sperre.
"""

from __future__ import annotations

from typing import NamedTuple

from creatordock.store import Store


class Option(NamedTuple):
    schluessel: str
    label: str
    kategorie: str
    typ: str  # "ja_nein" | "auswahl"
    standard: object
    wer: str  # "zusage" = du sagst es zu | "wahl" = sie entscheidet
    erklaerung: str
    optionen: tuple[str, ...] = ()


KATEGORIEN = (
    "Anonymität",
    "Am Set",
    "Nach dem Dreh",
    "Verwertung",
    "Vergütung",
)

KATALOG: tuple[Option, ...] = (
    # --- Anonymität ---------------------------------------------------
    Option(
        "gesicht", "Gesicht im Bild", "Anonymität", "auswahl",
        "ohne Gesicht", "wahl",
        "Der wichtigste Hebel: Viele drehen nur, wenn das Gesicht draußen bleibt.",
        ("mit Gesicht", "ohne Gesicht", "unkenntlich gemacht"),
    ),
    Option(
        "merkmale_abdecken", "Tattoos und Narben abdecken", "Anonymität", "ja_nein",
        False, "wahl",
        "Erkennungsmerkmale sind so eindeutig wie ein Gesicht.",
    ),
    Option(
        "stimme", "Stimme im Ton", "Anonymität", "auswahl",
        "unverändert", "wahl",
        "Stimmen sind wiedererkennbar — Verzerren oder Stummschalten ist möglich.",
        ("unverändert", "verzerrt", "kein Ton"),
    ),
    Option(
        "kuenstlername_ihrs", "Sie tritt unter eigenem Künstlernamen auf",
        "Anonymität", "ja_nein", True, "wahl",
        "Nie unter dem Klarnamen, auch nicht in Dateinamen oder Beschreibungen.",
    ),

    # --- Am Set -------------------------------------------------------
    Option(
        "begleitperson", "Begleitperson darf mitkommen", "Am Set", "ja_nein",
        True, "zusage",
        "Eine Vertrauensperson vor Ort kostet dich nichts und nimmt enorm viel Druck.",
    ),
    Option(
        "abbruchwort", "Abbruchwort gilt ohne Diskussion", "Am Set", "ja_nein",
        True, "zusage",
        "Ein Wort, das alles sofort stoppt — auch mitten in der Aufnahme.",
    ),
    Option(
        "keine_zuschauer", "Keine weiteren Personen am Set", "Am Set", "ja_nein",
        True, "zusage",
        "Nur ihr beide (plus ihre Begleitperson). Kein Team, kein Publikum.",
    ),
    Option(
        "grenzen_schriftlich", "Grenzen vorher schriftlich festgehalten",
        "Am Set", "ja_nein", True, "zusage",
        "Was nicht auf der Liste steht, passiert nicht. Auch nicht spontan.",
    ),
    Option(
        "oeffentliches_kennenlernen", "Kennenlernen an einem Ort ihrer Wahl",
        "Am Set", "ja_nein", True, "zusage",
        "Video-Call oder öffentlicher Ort — sie entscheidet.",
    ),

    # --- Nach dem Dreh ------------------------------------------------
    Option(
        "sichtungsrecht", "Sichtung und Freigabe vor der Veröffentlichung",
        "Nach dem Dreh", "ja_nein", True, "wahl",
        "Sie sieht den fertigen Schnitt und kann Szenen streichen lassen.",
    ),
    Option(
        "widerruf_tage", "Widerrufsfrist nach dem Dreh", "Nach dem Dreh", "auswahl",
        "14 Tage", "zusage",
        "Bis zum Ablauf kann sie alles zurückziehen, ohne Begründung.",
        ("7 Tage", "14 Tage", "30 Tage", "jederzeit"),
    ),
    Option(
        "loeschbestaetigung", "Schriftliche Löschbestätigung nach Widerruf",
        "Nach dem Dreh", "ja_nein", True, "zusage",
        "Sie bekommt schwarz auf weiß, dass und wann alles offline ist.",
    ),
    Option(
        "kopie_material", "Sie bekommt eine Kopie ihres Materials",
        "Nach dem Dreh", "ja_nein", False, "wahl",
        "Manche wollen das Material für ihr eigenes Portfolio.",
    ),

    # --- Verwertung ---------------------------------------------------
    Option(
        "wasserzeichen", "Wasserzeichen auf allem Material", "Verwertung", "ja_nein",
        True, "zusage",
        "Erschwert das Weiterverbreiten außerhalb der vereinbarten Plattformen.",
    ),
    Option(
        "nur_vereinbarte_plattformen", "Nur auf den vereinbarten Plattformen",
        "Verwertung", "ja_nein", True, "zusage",
        "Keine Zweitverwertung, kein Weiterverkauf, keine Weitergabe an Dritte.",
    ),
    Option(
        "metadaten_entfernt", "Metadaten vor jedem Upload entfernt",
        "Verwertung", "ja_nein", True, "zusage",
        "GPS und Gerätekennung verraten sonst Drehort und Kamera.",
    ),
    Option(
        "exklusivitaet", "Exklusivität verlangt", "Verwertung", "ja_nein",
        False, "zusage",
        "Ohne Exklusivität kann sie parallel für andere drehen — das erhöht "
        "deine Chancen bei erfahrenen Darstellerinnen deutlich.",
    ),
    Option(
        "laufzeit", "Laufzeit der Rechteeinräumung", "Verwertung", "auswahl",
        "24 Monate", "zusage",
        "Unbefristet schreckt ab. Eine Befristung ist ein starkes Argument.",
        ("12 Monate", "24 Monate", "36 Monate", "unbefristet"),
    ),

    # --- Vergütung ----------------------------------------------------
    Option(
        "modell", "Vergütungsmodell", "Vergütung", "auswahl",
        "Festgage", "wahl",
        "Festgage ist für sie planbar, Beteiligung für dich liquiditätsschonend.",
        ("Festgage", "Umsatzbeteiligung", "Festgage + Beteiligung"),
    ),
    Option(
        "erfolgsunabhaengig", "Vergütung unabhängig vom Erfolg", "Vergütung", "ja_nein",
        True, "zusage",
        "Sie trägt nicht dein Vermarktungsrisiko. Das ist Szene-Standard.",
    ),
    Option(
        "zahlung_am_drehtag", "Auszahlung am Drehtag", "Vergütung", "ja_nein",
        True, "zusage",
        "Bar oder sofortige Überweisung. Das stärkste Vertrauenssignal überhaupt.",
    ),
    Option(
        "reisekosten", "Reisekosten werden erstattet", "Vergütung", "ja_nein",
        True, "zusage",
        "Kleiner Betrag, große Wirkung bei der Zusage.",
    ),
)

NACH_SCHLUESSEL = {option.schluessel: option for option in KATALOG}


# --- Auflagen: aus Zusagen werden Sperren ---------------------------------

def _auflage_gesicht(wert) -> str | None:
    if wert == "ohne Gesicht":
        return "Gesicht kommt im gesamten Material nicht vor"
    if wert == "unkenntlich gemacht":
        return "Gesicht ist durchgängig unkenntlich gemacht (geprüft, Bild für Bild)"
    return None


def _auflage_stimme(wert) -> str | None:
    if wert == "verzerrt":
        return "Stimme ist verzerrt"
    if wert == "kein Ton":
        return "Tonspur ist entfernt"
    return None


# Schlüssel -> Funktion, die aus dem vereinbarten Wert eine Auflage macht.
AUFLAGE_REGELN = {
    "gesicht": _auflage_gesicht,
    "stimme": _auflage_stimme,
    "merkmale_abdecken": lambda w: "Tattoos und Narben sind abgedeckt oder retuschiert" if w else None,
    "sichtungsrecht": lambda w: "Partnerin hat den fertigen Schnitt gesichtet und freigegeben" if w else None,
    "wasserzeichen": lambda w: "Wasserzeichen ist gesetzt" if w else None,
    "metadaten_entfernt": lambda w: "Metadaten (GPS, Gerätekennung) sind entfernt" if w else None,
    "nur_vereinbarte_plattformen": lambda w: "Nur die vereinbarten Plattformen werden bespielt" if w else None,
    "kuenstlername_ihrs": lambda w: "Nirgends Klarname — auch nicht in Dateinamen und Beschreibungen" if w else None,
}

# Auflagen, die sich auf das Material beziehen und deshalb auch für Solo-Drehs
# gelten. Alles andere (Gesicht, Stimme, Sichtungsrecht) betrifft eine
# Partnerin und ergibt ohne sie keinen Sinn.
MATERIALBEZOGEN = frozenset({
    "wasserzeichen",
    "metadaten_entfernt",
    "nur_vereinbarte_plattformen",
})


# --- Standardangebot ------------------------------------------------------

def standard(store: Store) -> dict:
    """Das Standardangebot; fehlende Schlüssel werden mit dem Default gefüllt."""
    gespeichert = store.laden()["projekt"].setdefault("angebot", {})
    return {
        option.schluessel: gespeichert.get(option.schluessel, option.standard)
        for option in KATALOG
    }


def standard_setzen(store: Store, schluessel: str, wert) -> dict:
    option = _option(schluessel)
    store.laden()["projekt"].setdefault("angebot", {})[schluessel] = _pruefe_wert(option, wert)
    return standard(store)


# --- Vereinbarung je Partnerin -------------------------------------------

def vereinbarung(store: Store, partner_id: str) -> dict:
    """Das für diese Partnerin geltende Angebot (Standard + ihre Wahl)."""
    partnerin = store.finden("partnerinnen", partner_id)
    werte = standard(store)
    werte.update(partnerin.get("vereinbarung") or {})
    return werte


def vereinbarung_setzen(store: Store, partner_id: str, schluessel: str, wert) -> dict:
    option = _option(schluessel)
    partnerin = store.finden("partnerinnen", partner_id)
    partnerin.setdefault("vereinbarung", {})[schluessel] = _pruefe_wert(option, wert)
    return vereinbarung(store, partner_id)


def vereinbarung_zuruecksetzen(store: Store, partner_id: str, schluessel: str) -> dict:
    """Nimmt eine abweichende Wahl zurück — es gilt wieder der Standard."""
    partnerin = store.finden("partnerinnen", partner_id)
    (partnerin.get("vereinbarung") or {}).pop(schluessel, None)
    return vereinbarung(store, partner_id)


def abweichungen(store: Store, partner_id: str) -> list[dict]:
    """Wo diese Partnerin vom Standardangebot abweicht."""
    partnerin = store.finden("partnerinnen", partner_id)
    eigene = partnerin.get("vereinbarung") or {}
    grund = standard(store)
    return [
        {
            "schluessel": schluessel,
            "label": NACH_SCHLUESSEL[schluessel].label,
            "standard": grund.get(schluessel),
            "vereinbart": wert,
        }
        for schluessel, wert in eigene.items()
        if schluessel in NACH_SCHLUESSEL and wert != grund.get(schluessel)
    ]


# --- Auflagen für einen Dreh ---------------------------------------------

def auflagen_fuer_dreh(store: Store, dreh: dict) -> list[dict]:
    """Alle Bedingungen, die vor der Veröffentlichung erfüllt sein müssen.

    Solo-Drehs erben die Auflagen aus dem Standardangebot (Wasserzeichen,
    Metadaten), Drehs mit Partnerinnen zusätzlich deren Wahl.
    """
    gesammelt: dict[str, dict] = {}

    def aufnehmen(schluessel: str, wert, pseudonym: str | None) -> None:
        regel = AUFLAGE_REGELN.get(schluessel)
        if regel is None:
            return
        text = regel(wert)
        if not text:
            return
        # Je Auflage genügt eine Bestätigung, die Namen werden gesammelt.
        eintrag = gesammelt.setdefault(
            schluessel, {"schluessel": schluessel, "text": text, "fuer": []}
        )
        if pseudonym and pseudonym not in eintrag["fuer"]:
            eintrag["fuer"].append(pseudonym)
        # Die strengere Formulierung gewinnt (z. B. "ohne Gesicht").
        eintrag["text"] = text if len(text) > len(eintrag["text"]) else eintrag["text"]

    partner_ids = dreh.get("partner_ids", [])
    if partner_ids:
        for kennung in partner_ids:
            try:
                partnerin = store.finden("partnerinnen", kennung)
            except KeyError:
                continue
            werte = vereinbarung(store, kennung)
            for schluessel, wert in werte.items():
                aufnehmen(schluessel, wert, partnerin.get("pseudonym", kennung))
    else:
        # Solo-Dreh: nur was das Material selbst betrifft.
        for schluessel, wert in standard(store).items():
            if schluessel in MATERIALBEZOGEN:
                aufnehmen(schluessel, wert, None)

    bestaetigt = dreh.get("auflagen_bestaetigt") or {}
    for eintrag in gesammelt.values():
        eintrag["bestaetigt"] = bool(bestaetigt.get(eintrag["schluessel"]))
    return sorted(gesammelt.values(), key=lambda a: a["schluessel"])


def offene_auflagen(store: Store, dreh: dict) -> list[dict]:
    return [a for a in auflagen_fuer_dreh(store, dreh) if not a["bestaetigt"]]


# --- Darstellung ----------------------------------------------------------

def katalog(store: Store | None = None, partner_id: str | None = None) -> list[dict]:
    """Der Optionskatalog mit aktuellen Werten — für Oberfläche und CLI."""
    werte = {}
    if store is not None:
        werte = vereinbarung(store, partner_id) if partner_id else standard(store)
    eigene = {}
    if store is not None and partner_id:
        eigene = store.finden("partnerinnen", partner_id).get("vereinbarung") or {}
    return [
        {
            "schluessel": o.schluessel,
            "label": o.label,
            "kategorie": o.kategorie,
            "typ": o.typ,
            "optionen": list(o.optionen),
            "wer": o.wer,
            "erklaerung": o.erklaerung,
            "wert": werte.get(o.schluessel, o.standard),
            "abweichend": o.schluessel in eigene,
            # Nur wahr, wenn der *aktuelle* Wert tatsächlich eine Auflage
            # auslöst — "Stimme: unverändert" ist keine.
            "erzeugt_auflage": bool(
                o.schluessel in AUFLAGE_REGELN
                and AUFLAGE_REGELN[o.schluessel](werte.get(o.schluessel, o.standard))
            ),
        }
        for o in KATALOG
    ]


def angebotsblatt(store: Store, partner_id: str | None = None) -> str:
    """Das Angebot als lesbarer Text — genau das, was sie vorab bekommt."""
    werte = vereinbarung(store, partner_id) if partner_id else standard(store)
    zeilen: list[str] = []
    for kategorie in KATEGORIEN:
        posten = []
        for option in KATALOG:
            if option.kategorie != kategorie:
                continue
            wert = werte.get(option.schluessel, option.standard)
            if option.typ == "ja_nein":
                if not wert:
                    continue
                posten.append(f"- {option.label}")
            else:
                posten.append(f"- {option.label}: {wert}")
        if posten:
            zeilen.append(f"**{kategorie}**")
            zeilen.extend(posten)
            zeilen.append("")
    return "\n".join(zeilen).strip()


def _option(schluessel: str) -> Option:
    if schluessel not in NACH_SCHLUESSEL:
        raise ValueError(
            f"Unbekannte Angebots-Option '{schluessel}'. Möglich: "
            + ", ".join(NACH_SCHLUESSEL)
        )
    return NACH_SCHLUESSEL[schluessel]


def _pruefe_wert(option: Option, wert):
    if option.typ == "ja_nein":
        return bool(wert)
    text = str(wert)
    if text not in option.optionen:
        raise ValueError(
            f"'{text}' ist bei '{option.label}' nicht möglich. Erlaubt: "
            + ", ".join(option.optionen)
        )
    return text
