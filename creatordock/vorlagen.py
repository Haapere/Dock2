"""Textvorlagen: Model-Release, Anzeige, Erstkontakt, Drehtag-Checkliste.

Alle Vorlagen sind **Arbeitsentwürfe auf Basis der Checkliste aus dem Konzept**,
keine anwaltlich geprüften Vertragstexte. Für die rechtssichere Fassung gehört
der Model-Release einmalig einem Anwalt vorgelegt — das kostet einmal Geld und
ersetzt danach jede Diskussion im Streitfall.

Platzhalter in geschweiften Klammern werden aus den Projektdaten gefüllt.
"""

from __future__ import annotations

from datetime import date

from creatordock.store import Store

RECHTSHINWEIS = (
    "Dieser Text ist ein Arbeitsentwurf aus einer Checkliste, kein geprüfter "
    "Vertrag und keine Rechtsberatung. Vor der ersten Verwendung einmalig "
    "anwaltlich prüfen lassen."
)


MODEL_RELEASE = """\
# Model-Release und Einwilligungserklärung

{rechtshinweis}

**Produzent (Künstlername):** {kuenstlername}
**Model (Künstlername):** ______________________
**Datum des Drehs:** ______________________
**Aktenzeichen der Ablage:** ______________________

## 1. Altersbestätigung und Identität

Beide Vertragsparteien haben sich vor Vertragsschluss gegenseitig durch ein
amtliches Lichtbilddokument ausgewiesen. Beide bestätigen, zum Zeitpunkt der
Aufnahme das 18. Lebensjahr vollendet zu haben. Kopien der Ausweise werden
ausschließlich zum Nachweis des Alters angefertigt, verschlüsselt gespeichert
und nicht weitergegeben.

## 2. Gegenstand der Aufnahmen

Aufgenommen werden: ______________________________________________
Ausdrücklich **nicht** Gegenstand der Aufnahmen sind: ____________________
Grenzen und Tabus des Models (verbindlich): ______________________________

## 3. Einwilligung und Verwertungsrechte

Das Model überträgt dem Produzenten das Recht, das Material auf folgenden
Plattformen zu veröffentlichen und zu verwerten:

- [ ] {plattformen}
- [ ] weitere: ______________________

Nicht eingeräumt werden Rechte zur Weitergabe an Dritte, zum Weiterverkauf des
Rohmaterials und zur Nutzung außerhalb der genannten Plattformen.

**Vereinbarte Anonymität:**

{anonymitaet}

**Wasserzeichen:** Das Material wird durchgängig mit dem Wasserzeichen
"{wasserzeichen}" versehen.

## 4. Laufzeit und Exklusivität

Die Rechteeinräumung gilt ab Unterzeichnung für {laufzeit}.
Exklusivität: {exklusivitaet}

## 5. Vergütung

Vergütungsmodell: **{verguetungsmodell}**

[ ] Festgage in Höhe von ________ € , zahlbar {zahlungszeitpunkt}
[ ] Umsatzbeteiligung in Höhe von ____ % , abgerechnet ______________

{verguetung_zusagen}

## 6. Widerruf

Das Model kann die Einwilligung {widerrufsfrist} nach dem Dreh ohne Angabe von
Gründen in Textform widerrufen. Nach einem Widerruf wird das Material
innerhalb von {widerruf_frist} Tagen von allen Plattformen entfernt, nicht
weiter verwertet und auf Verlangen gelöscht. Bereits ausgezahlte Vergütung
bleibt unberührt.

{nach_dreh_zusagen}

Darüber hinaus kann das Model einer weiteren Verwertung jederzeit mit Wirkung
für die Zukunft widersprechen.

## 7. Gesundheit

Beide Parteien haben sich gegenseitig aktuelle STI-Testnachweise vorgelegt.
Datum der Nachweise: Model ____________  Produzent ____________

## 8. Vertraulichkeit

Beide Parteien behandeln Klarnamen, Anschriften und alle weiteren
personenbezogenen Daten der jeweils anderen Partei vertraulich und geben sie
nicht an Dritte weiter. Diese Pflicht gilt über das Ende der Zusammenarbeit
hinaus.

## 9. Datenschutz

Verantwortlicher im Sinne der DSGVO ist der Produzent. Die Daten werden
ausschließlich zur Durchführung dieses Vertrags und zur Erfüllung
gesetzlicher Nachweispflichten verarbeitet und nach deren Ablauf gelöscht.
Dem Model stehen die Rechte auf Auskunft, Berichtigung und Löschung zu.

---

Ort, Datum: ______________________

Produzent: ______________________    Model: ______________________
"""


ANZEIGE = """\
# Anzeige: Suche Dreh-Partnerinnen ({kuenstlername})

**Wichtig:** Diese Anzeige wird **veröffentlicht** — sie wird nicht als
Direktnachricht verschickt. Keine unaufgeforderten Anschreiben an Dritte,
keine automatisierten Kontaktaufnahmen. Wer sich meldet, meldet sich selbst.

---

**Wer ich bin:** Amateur-Produktion, eigene Marke, Veröffentlichung auf
{plattformen}. Kleines, ruhiges Set — keine Crew, keine Zuschauer.

**Wen ich suche:** Volljährige Darstellerinnen (18+), die Erfahrung mitbringen
oder klar wissen, worauf sie sich einlassen.

**Was ich anbiete:**

{angebot}

**Wie der Ablauf aussieht — ohne Ausnahme:**

1. Schriftlicher Kontakt, in Ruhe. Kein Druck, keine Fristen von meiner Seite.
2. Video-Call oder Treffen an einem öffentlichen Ort zum Kennenlernen.
3. Ausweisprüfung (18+) auf beiden Seiten vor jedem persönlichen Treffen.
4. Model-Release wird vorab zugeschickt, in Ruhe gelesen und unterschrieben —
   erst danach wird ein Termin vereinbart.
5. Gegenseitiger Austausch aktueller STI-Nachweise.
6. Erst dann der Dreh.

**Kontakt:** {kontakt}

Nachrichten ohne Bezug zur Anzeige beantworte ich nicht.
"""


ERSTKONTAKT = """\
# Antwortvorlage auf eine Bewerbung

Hallo,

danke für deine Nachricht und dein Interesse.

Damit du weißt, worauf du dich einlässt, hier der komplette Ablauf, bevor
irgendetwas gedreht wird:

1. Wir telefonieren oder machen einen Video-Call — oder treffen uns an einem
   öffentlichen Ort. Du entscheidest, was dir lieber ist.
2. Wir weisen uns beide aus (18+). Das ist keine Formalie, sondern Bedingung.
3. Ich schicke dir vorher den Model-Release. Lies ihn in Ruhe, gern auch mit
   jemandem, dem du vertraust. Fragen dazu beantworte ich vollständig.
4. Wir tauschen aktuelle STI-Nachweise aus.
5. Erst wenn all das steht, machen wir einen Termin.

Das ist mein Angebot — jeder Punkt steht so auch im Vertrag:

{angebot}

Was davon dir wichtig ist und was nicht, besprechen wir. Einiges kannst du
frei wählen: ob dein Gesicht zu sehen ist, ob deine Stimme drauf ist, ob du
den fertigen Schnitt vorher freigibst.

Wenn das für dich passt, schlag mir gern zwei, drei Zeiten für ein Gespräch
vor. Wenn nicht, ist das auch völlig in Ordnung — dann alles Gute.

Viele Grüße
{kuenstlername}
"""


DREHTAG = """\
# Checkliste Drehtag — {kuenstlername}

## Vorher (am Abend davor)

- [ ] Freigabe in CreatorDock geprüft: alle Vetting-Schritte grün?
- [ ] Model-Release unterschrieben und abgelegt (Aktenzeichen notiert)
- [ ] STI-Nachweise aktuell und ausgetauscht
- [ ] Akkus geladen, Speicherkarten leer, SSD angeschlossen
- [ ] Licht aufgebaut und einmal getestet
- [ ] Drehort geprüft: keine Adressen, Post, Fotos, Dokumente im Bild
- [ ] Getränke, Handtücher, Hygieneartikel bereit

## Direkt vor dem Dreh

- [ ] Ausweis nochmals gesichtet, Alter bestätigt (18+)
- [ ] Grenzen und Tabus gemeinsam durchgegangen
- [ ] Abbruchwort vereinbart
- [ ] Kurze Einwilligung on camera aufgenommen (Datum nennen lassen)
- [ ] Gesichtsregel geklärt: mit oder ohne Gesicht?

## Nach dem Dreh

- [ ] Kurzes Nachgespräch, alles in Ordnung?
- [ ] Vergütung ausgezahlt oder Zahlungstermin bestätigt
- [ ] Widerrufsfrist noch einmal ausdrücklich genannt
- [ ] Rohmaterial auf die verschlüsselte SSD, Karte erst danach leeren
- [ ] Dreh in CreatorDock auf "gedreht" gesetzt

## Vor der Veröffentlichung

- [ ] Metadaten (GPS, Gerätekennung) entfernt
- [ ] Wasserzeichen gesetzt
- [ ] Bild auf erkennbare Orte und Merkmale durchgesehen
- [ ] Gesichtsregel des Releases eingehalten
- [ ] Widerrufsfrist abgelaufen oder Freigabe schriftlich bestätigt
"""


ANGEBOTSBLATT = """\
# Was ich zusage — {kuenstlername}

Dieses Blatt bekommst du vor dem Kennenlerngespräch, damit du in Ruhe
entscheiden kannst. Jeder Punkt hier steht später wortgleich im Vertrag.

{angebot}

## Was du selbst entscheidest

{wahlmoeglichkeiten}

## Was ich im Gegenzug erwarte

- Volljährigkeit, nachgewiesen durch ein amtliches Lichtbilddokument.
- Aktueller STI-Testnachweis, gegenseitig.
- Verlässlichkeit bei Terminen — sag lieber früh ab als gar nicht.
- Dass du sagst, wenn dir etwas nicht passt. Sofort, nicht hinterher.

## Woran du erkennst, dass etwas nicht stimmt

Falls du jemals bei mir oder bei jemand anderem Folgendes erlebst, brich ab:
Druck, den Vertrag „gleich hier“ zu unterschreiben; kein Ausweis auf der
Gegenseite; Nachverhandeln von Grenzen am Set; keine Vergütung vor oder am
Drehtag; Weigerung, eine Begleitperson zuzulassen.

---

{rechtshinweis}
"""


VORLAGEN = {
    "angebot": ("Angebotsblatt für Partnerinnen", ANGEBOTSBLATT),
    "model-release": ("Model-Release / Einwilligung", MODEL_RELEASE),
    "anzeige": ("Anzeige zur Partnerinnen-Suche", ANZEIGE),
    "erstkontakt": ("Antwort auf eine Bewerbung", ERSTKONTAKT),
    "drehtag": ("Checkliste Drehtag", DREHTAG),
}


def namen() -> list[dict]:
    return [{"schluessel": k, "titel": t} for k, (t, _) in VORLAGEN.items()]


def rendern(store: Store, schluessel: str, partner_id: str | None = None, **zusatz) -> str:
    """Füllt eine Vorlage mit den Projektdaten.

    Mit ``partner_id`` wird die individuelle Vereinbarung dieser Partnerin
    eingesetzt (gesichtslos, Sichtungsrecht, Vergütungsmodell) statt des
    Standardangebots — der Model-Release passt dann exakt zu dem, was ihr
    besprochen habt.
    """
    if schluessel not in VORLAGEN:
        raise ValueError(
            f"Unbekannte Vorlage '{schluessel}'. Möglich: {', '.join(VORLAGEN)}"
        )
    from creatordock import angebot as angebot_mod
    from creatordock import persona as persona_mod
    from creatordock.partnerinnen import WIDERRUF_FRIST_TAGE

    projekt = store.laden()["projekt"]
    konditionen = (
        angebot_mod.vereinbarung(store, partner_id)
        if partner_id
        else angebot_mod.standard(store)
    )
    kanaele = [
        k.get("plattform", "")
        for k in store.sammlung("kanaele")
        if k.get("zweck") in ("Paid-Plattform", "NSFW-Reichweite")
    ]
    kuenstlername = projekt.get("kuenstlername") or "[Künstlername eintragen]"
    wasserzeichen = persona_mod.identitaet(store).get("wasserzeichen") or kuenstlername

    werte = {
        "kuenstlername": kuenstlername,
        "wasserzeichen": wasserzeichen,
        "plattformen": ", ".join(kanaele) or "OnlyFans, Pornhub",
        "widerruf_frist": WIDERRUF_FRIST_TAGE,
        "kontakt": projekt.get("kontakt") or "[Projekt-Mailadresse eintragen]",
        "rechtshinweis": f"> {RECHTSHINWEIS}",
        "datum": date.today().isoformat(),
        "angebot": angebot_mod.angebotsblatt(store, partner_id),
        "wahlmoeglichkeiten": _wahlmoeglichkeiten(angebot_mod),
        "anonymitaet": _anonymitaet(konditionen),
        "laufzeit": str(konditionen.get("laufzeit", "24 Monate")),
        "exklusivitaet": "ja" if konditionen.get("exklusivitaet") else "nein",
        "verguetungsmodell": str(konditionen.get("modell", "Festgage")),
        "zahlungszeitpunkt": (
            "am Drehtag" if konditionen.get("zahlung_am_drehtag") else "bis zum ____________"
        ),
        "widerrufsfrist": _widerrufsfrist(konditionen),
        "verguetung_zusagen": _zusagen(
            konditionen,
            [
                ("erfolgsunabhaengig", "Die Vergütung ist unabhängig davon geschuldet, ob "
                                       "und wie erfolgreich das Material veröffentlicht wird."),
                ("reisekosten", "Reisekosten werden gegen Nachweis erstattet."),
            ],
        ),
        "nach_dreh_zusagen": _zusagen(
            konditionen,
            [
                ("sichtungsrecht", "Vor der Veröffentlichung erhält das Model den fertigen "
                                   "Schnitt zur Sichtung und kann einzelne Szenen streichen lassen."),
                ("loeschbestaetigung", "Nach einem Widerruf wird die vollständige Löschung "
                                       "schriftlich bestätigt."),
                ("kopie_material", "Das Model erhält auf Wunsch eine Kopie des eigenen Materials."),
            ],
        ),
    }
    werte.update({k: v for k, v in zusatz.items() if v})
    return VORLAGEN[schluessel][1].format(**werte)


def _anonymitaet(konditionen: dict) -> str:
    """Formuliert die Anonymitätszusagen als Vertragstext."""
    gesicht = konditionen.get("gesicht", "ohne Gesicht")
    zeilen = {
        "mit Gesicht": "Das Gesicht des Models darf im Material erkennbar sein.",
        "ohne Gesicht": "Das Gesicht des Models wird nicht aufgenommen. Aufnahmen, "
                        "auf denen es dennoch erkennbar ist, werden nicht verwertet.",
        "unkenntlich gemacht": "Das Gesicht des Models wird in der Nachbearbeitung "
                               "durchgängig unkenntlich gemacht.",
    }
    ergebnis = [f"- {zeilen.get(gesicht, zeilen['ohne Gesicht'])}"]

    stimme = konditionen.get("stimme", "unverändert")
    if stimme == "verzerrt":
        ergebnis.append("- Die Stimme des Models wird verzerrt.")
    elif stimme == "kein Ton":
        ergebnis.append("- Das Material wird ohne Tonspur veröffentlicht.")

    if konditionen.get("merkmale_abdecken"):
        ergebnis.append(
            "- Tattoos, Narben und vergleichbare Erkennungsmerkmale werden abgedeckt "
            "oder in der Nachbearbeitung entfernt."
        )
    if konditionen.get("kuenstlername_ihrs"):
        ergebnis.append(
            "- Das Model tritt ausschließlich unter seinem Künstlernamen auf. Der "
            "Klarname erscheint nirgends, auch nicht in Dateinamen oder Beschreibungen."
        )
    return "\n".join(ergebnis)


def _widerrufsfrist(konditionen: dict) -> str:
    wert = str(konditionen.get("widerruf_tage", "14 Tage"))
    return "jederzeit" if wert == "jederzeit" else f"innerhalb von {wert}"


def _zusagen(konditionen: dict, punkte: list[tuple[str, str]]) -> str:
    aktiv = [text for schluessel, text in punkte if konditionen.get(schluessel)]
    return "\n".join(aktiv) if aktiv else ""


def _wahlmoeglichkeiten(angebot_mod) -> str:
    """Listet auf, was die Partnerin selbst entscheidet."""
    zeilen = []
    for option in angebot_mod.KATALOG:
        if option.wer != "wahl":
            continue
        if option.typ == "auswahl":
            zeilen.append(f"- **{option.label}:** {' / '.join(option.optionen)}")
        else:
            zeilen.append(f"- **{option.label}:** ja oder nein")
    return "\n".join(zeilen)
