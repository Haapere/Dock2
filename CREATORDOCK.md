# CreatorDock

Lokale Projektzentrale für das Content-Creator-Projekt. Setzt das Konzept
(`Konzept_Content_Creator.docx`) und den Tracker (`Tracker_Content_Creator.xlsx`)
in ein laufendes Programm um: Partnerinnen-Onboarding mit Freigabelogik,
Drehplanung, Content-Kalender, Kanal-Register, Buchhaltung und Fahrplan.

Läuft komplett offline auf dem eigenen Rechner. Keine Cloud, kein Konto,
keine Fremdbibliotheken — nur die Python-Standardbibliothek.

## Starten

Doppelklick genügt:

| System  | Datei                          | Hinweis |
|---------|--------------------------------|---------|
| Windows | `start-creatordock-windows.bat` | Doppelklick |
| macOS   | `start-creatordock-mac.command` | beim ersten Mal ggf. Rechtsklick → „Öffnen" |
| Linux   | `start-creatordock-linux.sh`    | einmalig `chmod +x`, dann ausführen |

Wenn das Paket installiert ist (`pip install -e .`), geht es auch direkt:

```bash
creatordock            # Oberfläche starten (Standard)
creatordock status     # Lagebild im Terminal
```

Die Oberfläche lauscht ausschließlich auf `127.0.0.1` — anders als StrategyLab
gibt es hier **keinen** Handy-Modus. Die Daten sind zu sensibel, um sie ins
WLAN zu stellen.

## Wo die Daten liegen

Standard: `~/CreatorDock-Daten/daten.json` — bewusst **außerhalb** des
Projektordners, damit nichts versehentlich in Git landet. Anderer Ort:

```bash
creatordock --daten /pfad/zum/ordner status
export CREATORDOCK_DATEN=/pfad/zum/ordner    # oder dauerhaft
```

Vor jedem Schreiben entsteht eine Sicherung (`daten.json.bak`), geschrieben
wird atomar. Ordner und Datei bekommen enge Rechte (0700/0600).

### Was NICHT in die App gehört

Ausweiskopien, unterschriebene Model-Releases und STI-Nachweise. Die App
speichert nur **Pseudonyme, Bestätigungen und Daten** — plus ein Aktenzeichen,
das auf die verschlüsselte Ablage außerhalb verweist (VeraCrypt, BitLocker,
FileVault, LUKS). Wer Dokumente in einer JSON-Datei sammelt, hat im Fall eines
Geräteverlusts ein sehr viel größeres Problem als eine unvollständige Akte.

## Die Freigabelogik — der eigentliche Zweck

Sieben Pflicht-Schritte pro Partnerin, alle aus dem Konzept:

1. Schriftlicher Erstkontakt dokumentiert
2. Alter per Ausweis geprüft (18+)
3. Kennenlerngespräch geführt
4. Model-Release / Vertrag unterschrieben
5. STI-Test-Nachweise ausgetauscht
6. Vergütung und Zahlungstermin fixiert
7. Widerrufsfrist vereinbart

Erst wenn **alle sieben** abgehakt sind, gilt eine Partnerin als freigegeben.
Ein Dreh mit ihr lässt sich sonst nicht über „geplant" hinausschieben — die App
verweigert den Statuswechsel mit Begründung. Solo-Drehs ohne Partnerinnen
laufen ohne diese Prüfung.

Ein hinterlegtes Ablaufdatum des STI-Nachweises blockiert den Dreh ebenfalls,
sobald es überschritten ist.

### Widerruf

Ein erfasster Widerruf wirkt rückwirkend und automatisch:

* Die Partnerin verliert die Freigabe, weitere Schritte lassen sich nicht mehr
  abhaken.
* **Alle** Drehs mit ihr werden gesperrt und lassen sich nicht mehr
  weiterbearbeiten oder veröffentlichen.
* War bereits etwas veröffentlicht, entsteht automatisch eine Aufgabe mit
  hoher Priorität und sieben Tagen Frist: Material depublizieren und die
  Löschung schriftlich bestätigen.

Versehentlich erfasst? `Widerruf zurücknehmen` stellt den vorherigen Stand her.

## Das Angebot — und warum es sich selbst durchsetzt

Der Vertrag regelt, was rechtlich gilt. Das **Angebot** ist das, was eine
Partnerin überhaupt erst zusagen lässt: gesichtslos drehen, Sichtungsrecht vor
der Veröffentlichung, Begleitperson am Set, Auszahlung am Drehtag.

Es gibt zwei Ebenen:

* **Standardangebot** — was du jeder Partnerin zusagst, einmal konfiguriert.
* **Vereinbarung** — was eine einzelne Partnerin daraus gewählt hat. Sie
  überschreibt den Standard punktuell; Abweichungen werden ausgewiesen.

Der entscheidende Teil ist die Durchsetzung. Aus jeder Zusage, die das fertige
Material betrifft, wird eine **Auflage**:

| Vereinbart | Auflage vor der Veröffentlichung |
|------------|----------------------------------|
| Gesicht: ohne Gesicht | Gesicht kommt im gesamten Material nicht vor |
| Gesicht: unkenntlich gemacht | Gesicht ist durchgängig unkenntlich gemacht |
| Stimme: verzerrt | Stimme ist verzerrt |
| Tattoos abdecken | Erkennungsmerkmale sind abgedeckt oder retuschiert |
| Sichtungsrecht | Partnerin hat den fertigen Schnitt freigegeben |
| Wasserzeichen | Wasserzeichen ist gesetzt |
| Metadaten entfernen | GPS und Gerätekennung sind entfernt |

**Solange eine dieser Auflagen nicht bestätigt ist, lässt sich der Dreh nicht
auf „veröffentlicht" setzen.** Aus dem Versprechen wird eine Sperre. Bei
Solo-Drehs gelten nur die materialbezogenen Auflagen — Gesicht und
Sichtungsrecht ergeben ohne Partnerin keinen Sinn.

Das Angebot speist außerdem die Texte: Anzeige, Erstkontakt-Antwort,
Angebotsblatt und Model-Release werden daraus generiert. Mit
`--partnerin P1` steht im Release genau das, was ihr besprochen habt — nicht
ein Standardtext mit Ankreuzkästchen.

## Persona aufbauen

Der Bereich **Persona** macht aus „Künstlername festlegen" einen Ablauf:

* **Namenskandidaten** mit Verfügbarkeitsprüfung je Plattform. Ein Name lässt
  sich erst wählen, wenn er nirgends als *vergeben* markiert ist — ein Name,
  der nicht überall frei ist, zerreißt die Marke. Beim Wählen wird er
  automatisch als Wasserzeichen übernommen.
* **Steckbrief**: Nische, Zielgruppe, Tonalität, Alleinstellungsmerkmal,
  Tabus, versprochener Rhythmus.
* **Visuelle Identität**: Wasserzeichen, Farbwelt, Profilbild-Konzept,
  Bio-Link.
* **Profiltexte je Plattform**, aus dem Steckbrief erzeugt und auf das echte
  Zeichenlimit gekürzt (X 160, Instagram 150, TikTok 80, Reddit 200,
  Paid-Plattformen 1000). SFW-Kanäle bekommen bewusst keine expliziten
  Bausteine untergeschoben.
* **Plattform-Spielregeln**: was wo erlaubt ist und woran Konten typischerweise
  sterben — Instagram-Sperre wegen Direktlink, Reddit-Bann wegen Sub-Regeln,
  X-Shadowban ohne Sensibel-Markierung.
* **Stufenplan** über sechs Wochen: Fundament, Kanäle, Vorrat, Start.

Die App prüft **keine** Handles online und postet nirgends. Sie sagt dir, was
zu prüfen ist, und hält fest, was du herausgefunden hast.

## Bereiche

| Bereich | Was drinsteckt |
|---------|----------------|
| **Übersicht** | Kennzahlen und die Warnliste: fehlende Freigaben, offene Auflagen, gesperrte Drehs, abgelaufene Nachweise, überfällige Fristen, drohende Umsatzgrenzen |
| **Persona** | Künstlername, Steckbrief, visuelle Identität, Profiltexte, Stufenplan |
| **Angebot** | Was du zusagst — als Standard und je Partnerin, mit Durchsetzung |
| **Partnerinnen** | Onboarding, die sieben Schritte, STI-Gültigkeit, Widerruf |
| **Drehs** | Produktionspipeline `geplant → gedreht → geschnitten → veröffentlicht` mit Freigabeprüfung und Auflagen-Checkliste |
| **Kalender** | Redaktionsplan aus festem Rhythmus (Standard: Teaser Mo/Mi/Fr auf X, Paid-Release sonntags) |
| **Finanzen** | EÜR, Journal mit laufendem Saldo, Monatsübersicht, Steuerrücklage, Kleinunternehmer-Monitor, Ausrüstungsbudget |
| **Kanäle** | Kanal-Register (Handle, Projekt-Mail, 2FA, Verifizierung) und OPSEC-Checkliste |
| **Fahrplan** | Aufgaben mit Fristen, überfällige stehen oben |
| **Vorlagen** | Angebotsblatt, Model-Release, Anzeige, Antwort auf Bewerbungen, Drehtag-Checkliste — alle aus den echten Daten erzeugt |

## Kleinunternehmerregelung

Die App prüft **beide** Grenzen des § 19 UStG in der seit 2025 geltenden
Fassung — das Konzeptpapier nennt nur die erste:

* Vorjahresumsatz ≤ **25.000 €**
* laufender Umsatz ≤ **100.000 €**

Wird die obere Grenze im laufenden Jahr überschritten, endet die
Kleinunternehmer-Eigenschaft **sofort ab diesem Umsatz** — ab dann ist
Umsatzsteuer auszuweisen. Ab 80 % einer Grenze warnt die Übersicht.

Der Vorjahresumsatz wird unter *Einstellungen* eingetragen; im ersten Jahr
bleibt er 0.

Die Steuerrücklage (Standard 25 % vom Gewinn) ist ein Richtwert, kein
Steuersatz. Die App ersetzt keine Steuerberatung.

## Kommandozeile

```bash
creatordock init --kuenstlername "Name"        # Startdaten aus dem Konzept anlegen
creatordock status                             # Lagebild und offene Risiken

creatordock persona status                     # Aufbaustand und Stufenplan
creatordock persona name --name "NachtSchicht" # Namenskandidat aufnehmen
creatordock persona namen                      # Kandidaten mit Prüfstand
creatordock persona setzen --schluessel nische --wert "..."
creatordock persona bios                       # Profiltexte je Plattform

creatordock angebot zeigen                     # Standardangebot
creatordock angebot zeigen --partnerin P1      # ihre Vereinbarung
creatordock angebot setzen --schluessel gesicht --wert "ohne Gesicht"
creatordock angebot setzen --partnerin P1 --schluessel stimme --wert verzerrt
creatordock angebot blatt                      # Angebotsblatt als Text

creatordock partnerin neu --pseudonym Model_A --quelle "Anzeige"
creatordock partnerin liste
creatordock partnerin gate --id P1 --gate release
creatordock partnerin widerruf --id P1 --grund "..."

creatordock dreh neu --datum 2026-08-15 --titel "..." --partnerin P1 --plattform OnlyFans
creatordock dreh liste                         # zeigt offene Auflagen
creatordock dreh status --id D1 --wert gedreht

creatordock buchen 2026-08-20 "OnlyFans Payout" "Einnahme Plattform" --einnahme 340
creatordock finanzen --jahr 2026

creatordock kalender planen --start 2026-08-10 --wochen 6
creatordock aufgabe liste
creatordock kanaele

creatordock vorlage angebot                        # Angebotsblatt
creatordock vorlage model-release --partnerin P1 --out release.md
creatordock bericht --out bericht.html
```

Die Auflagen eines Drehs hakst du in der Oberfläche unter *Drehs* ab — sie
klappen dort auf, sobald der Dreh auf „geschnitten" steht.

Die Vetting-Schlüssel für `--gate`: `erstkontakt`, `alter_verifiziert`,
`kennenlernen`, `release`, `sti_nachweis`, `verguetung`, `widerrufsfrist`.

## Statusbericht

`creatordock bericht` erzeugt eine eigenständige HTML-Datei mit Kennzahlen,
Risiken, Vetting-Stand, Pipeline, Kalender, Finanzen und Fahrplan — zum
Ausdrucken oder zur Weitergabe an den Steuerberater. Aktenzeichen und
Dokumentverweise bleiben bewusst draußen.

## Tests

```bash
python -m pytest tests/test_creatordock.py -v
```

## Grenzen

* **Keine Rechtsberatung.** Der Model-Release ist ein Arbeitsentwurf aus der
  Checkliste des Konzepts. Vor der ersten Verwendung einmalig anwaltlich
  prüfen lassen — das kostet einmal Geld und erspart im Streitfall jede
  Diskussion.
* **Keine Steuerberatung.** Die EÜR ist eine Aufzeichnung, keine Erklärung.
* **Kein Versand, keine Automatisierung nach außen.** Die App verschickt
  nichts, kontaktiert niemanden und lädt nichts hoch. Die Anzeigen-Vorlage ist
  zum Veröffentlichen gedacht, nicht zum Anschreiben — so steht es auch im
  Konzept.
* **Verschlüsselung** übernimmt das Betriebssystem, nicht die App. Ohne
  aktivierte Festplattenverschlüsselung liegen die Daten im Klartext.
