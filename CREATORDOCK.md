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

## Bereiche

| Bereich | Was drinsteckt |
|---------|----------------|
| **Übersicht** | Kennzahlen und die Warnliste: fehlende Freigaben, gesperrte Drehs, abgelaufene Nachweise, überfällige Fristen, drohende Umsatzgrenzen |
| **Partnerinnen** | Onboarding, die sieben Schritte, STI-Gültigkeit, Widerruf |
| **Drehs** | Produktionspipeline `geplant → gedreht → geschnitten → veröffentlicht` mit Freigabeprüfung |
| **Kalender** | Redaktionsplan aus festem Rhythmus (Standard: Teaser Mo/Mi/Fr auf X, Paid-Release sonntags) |
| **Finanzen** | EÜR, Journal mit laufendem Saldo, Monatsübersicht, Steuerrücklage, Kleinunternehmer-Monitor, Ausrüstungsbudget |
| **Kanäle** | Kanal-Register (Handle, Projekt-Mail, 2FA, Verifizierung) und OPSEC-Checkliste |
| **Fahrplan** | Aufgaben mit Fristen, überfällige stehen oben |
| **Vorlagen** | Model-Release, Anzeige, Antwort auf Bewerbungen, Drehtag-Checkliste |

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

creatordock partnerin neu --pseudonym Model_A --quelle "Anzeige"
creatordock partnerin liste
creatordock partnerin gate --id P1 --gate release
creatordock partnerin widerruf --id P1 --grund "..."

creatordock dreh neu --datum 2026-08-15 --titel "..." --partnerin P1 --plattform OnlyFans
creatordock dreh liste
creatordock dreh status --id D1 --wert gedreht

creatordock buchen 2026-08-20 "OnlyFans Payout" "Einnahme Plattform" --einnahme 340
creatordock finanzen --jahr 2026

creatordock kalender planen --start 2026-08-10 --wochen 6
creatordock aufgabe liste
creatordock kanaele

creatordock vorlage model-release --out release.md
creatordock bericht --out bericht.html
```

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
