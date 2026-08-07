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

**Gesichtszeigung:** [ ] mit Gesicht   [ ] ohne Gesicht / unkenntlich
**Wasserzeichen:** Das Material wird durchgängig mit dem Wasserzeichen
"{kuenstlername}" versehen.

## 4. Laufzeit und Exklusivität

Die Rechteeinräumung gilt ab Unterzeichnung für ____ Monate / unbefristet.
Exklusivität: [ ] ja   [ ] nein   Umfang: ______________________

## 5. Vergütung

[ ] Festgage in Höhe von ________ € , zahlbar bis zum ______________
[ ] Umsatzbeteiligung in Höhe von ____ % , abgerechnet ______________
[ ] Kombination: ______________________

Die Vergütung ist unabhängig davon geschuldet, ob und wie erfolgreich das
Material veröffentlicht wird.

## 6. Widerruf

Das Model kann die Einwilligung innerhalb von ____ Tagen nach dem Dreh ohne
Angabe von Gründen in Textform widerrufen. Nach einem Widerruf wird das
Material innerhalb von {widerruf_frist} Tagen von allen Plattformen entfernt,
nicht weiter verwertet und auf Verlangen gelöscht; die Löschung wird
schriftlich bestätigt. Bereits ausgezahlte Vergütung bleibt unberührt.

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

**Wie der Ablauf aussieht — ohne Ausnahme:**

1. Schriftlicher Kontakt, in Ruhe. Kein Druck, keine Fristen von meiner Seite.
2. Video-Call oder Treffen an einem öffentlichen Ort zum Kennenlernen.
3. Ausweisprüfung (18+) auf beiden Seiten vor jedem persönlichen Treffen.
4. Model-Release wird vorab zugeschickt, in Ruhe gelesen und unterschrieben —
   erst danach wird ein Termin vereinbart.
5. Gegenseitiger Austausch aktueller STI-Nachweise.
6. Erst dann der Dreh.

**Was ich zusage:**

- Vergütung: {verguetung}
- Zahlung zum vereinbarten Termin, unabhängig vom Erfolg der Veröffentlichung.
- Feste Grenzen werden vorher schriftlich festgehalten und eingehalten.
- Jederzeitiges Abbrechen am Set, ohne Diskussion und ohne Rückforderung.
- Widerrufsrecht nach dem Dreh, Frist steht im Vertrag.
- Veröffentlichung ausschließlich auf den vereinbarten Plattformen.
- Auf Wunsch ohne Gesicht.

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

Was du wissen solltest:

- Was gedreht wird und was nicht, legen wir vorher gemeinsam schriftlich fest.
- Deine Grenzen stehen im Vertrag und gelten am Set ohne Diskussion.
- Du kannst jederzeit abbrechen. Auch mittendrin, auch ohne Begründung.
- Nach dem Dreh hast du eine Widerrufsfrist, in der du alles zurückziehen
  kannst.
- Veröffentlicht wird nur auf den Plattformen, die im Vertrag stehen.
- Vergütung: {verguetung}

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


VORLAGEN = {
    "model-release": ("Model-Release / Einwilligung", MODEL_RELEASE),
    "anzeige": ("Anzeige zur Partnerinnen-Suche", ANZEIGE),
    "erstkontakt": ("Antwort auf eine Bewerbung", ERSTKONTAKT),
    "drehtag": ("Checkliste Drehtag", DREHTAG),
}


def namen() -> list[dict]:
    return [{"schluessel": k, "titel": t} for k, (t, _) in VORLAGEN.items()]


def rendern(store: Store, schluessel: str, **zusatz) -> str:
    """Füllt eine Vorlage mit den Projektdaten."""
    if schluessel not in VORLAGEN:
        raise ValueError(
            f"Unbekannte Vorlage '{schluessel}'. Möglich: {', '.join(VORLAGEN)}"
        )
    from creatordock.partnerinnen import WIDERRUF_FRIST_TAGE

    projekt = store.laden()["projekt"]
    kanaele = [
        k.get("plattform", "")
        for k in store.sammlung("kanaele")
        if k.get("zweck") in ("Paid-Plattform", "NSFW-Reichweite")
    ]
    werte = {
        "kuenstlername": projekt.get("kuenstlername") or "[Künstlername eintragen]",
        "plattformen": ", ".join(kanaele) or "OnlyFans, Pornhub",
        "widerruf_frist": WIDERRUF_FRIST_TAGE,
        "verguetung": "nach Absprache — Festgage oder Umsatzbeteiligung",
        "kontakt": projekt.get("kontakt") or "[Projekt-Mailadresse eintragen]",
        "rechtshinweis": f"> {RECHTSHINWEIS}",
        "datum": date.today().isoformat(),
    }
    werte.update({k: v for k, v in zusatz.items() if v})
    return VORLAGEN[schluessel][1].format(**werte)
