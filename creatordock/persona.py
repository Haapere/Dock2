"""Aufbau der Social-Media-Identität.

Das Konzept nennt „Künstlername, getrennt von der echten Identität“ und
„konsistentes Wasserzeichen“ — als Stichpunkte. Hier wird daraus ein Ablauf:
Namenskandidaten mit Verfügbarkeitsprüfung, ein Steckbrief, der die Nische
festnagelt, daraus generierte Profiltexte je Plattform (mit den echten
Zeichenlimits) und ein Stufenplan für die ersten Wochen.

Bewusst ohne Automatik nach außen: Die App prüft keine Handles online und
postet nichts. Sie sagt dir, was zu prüfen ist, und hält fest, was du
herausgefunden hast.
"""

from __future__ import annotations

from creatordock.store import Store

# --- Steckbrief: die inhaltliche Grundlage --------------------------------

STECKBRIEF_FELDER = (
    ("nische", "Nische",
     "In einem Satz: Was bekommt man hier, das man woanders nicht bekommt?"),
    ("zielgruppe", "Zielgruppe",
     "Wen sprichst du an? Je enger, desto besser funktioniert der Kanal."),
    ("tonalitaet", "Tonalität",
     "Wie klingst du? Z. B. trocken-humorvoll, dominant, verspielt, nahbar."),
    ("alleinstellung", "Alleinstellungsmerkmal",
     "Der eine Grund zu abonnieren statt weiterzuscrollen."),
    ("tabus", "Was es hier nicht gibt",
     "Klare Abgrenzung schafft Vertrauen — bei Fans wie bei Partnerinnen."),
    ("rhythmus", "Versprochener Rhythmus",
     "Was Abonnenten verlässlich bekommen, z. B. 3 Teaser + 1 Release pro Woche."),
)

IDENTITAET_FELDER = (
    ("wasserzeichen", "Wasserzeichen-Text",
     "Erscheint auf jedem Bild und Video. Meist der Künstlername."),
    ("farben", "Farbwelt",
     "Zwei bis drei Farben, die überall wiederkehren."),
    ("profilbild", "Profilbild-Konzept",
     "Muss auf allen Kanälen dasselbe sein — und nirgends sonst existieren."),
    ("bio_link", "Bio-Link",
     "Eine Sammelseite, die auf alle Kanäle zeigt. Nur ein Link im Profil."),
)

# --- Plattformen: echte Grenzen und Spielregeln ---------------------------

class _Regel(dict):
    pass


PLATTFORM_REGELN = {
    "X/Twitter": {
        "bio_limit": 160,
        "inhalt": "NSFW erlaubt (Konto als sensibel markieren)",
        "link": "Ein Link im Profil, weitere in Beiträgen",
        "hinweise": [
            "Konto in den Einstellungen als „sensible Inhalte“ markieren, sonst Shadowban-Risiko.",
            "Ohne Markierung greift die automatische Moderation — Reichweite bricht ein.",
        ],
    },
    "Reddit": {
        "bio_limit": 200,
        "inhalt": "NSFW erlaubt, aber je Sub eigene Regeln",
        "link": "Oft erst ab bestimmtem Karma erlaubt",
        "hinweise": [
            "Regeln jedes Subs vorher lesen — Verstöße führen zu dauerhaften Sperren.",
            "Viele Subs verlangen Verifizierung mit handschriftlichem Schild.",
            "Erst kommentieren und Karma sammeln, dann posten.",
        ],
    },
    "Instagram": {
        "bio_limit": 150,
        "inhalt": "NUR SFW — kein expliziter Inhalt",
        "link": "Ein Link im Profil",
        "hinweise": [
            "Direkte Links zu Paid-Plattformen führen regelmäßig zur Sperre.",
            "Als reiner Trichter behandeln: Lifestyle, Backstage, Andeutung.",
        ],
    },
    "TikTok": {
        "bio_limit": 80,
        "inhalt": "NUR SFW — strengste Moderation",
        "link": "Erst ab Mindest-Followerzahl",
        "hinweise": [
            "Auch Andeutungen werden erkannt. Sehr konservativ bleiben.",
            "Konto ist jederzeit verlierbar — niemals einzige Reichweitenquelle.",
        ],
    },
    "OnlyFans": {
        "bio_limit": 1000,
        "inhalt": "Paid-Plattform, expliziter Inhalt",
        "link": "Zielseite — hierhin führt alles",
        "hinweise": [
            "Ausweisverifizierung nötig, auch für jede mitwirkende Person.",
            "Preis lieber niedrig starten und über Bundles arbeiten.",
        ],
    },
    "Fansly": {
        "bio_limit": 1000,
        "inhalt": "Paid-Plattform, expliziter Inhalt",
        "link": "Zweitplattform",
        "hinweise": [
            "Streut das Risiko einer Kontosperre — nicht alles auf eine Plattform.",
        ],
    },
    "Pornhub Model Program": {
        "bio_limit": 500,
        "inhalt": "NSFW, Reichweite plus Zusatzerlös",
        "link": "Verweis auf die Paid-Plattform erlaubt",
        "hinweise": [
            "Verifizierung aller Mitwirkenden verpflichtend.",
            "Kostenlose Clips als Trichter, nicht als Haupterlös.",
        ],
    },
}

# --- Stufenplan -----------------------------------------------------------

AUFBAU_PHASEN = (
    ("Fundament", "Woche 1–2", (
        "Künstlernamen festlegen und auf allen Zielplattformen sichern",
        "Projekt-Mailadresse und eigene Telefonnummer einrichten",
        "Steckbrief ausfüllen: Nische, Zielgruppe, Tonalität, Tabus",
        "Wasserzeichen und Farbwelt festlegen",
        "Profilbild erstellen, das nirgendwo sonst existiert",
    )),
    ("Kanäle", "Woche 2–3", (
        "Paid-Plattform anlegen und verifizieren lassen",
        "X/Twitter anlegen, Konto als sensibel markieren",
        "Bio-Link-Seite aufsetzen und überall eintragen",
        "Zwei-Faktor-Authentisierung auf jedem Konto aktivieren",
        "Reddit-Konto anlegen und passende Subs sammeln (noch nicht posten)",
    )),
    ("Vorrat", "Woche 3–4", (
        "Erster Solo-Dreh: Technik und Workflow testen",
        "Material für mindestens zwei Wochen im Voraus schneiden",
        "Content-Kalender für sechs Wochen füllen",
        "Reddit-Karma durch Kommentare aufbauen",
    )),
    ("Start", "Woche 5–6", (
        "Veröffentlichung nach Plan beginnen — Rhythmus ist wichtiger als Menge",
        "Erste Anzeige zur Partnerinnen-Suche veröffentlichen",
        "In den gesammelten Subs zu posten beginnen",
        "Wöchentlich auswerten: Was hat Reichweite gebracht, was nicht",
    )),
)


# --- Steckbrief und Identität --------------------------------------------

def steckbrief(store: Store) -> dict:
    daten = store.laden()["projekt"].setdefault("steckbrief", {})
    return {schluessel: daten.get(schluessel, "") for schluessel, _, _ in STECKBRIEF_FELDER}


def steckbrief_setzen(store: Store, schluessel: str, wert: str) -> dict:
    gueltig = {s for s, _, _ in STECKBRIEF_FELDER}
    if schluessel not in gueltig:
        raise ValueError(f"Unbekanntes Steckbrief-Feld '{schluessel}'.")
    store.laden()["projekt"].setdefault("steckbrief", {})[schluessel] = str(wert or "").strip()
    return steckbrief(store)


def identitaet(store: Store) -> dict:
    daten = store.laden()["projekt"].setdefault("identitaet", {})
    return {schluessel: daten.get(schluessel, "") for schluessel, _, _ in IDENTITAET_FELDER}


def identitaet_setzen(store: Store, schluessel: str, wert: str) -> dict:
    gueltig = {s for s, _, _ in IDENTITAET_FELDER}
    if schluessel not in gueltig:
        raise ValueError(f"Unbekanntes Identitäts-Feld '{schluessel}'.")
    store.laden()["projekt"].setdefault("identitaet", {})[schluessel] = str(wert or "").strip()
    return identitaet(store)


# --- Namenskandidaten -----------------------------------------------------

PRUEF_STATUS = ("offen", "frei", "vergeben")


def name_vorschlagen(store: Store, name: str) -> dict:
    name = str(name or "").strip()
    if not name:
        raise ValueError("Bitte einen Namen angeben.")
    if any(k["name"].lower() == name.lower() for k in store.sammlung("namenskandidaten")):
        raise ValueError(f"'{name}' steht bereits auf der Liste.")
    zu_pruefen = [k.get("plattform", "") for k in store.sammlung("kanaele")] or list(PLATTFORM_REGELN)
    return store.anlegen(
        "namenskandidaten",
        {
            "name": name,
            "favorit": False,
            "geprueft": {plattform: "offen" for plattform in zu_pruefen},
            "notiz": "",
        },
    )


def name_pruefung_setzen(store: Store, kennung: str, plattform: str, status: str) -> dict:
    if status not in PRUEF_STATUS:
        raise ValueError(f"Status muss einer von {', '.join(PRUEF_STATUS)} sein.")
    kandidat = store.finden("namenskandidaten", kennung)
    kandidat.setdefault("geprueft", {})[plattform] = status
    return kandidat


def name_waehlen(store: Store, kennung: str) -> dict:
    """Macht einen Kandidaten zum Künstlernamen des Projekts."""
    kandidat = store.finden("namenskandidaten", kennung)
    vergeben = [p for p, s in (kandidat.get("geprueft") or {}).items() if s == "vergeben"]
    if vergeben:
        raise ValueError(
            f"'{kandidat['name']}' ist auf folgenden Plattformen vergeben: "
            + ", ".join(vergeben)
            + ". Ein Name, der nicht überall verfügbar ist, zerreißt die Marke."
        )
    for anderer in store.sammlung("namenskandidaten"):
        anderer["favorit"] = anderer["id"] == kennung
    projekt = store.laden()["projekt"]
    projekt["kuenstlername"] = kandidat["name"]
    projekt.setdefault("identitaet", {}).setdefault("wasserzeichen", kandidat["name"])
    return kandidat


def namensuebersicht(store: Store) -> list[dict]:
    zeilen = []
    for kandidat in store.sammlung("namenskandidaten"):
        geprueft = kandidat.get("geprueft") or {}
        zeilen.append(
            {
                **kandidat,
                "frei": sum(1 for s in geprueft.values() if s == "frei"),
                "vergeben": sum(1 for s in geprueft.values() if s == "vergeben"),
                "offen": sum(1 for s in geprueft.values() if s == "offen"),
                "waehlbar": all(s == "frei" for s in geprueft.values()) if geprueft else False,
            }
        )
    return sorted(zeilen, key=lambda k: (not k["favorit"], -k["frei"], k["name"]))


# --- Profiltexte ----------------------------------------------------------

def bio_vorschlag(store: Store, plattform: str) -> dict:
    """Baut einen Profiltext aus dem Steckbrief, passend zum Zeichenlimit."""
    regel = PLATTFORM_REGELN.get(plattform)
    if regel is None:
        raise ValueError(
            f"Für '{plattform}' sind keine Regeln hinterlegt. Möglich: "
            + ", ".join(PLATTFORM_REGELN)
        )
    projekt = store.laden()["projekt"]
    brief = steckbrief(store)
    name = projekt.get("kuenstlername") or "[Künstlername]"
    limit = regel["bio_limit"]
    sfw = "NUR SFW" in regel["inhalt"]

    bausteine = [name]
    if brief["nische"]:
        bausteine.append(brief["nische"])
    if brief["alleinstellung"] and not sfw:
        bausteine.append(brief["alleinstellung"])
    if brief["rhythmus"]:
        bausteine.append(brief["rhythmus"])
    if sfw:
        bausteine.append("Alles Weitere über den Link.")
    elif projekt.get("kontakt"):
        bausteine.append("Anfragen nur schriftlich.")

    text = " · ".join(b.strip().rstrip(".") for b in bausteine if b.strip())
    gekuerzt = text if len(text) <= limit else text[: limit - 1].rstrip(" ·") + "…"

    return {
        "plattform": plattform,
        "text": gekuerzt,
        "zeichen": len(gekuerzt),
        "limit": limit,
        "passt": len(gekuerzt) <= limit,
        "inhalt": regel["inhalt"],
        "link": regel["link"],
        "hinweise": regel["hinweise"],
        "vollstaendig": not any(
            not brief[feld] for feld in ("nische", "alleinstellung", "rhythmus")
        ),
    }


def alle_bios(store: Store) -> list[dict]:
    """Profiltexte für die Plattformen, die im Kanal-Register stehen."""
    plattformen = [
        k.get("plattform", "")
        for k in store.sammlung("kanaele")
        if k.get("plattform") in PLATTFORM_REGELN
    ]
    if not plattformen:
        plattformen = list(PLATTFORM_REGELN)
    gesehen: list[str] = []
    for plattform in plattformen:
        if plattform not in gesehen:
            gesehen.append(plattform)
    return [bio_vorschlag(store, plattform) for plattform in gesehen]


# --- Fortschritt ----------------------------------------------------------

def fortschritt(store: Store) -> dict:
    """Wie weit der Identitätsaufbau ist — Grundlage fürs Dashboard."""
    projekt = store.laden()["projekt"]
    brief = steckbrief(store)
    ident = identitaet(store)

    brief_gefuellt = sum(1 for wert in brief.values() if wert)
    ident_gefuellt = sum(1 for wert in ident.values() if wert)
    hat_namen = bool(projekt.get("kuenstlername"))

    offen: list[str] = []
    if not hat_namen:
        offen.append("Künstlername ist noch nicht festgelegt")
    for schluessel, label, _ in STECKBRIEF_FELDER:
        if not brief[schluessel]:
            offen.append(f"Steckbrief: {label} fehlt")
    for schluessel, label, _ in IDENTITAET_FELDER:
        if not ident[schluessel]:
            offen.append(f"Identität: {label} fehlt")

    gesamt = 1 + len(STECKBRIEF_FELDER) + len(IDENTITAET_FELDER)
    erledigt = int(hat_namen) + brief_gefuellt + ident_gefuellt
    return {
        "erledigt": erledigt,
        "gesamt": gesamt,
        "anteil": round(100 * erledigt / gesamt),
        "kuenstlername": projekt.get("kuenstlername", ""),
        "offen": offen,
    }


def felder() -> dict:
    """Feldbeschreibungen für die Oberfläche."""
    return {
        "steckbrief": [
            {"schluessel": s, "label": label, "erklaerung": erklaerung}
            for s, label, erklaerung in STECKBRIEF_FELDER
        ],
        "identitaet": [
            {"schluessel": s, "label": label, "erklaerung": erklaerung}
            for s, label, erklaerung in IDENTITAET_FELDER
        ],
        "phasen": [
            {"name": name, "zeitraum": zeitraum, "schritte": list(schritte)}
            for name, zeitraum, schritte in AUFBAU_PHASEN
        ],
        "plattformen": list(PLATTFORM_REGELN),
    }
