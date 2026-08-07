"""Kanal-Register und OPSEC-Checkliste für die Trennung von Persona und Person.

Der heikelste Teil des Projekts ist nicht die Technik, sondern die Trennung
zwischen Künstlernamen und echter Identität. Dieses Modul führt deshalb Buch
über jeden Kanal (eigene Mailadresse? Zwei-Faktor aktiv?) und über die
wiederkehrenden OPSEC-Punkte, die vor jedem Upload zu prüfen sind.
"""

from __future__ import annotations

from creatordock.store import Store

ZWECKE = ("Paid-Plattform", "NSFW-Reichweite", "SFW-Trichter", "Auszahlung/Backoffice")

# Empfohlener Grundaufbau aus dem Konzept.
STANDARD_KANAELE = (
    {"plattform": "OnlyFans", "zweck": "Paid-Plattform", "notizen": "Haupterlösquelle, Link aus allen Profilen."},
    {"plattform": "Fansly", "zweck": "Paid-Plattform", "notizen": "Zweitplattform, streut das Sperr-Risiko."},
    {"plattform": "Pornhub Model Program", "zweck": "NSFW-Reichweite", "notizen": "Verifizierung nötig, Reichweite + Zusatzerlös."},
    {"plattform": "X/Twitter", "zweck": "NSFW-Reichweite", "notizen": "Hauptkanal für Teaser, Link im Profil."},
    {"plattform": "Reddit", "zweck": "NSFW-Reichweite", "notizen": "Nur passende NSFW-Subs, Regeln je Sub vorher lesen."},
    {"plattform": "Instagram", "zweck": "SFW-Trichter", "notizen": "Ausschließlich SFW — kein expliziter Inhalt."},
    {"plattform": "TikTok", "zweck": "SFW-Trichter", "notizen": "Ausschließlich SFW, Lifestyle/Backstage."},
)

# Punkte, die dauerhaft gelten (Setup) bzw. vor jedem Upload zu prüfen sind.
OPSEC_PUNKTE = (
    ("mail", "Eigene E-Mail-Adresse nur für das Projekt", "setup"),
    ("nummer", "Eigene Telefonnummer / eSIM nur für das Projekt", "setup"),
    ("zahlung", "Auszahlungskonto getrennt vom privaten Konto", "setup"),
    ("2fa", "Zwei-Faktor-Authentisierung auf allen Kanälen aktiv", "setup"),
    ("wasserzeichen", "Einheitliches Wasserzeichen definiert", "setup"),
    ("hintergrund", "Drehort zeigt keine erkennbaren Orte, Adressen oder Dokumente", "pro_upload"),
    ("metadaten", "Metadaten (GPS, Gerätekennung) vor dem Upload entfernt", "pro_upload"),
    ("tattoos", "Eindeutige Merkmale geprüft (Tattoos, Narben, Schmuck)", "pro_upload"),
    ("gesicht", "Gesichtsregel des Model-Release eingehalten", "pro_upload"),
    ("reverse", "Profilbilder nicht anderswo verwendet (Rückwärtssuche)", "pro_upload"),
)


def anlegen(store: Store, plattform: str, **felder) -> dict:
    plattform = str(plattform or "").strip()
    if not plattform:
        raise ValueError("Bitte eine Plattform angeben.")
    zweck = str(felder.get("zweck", "") or "NSFW-Reichweite")
    if zweck not in ZWECKE:
        raise ValueError(f"Unbekannter Zweck '{zweck}'. Möglich: {', '.join(ZWECKE)}")

    handle = str(felder.get("handle", "")).strip()
    # Mehrere Accounts je Plattform sind erlaubt, ein exaktes Duplikat nicht.
    for vorhanden in store.sammlung("kanaele"):
        if (vorhanden.get("plattform", "").lower() == plattform.lower()
                and vorhanden.get("handle", "").lower() == handle.lower()):
            raise ValueError(
                f"'{plattform}'"
                + (f" mit Handle '{handle}'" if handle else " ohne Handle")
                + " steht bereits im Register."
            )

    eintrag = {
        "plattform": plattform,
        "handle": handle,
        "zweck": zweck,
        "email": str(felder.get("email", "")).strip(),
        "zwei_faktor": bool(felder.get("zwei_faktor", False)),
        "verifiziert": bool(felder.get("verifiziert", False)),
        "angelegt": bool(felder.get("angelegt", False)),
        "notizen": str(felder.get("notizen", "")).strip(),
    }
    return store.anlegen("kanaele", eintrag)


def aktualisieren(store: Store, kennung: str, **felder) -> dict:
    kanal = store.finden("kanaele", kennung)
    for feld in ("handle", "email", "notizen"):
        if feld in felder:
            kanal[feld] = str(felder[feld] or "").strip()
    for feld in ("zwei_faktor", "verifiziert", "angelegt"):
        if feld in felder:
            kanal[feld] = bool(felder[feld])
    if "zweck" in felder:
        if felder["zweck"] not in ZWECKE:
            raise ValueError(f"Unbekannter Zweck '{felder['zweck']}'.")
        kanal["zweck"] = felder["zweck"]
    return kanal


def opsec_status(store: Store) -> dict:
    """Bewertet die Setup-Punkte der OPSEC-Checkliste anhand des Kanal-Registers."""
    projekt = store.laden()["projekt"]
    haken: dict[str, bool] = dict(projekt.get("opsec", {}))

    kanaele = store.sammlung("kanaele")
    angelegte = [k for k in kanaele if k.get("angelegt")]
    # Zwei Punkte lassen sich aus den Kanaldaten ableiten statt manuell abhaken.
    if angelegte:
        haken["2fa"] = all(k.get("zwei_faktor") for k in angelegte)
        haken["mail"] = all(k.get("email") for k in angelegte)

    setup = [p for p in OPSEC_PUNKTE if p[2] == "setup"]
    erledigt = sum(1 for schluessel, _, _ in setup if haken.get(schluessel))
    return {
        "punkte": [
            {
                "schluessel": schluessel,
                "label": label,
                "art": art,
                "erledigt": bool(haken.get(schluessel)),
            }
            for schluessel, label, art in OPSEC_PUNKTE
        ],
        "setup_erledigt": erledigt,
        "setup_gesamt": len(setup),
        "kanaele_ohne_2fa": [
            k.get("plattform", k["id"]) for k in angelegte if not k.get("zwei_faktor")
        ],
    }


def opsec_setzen(store: Store, schluessel: str, erledigt: bool = True) -> dict:
    gueltig = {p[0] for p in OPSEC_PUNKTE}
    if schluessel not in gueltig:
        raise ValueError(f"Unbekannter OPSEC-Punkt '{schluessel}'.")
    projekt = store.laden()["projekt"]
    projekt.setdefault("opsec", {})[schluessel] = bool(erledigt)
    return opsec_status(store)


def uebersicht(store: Store) -> list[dict]:
    reihenfolge = {zweck: i for i, zweck in enumerate(ZWECKE)}
    return sorted(
        store.sammlung("kanaele"),
        key=lambda k: (reihenfolge.get(k.get("zweck", ""), 99), k.get("plattform", "")),
    )
