"""Onboarding und Freigabe von Dreh-Partnerinnen.

Das Modul bildet den Vetting-Ablauf aus dem Konzept als harte Reihenfolge ab:
Erst wenn **alle** Pflicht-Schritte dokumentiert sind, gilt eine Partnerin als
freigegeben — und erst dann lässt sich ein Dreh mit ihr über den Status
"geplant" hinausschieben (siehe :mod:`creatordock.drehs`).

Ein Widerruf wirkt rückwirkend: die Partnerin verliert die Freigabe, alle
zugehörigen Drehs werden gesperrt und für bereits veröffentlichtes Material
entsteht automatisch eine Aufgabe mit Frist.
"""

from __future__ import annotations

from datetime import date, timedelta

from creatordock.store import Store, pruefe_datum

# (Schlüssel, Beschriftung, Erklärung)
GATES: tuple[tuple[str, str, str], ...] = (
    (
        "erstkontakt",
        "Schriftlicher Erstkontakt dokumentiert",
        "Kontakt kam über eine seriöse Anzeige oder Community zustande, ohne Drängeln.",
    ),
    (
        "alter_verifiziert",
        "Alter per Ausweis geprüft (18+)",
        "Amtliches Lichtbilddokument im Original gesehen, vor dem ersten persönlichen Treffen.",
    ),
    (
        "kennenlernen",
        "Kennenlerngespräch geführt",
        "Video-Call oder Treffen an einem öffentlichen Ort vor dem Dreh.",
    ),
    (
        "release",
        "Model-Release / Vertrag unterschrieben",
        "Inhalte, Plattformen, Laufzeit und Verwertungsrechte schriftlich fixiert.",
    ),
    (
        "sti_nachweis",
        "STI-Test-Nachweise ausgetauscht",
        "Gegenseitig, aktuell, mit Datum — Szene-Standard.",
    ),
    (
        "verguetung",
        "Vergütung und Zahlungstermin fixiert",
        "Festgage, Revenue-Share oder Kombination — schriftlich, inklusive Termin.",
    ),
    (
        "widerrufsfrist",
        "Widerrufsfrist vereinbart",
        "Frist, bis wann das Material zurückgezogen werden kann, steht im Vertrag.",
    ),
)

GATE_SCHLUESSEL = tuple(g[0] for g in GATES)

STATUS_KONTAKT = "kontakt"
STATUS_VETTING = "vetting"
STATUS_FREIGEGEBEN = "freigegeben"
STATUS_WIDERRUFEN = "widerrufen"
STATUS_ABGELEHNT = "abgelehnt"

STATUS_WERTE = (
    STATUS_KONTAKT,
    STATUS_VETTING,
    STATUS_FREIGEGEBEN,
    STATUS_WIDERRUFEN,
    STATUS_ABGELEHNT,
)

# Nach einem Widerruf: Frist, innerhalb derer Material offline sein soll.
WIDERRUF_FRIST_TAGE = 7


def anlegen(store: Store, pseudonym: str, **felder) -> dict:
    """Legt eine neue Partnerin an — bewusst nur mit Pseudonym.

    Klarnamen und Dokumente gehören nicht in die App; ``aktenzeichen`` verweist
    auf die verschlüsselte Ablage außerhalb.
    """
    pseudonym = str(pseudonym or "").strip()
    if not pseudonym:
        raise ValueError("Bitte ein Pseudonym angeben (kein Klarname).")
    if any(p.get("pseudonym", "").lower() == pseudonym.lower() for p in store.sammlung("partnerinnen")):
        raise ValueError(f"Das Pseudonym '{pseudonym}' ist bereits vergeben.")

    eintrag = {
        "pseudonym": pseudonym,
        "status": STATUS_KONTAKT,
        "quelle": str(felder.get("quelle", "")).strip(),
        "aktenzeichen": str(felder.get("aktenzeichen", "")).strip(),
        "kontakt_kanal": str(felder.get("kontakt_kanal", "")).strip(),
        "notizen": str(felder.get("notizen", "")).strip(),
        "gates": {schluessel: None for schluessel in GATE_SCHLUESSEL},
        "widerruf": None,
        "sti_gueltig_bis": "",
    }
    return store.anlegen("partnerinnen", eintrag)


def gate_setzen(
    store: Store,
    kennung: str,
    gate: str,
    erfuellt: bool = True,
    datum: str | None = None,
    notiz: str = "",
) -> dict:
    """Hakt einen Vetting-Schritt ab (oder nimmt die Bestätigung zurück)."""
    if gate not in GATE_SCHLUESSEL:
        raise ValueError(
            f"Unbekannter Schritt '{gate}'. Möglich: {', '.join(GATE_SCHLUESSEL)}"
        )
    partnerin = store.finden("partnerinnen", kennung)
    if partnerin.get("status") == STATUS_WIDERRUFEN:
        raise ValueError(
            f"{partnerin['pseudonym']} hat widerrufen — es lassen sich keine "
            "Schritte mehr abhaken. Bei Bedarf zuerst den Widerruf zurücknehmen."
        )

    gates = partnerin.setdefault("gates", {})
    if erfuellt:
        gates[gate] = {
            "datum": pruefe_datum(datum or date.today().isoformat()),
            "notiz": str(notiz or "").strip(),
        }
    else:
        gates[gate] = None
    _status_neu_berechnen(partnerin)
    return partnerin


def sti_gueltigkeit_setzen(store: Store, kennung: str, gueltig_bis: str) -> dict:
    """Hinterlegt, bis wann der STI-Nachweis als aktuell gilt."""
    partnerin = store.finden("partnerinnen", kennung)
    partnerin["sti_gueltig_bis"] = pruefe_datum(gueltig_bis, "Gültig bis")
    return partnerin


def ablehnen(store: Store, kennung: str, grund: str = "") -> dict:
    """Beendet das Onboarding ohne Freigabe."""
    partnerin = store.finden("partnerinnen", kennung)
    partnerin["status"] = STATUS_ABGELEHNT
    partnerin["notizen"] = _notiz_anhaengen(
        partnerin.get("notizen", ""), f"Abgelehnt am {date.today().isoformat()}: {grund}".strip(": ")
    )
    return partnerin


def widerrufen(store: Store, kennung: str, datum: str | None = None, grund: str = "") -> dict:
    """Verarbeitet einen Widerruf und zieht alle Folgen daraus.

    Alle Drehs mit dieser Partnerin werden gesperrt. Für bereits
    veröffentlichtes Material entsteht eine Aufgabe mit Frist, damit das
    Zurückziehen nicht untergeht.
    """
    partnerin = store.finden("partnerinnen", kennung)
    stichtag = pruefe_datum(datum or date.today().isoformat(), "Widerrufsdatum")
    partnerin["status"] = STATUS_WIDERRUFEN
    partnerin["widerruf"] = {"datum": stichtag, "grund": str(grund or "").strip()}

    frist = (date.fromisoformat(stichtag) + timedelta(days=WIDERRUF_FRIST_TAGE)).isoformat()
    betroffen: list[dict] = []
    veroeffentlicht: list[str] = []
    for dreh in store.sammlung("drehs"):
        if kennung in dreh.get("partner_ids", []):
            dreh["gesperrt"] = True
            betroffen.append(dreh)
            if dreh.get("status") == "veröffentlicht":
                veroeffentlicht.append(dreh["id"])

    if veroeffentlicht:
        store.anlegen(
            "fahrplan",
            {
                "titel": (
                    f"Widerruf {partnerin['pseudonym']}: Material zurückziehen "
                    f"({', '.join(veroeffentlicht)})"
                ),
                "bereich": "Recht",
                "prioritaet": "hoch",
                "faellig": frist,
                "status": "offen",
                "notiz": (
                    "Veröffentlichte Inhalte auf allen Plattformen depublizieren "
                    "und die Löschung schriftlich bestätigen."
                ),
            },
        )
    return partnerin


def widerruf_zuruecknehmen(store: Store, kennung: str) -> dict:
    """Nimmt einen versehentlich erfassten Widerruf zurück."""
    partnerin = store.finden("partnerinnen", kennung)
    partnerin["widerruf"] = None
    for dreh in store.sammlung("drehs"):
        if kennung in dreh.get("partner_ids", []):
            dreh["gesperrt"] = False
    _status_neu_berechnen(partnerin)
    return partnerin


# --- Auswertung -----------------------------------------------------------

def offene_gates(partnerin: dict) -> list[str]:
    """Liefert die Beschriftungen der noch fehlenden Pflicht-Schritte."""
    gates = partnerin.get("gates") or {}
    return [label for schluessel, label, _ in GATES if not gates.get(schluessel)]


def ist_freigegeben(partnerin: dict) -> bool:
    if partnerin.get("status") in (STATUS_WIDERRUFEN, STATUS_ABGELEHNT):
        return False
    return not offene_gates(partnerin)


def sti_abgelaufen(partnerin: dict, stichtag: str | None = None) -> bool:
    """True, wenn ein Gültigkeitsdatum hinterlegt und überschritten ist."""
    bis = partnerin.get("sti_gueltig_bis")
    if not bis:
        return False
    heute = date.fromisoformat(stichtag) if stichtag else date.today()
    return date.fromisoformat(bis) < heute


def uebersicht(store: Store) -> list[dict]:
    """Kompakte Liste aller Partnerinnen inklusive berechneter Felder."""
    zeilen = []
    for partnerin in store.sammlung("partnerinnen"):
        _status_neu_berechnen(partnerin)
        fehlend = offene_gates(partnerin)
        zeilen.append(
            {
                "id": partnerin["id"],
                "pseudonym": partnerin["pseudonym"],
                "status": partnerin["status"],
                "freigegeben": ist_freigegeben(partnerin),
                "erledigt": len(GATES) - len(fehlend),
                "gesamt": len(GATES),
                "offen": fehlend,
                "sti_gueltig_bis": partnerin.get("sti_gueltig_bis", ""),
                "sti_abgelaufen": sti_abgelaufen(partnerin),
                "quelle": partnerin.get("quelle", ""),
                "aktenzeichen": partnerin.get("aktenzeichen", ""),
                "widerruf": partnerin.get("widerruf"),
            }
        )
    return zeilen


def gate_liste() -> list[dict]:
    """Die Vetting-Schritte als JSON-fähige Liste für die Oberfläche."""
    return [
        {"schluessel": s, "label": label, "erklaerung": erklaerung}
        for s, label, erklaerung in GATES
    ]


def _status_neu_berechnen(partnerin: dict) -> None:
    """Hält den Status konsistent zu den abgehakten Schritten."""
    if partnerin.get("status") in (STATUS_WIDERRUFEN, STATUS_ABGELEHNT):
        if partnerin.get("status") == STATUS_WIDERRUFEN and not partnerin.get("widerruf"):
            pass  # Widerruf wurde zurückgenommen — unten neu einstufen.
        else:
            return
    gates = partnerin.get("gates") or {}
    erledigt = sum(1 for schluessel in GATE_SCHLUESSEL if gates.get(schluessel))
    if erledigt == len(GATE_SCHLUESSEL):
        partnerin["status"] = STATUS_FREIGEGEBEN
    elif erledigt == 0:
        partnerin["status"] = STATUS_KONTAKT
    else:
        partnerin["status"] = STATUS_VETTING


def _notiz_anhaengen(vorhanden: str, neu: str) -> str:
    vorhanden = (vorhanden or "").strip()
    return f"{vorhanden}\n{neu}".strip() if vorhanden else neu
