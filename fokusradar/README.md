# FokusRadar

Ein Aktivitäts-Monitor für den eigenen Rechner: Er erfasst im Hintergrund, **welches Programm gerade aktiv ist** und **wie viel wirklich gearbeitet wird**, speichert das ausschließlich lokal — und leitet daraus später konkrete Verbesserungsvorschläge zu Fokus und Bedienung ab.

> **Stand: Phase 5 von 6.** Erfassung, Kategorisierung, lokale Auswertung, Dashboard, Ausschlussliste, Screenshots mit lokaler OCR, verschlüsselte Datenbank, die Cloud-Analyse über die Claude-API und der Android-Begleiter stehen. Offen ist nur noch die optionale Phase 6 (siehe [Fahrplan](#fahrplan)).

## Was erfasst wird — und was nicht

| Wird erfasst | Wird **nicht** erfasst |
|---|---|
| Prozessname des aktiven Fensters (`code.exe`) | Tastatureingaben, Passwörter, Zwischenablage |
| Fenstertitel (abschaltbar) | alles, was auf der **Ausschlussliste** steht |
| Zeitpunkt und Dauer jeder Fensternutzung | irgendetwas, das das Gerät verlässt |
| Sekunden seit der letzten Eingabe (Idle-Zeit) | *welche* Taste gedrückt wurde |
| Anzahl der Eingaben pro Messpunkt (optional) | Bildschirminhalt, solange Screenshots aus sind (Vorgabe) |
| Screenshot-Text, wenn eingeschaltet (Bild wird danach gelöscht) | — |
| App-Nutzung des Handys in Sekunden, wenn der Begleiter eingerichtet ist | Inhalte, Benachrichtigungen oder Bildschirm des Handys |

Alle Daten liegen in **einer lokalen SQLite-Datei**, auf Wunsch mit SQLCipher verschlüsselt. Ohne `[cloud] aktiv = true` gibt es keinerlei Netzwerkzugriff — keine Telemetrie, keine Ausnahmen. Das Dashboard ist ein Server auf `localhost`, der nur die eigene Datenbank liest.

Ist die Cloud-Analyse eingeschaltet, geht **ausschließlich die verdichtete Tages- bzw. Wochenzusammenfassung** an die Claude-API: Zahlen und Prozessnamen, keine Fenstertitel, keine Screenshots, keine Rohdaten. Was genau, zeigt [`fokusradar cloud --zeigen`](#cloud-analyse-über-die-claude-api) — vor dem ersten Aufruf.

Drei Sperren greifen **vor** dem Speichern: die Ausschlussliste, die Smart Pause bei Videocalls und die Pausenerkennung. Was dort hängen bleibt, landet gar nicht erst in der Datenbank.

## Installation

Python 3.11 oder neuer genügt; für die Erfassung selbst sind **keine Zusatzpakete** nötig.

```bash
cd fokusradar
pip install -e .
```

Ohne Installation geht es auch direkt aus dem Ordner heraus: `python -m fokusradar ...`

Optional:

```bash
pip install -e ".[dashboard]"     # Weboberfläche (FastAPI, uvicorn, Jinja2)
pip install -e ".[screenshots]"   # Screenshots und OCR (mss, pytesseract)
pip install -e ".[krypto]"        # verschlüsselte Datenbank (SQLCipher)
pip install -e ".[cloud]"         # Vorschläge über die Claude-API (anthropic)
pip install -e ".[input]"         # zählt zusätzlich die Eingabe-Frequenz (pynput)
pip install -e ".[dev]"           # Tests
```

Für die Texterkennung muss zusätzlich **Tesseract** selbst installiert sein ([Windows-Installer](https://github.com/UB-Mannheim/tesseract/wiki), unter Linux `apt install tesseract-ocr tesseract-ocr-deu`).

Einzige Pflichtabhängigkeit ist `PyYAML` — daraus liest FokusRadar die Kategorien (eingebaute Regeln wie eigene `categories.yaml`). Die Erfassung selbst braucht weiterhin nichts weiter.

## Schnellstart

```bash
# 1. Zustand prüfen: Welche Backends laufen? Wo liegt die Datenbank?
fokusradar status

# 2. Erfassung starten (läuft im Vordergrund, Beenden mit Strg+C)
fokusradar track

# ... oder erst einmal fünf Minuten zum Ausprobieren, mit Ausgabe jedes Wechsels
fokusradar track --dauer 300 -v

# 3. Rohdaten ansehen
fokusradar log                      # letzte Fensternutzungen
fokusradar zeiten --tag heute       # Zeit je Programm
fokusradar aktivitaet               # Idle-Zeit und Eingabe-Frequenz

# 4. Auswerten: Fokus, Ablenkung, Vorschläge
fokusradar auswerten                # heute
fokusradar auswerten --tag gestern --woche

# 5. Dashboard im Browser (braucht das Extra [dashboard])
fokusradar dashboard --browser

# 6. Datenschutz: Ausschlussliste pflegen und Datenbank verschlüsseln
fokusradar ausschluss liste
fokusradar ausschluss hinzufuegen --prozess "keepass*.exe"
fokusradar verschluesseln

# 7. Cloud-Analyse: erst ansehen, was rausginge — dann fragen
fokusradar cloud --zeigen
fokusradar cloud
fokusradar kosten

# 8. Handy anbinden (Zahlen der App-Nutzung aus dem Heimnetz)
fokusradar android --token-neu
fokusradar android
```

Tagesangaben verstehen `heute`, `gestern`, `-3` (vor drei Tagen) und `2026-08-13`.

Beispielausgabe von `fokusradar auswerten`:

```
Auswertung für 2026-08-13
  Erfasste Zeit    3h 05m
  Fokuszeit        2h 20m (76 %)
  Ablenkung        39m 24s (21 %)
  Fensterwechsel   10 (3 pro Stunde)
  Längster Block   34m 14s

Kategorien
  + entwicklung               2h 20m  75.9%  ███████████████████
  − ablenkung                39m 24s  21.3%  █████
    kommunikation             5m 10s   2.8%  █

Fokus-Sessions
  08:45–09:09    24m 48s  code.exe
  10:20–10:50    29m 33s  code.exe, 1 Unterbrechung
  11:21–11:55    34m 14s  code.exe

Top-Ablenkungen
  steam.exe                30m 01s (1 Aufruf)

Vorschläge
  • 21 % der erfassten Zeit (39m 24s) gingen an Ablenkungen. Größter Posten:
    steam.exe (30m 01s). Ein fester Zeitpunkt dafür — statt zwischendurch —
    spart den Wiedereinstieg.
```

## Kategorien und Regeln

Welche Anwendung als Arbeit, als Ablenkung oder als neutral zählt, steht in `categories.yaml` (Vorgabe: neben der Konfigurationsdatei, Vorlage in [`config/categories.yaml`](config/categories.yaml)). Fehlt die Datei, greifen die eingebauten Regeln — nachsehen und ausprobieren lässt sich beides:

```bash
fokusradar kategorien                                     # geltende Regeln anzeigen
fokusradar kategorien --test firefox.exe --titel "… – YouTube"
```

Jede Kategorie legt über `zaehlt_als` fest, wie sie in die Auswertung eingeht:

| `zaehlt_als` | Bedeutung |
|---|---|
| `fokus` | zählt als konzentrierte Arbeit und bildet die Fokus-Sessions |
| `ablenkung` | zählt als Ablenkung (Ablenkungsanteil, Top-Ablenkungen) |
| `neutral` | wird nur gezählt, aber weder als Fokus noch als Ablenkung gewertet |

```yaml
kategorien:
  - name: entwicklung
    zaehlt_als: fokus
    prozesse: [code.exe, "pycharm*.exe"]
    titel: [stack overflow, github.com]
```

Geprüft wird **erst über alle Titel-Muster** (Teiltreffer, `*`/`?` erlaubt), **dann über die Prozess-Muster**; die erste Übereinstimmung gewinnt. Dadurch landet derselbe Browser je nach Inhalt in verschiedenen Kategorien: „… – YouTube" in `ablenkung`, „… – Stack Overflow" in `entwicklung`. Groß-/Kleinschreibung spielt nirgends eine Rolle.

Änderungen an den Regeln wirken **rückwirkend**: `auswerten` und das Dashboard bestimmen die Kategorien der betrachteten Tage jedes Mal neu.

## Auswertung: was gerechnet wird

* **Fokus-Session** — ein zusammenhängender Block in `fokus`-Kategorien. Kurze Abstecher (Vorgabe: bis 60 Sekunden, Pausen eingerechnet) unterbrechen den Block nicht, ihre Zeit zählt aber auch nicht als Fokuszeit. Ab 10 Minuten am Stück gilt der Block als Session; beide Werte sind einstellbar.
* **Wechsel pro Stunde** — Maß für Zerfaserung: jede Fensternutzung ist ein Wechsel.
* **Ablenkungsanteil** — Zeit in `ablenkung`-Kategorien im Verhältnis zur erfassten Zeit.
* **Vorschläge** — höchstens drei, regelbasiert aus genau diesen Kennzahlen, nach Dringlichkeit sortiert (viele Wechsel, hoher Ablenkungsanteil, kein langer Block, häufige Kurzbesuche in derselben App). Sie landen mit `source = 'local'` in der Tabelle `suggestions`; ab Phase 4 kommen zusätzlich Vorschläge aus der Claude-API dazu. Ein im Dashboard weggeklickter Vorschlag kommt bei der nächsten Auswertung nicht zurück.

Tage unter 15 Minuten erfasster Zeit bekommen keine Vorschläge — dafür ist die Datenlage zu dünn.

## Dashboard

```bash
fokusradar dashboard              # http://127.0.0.1:8760/
fokusradar dashboard --browser    # und Browser gleich öffnen
```

Drei Ansichten: **Tag** (Kennzahlen, Tagesverlauf als Zeitstrahl, Vorschläge, Kategorien, Fokus-Sessions, Programme), **Woche** (sieben Tage im Vergleich) und **Ausschluss** (Liste pflegen, siehe unten). Dazu `GET /api/tag/<datum>` als JSON — genau die verdichtete Form, die ab Phase 4 an die Claude-API geht.

Die Seite lädt keine externen Skripte, Schriften oder Bilder und funktioniert offline. Sie hört auf `127.0.0.1`, ist also nicht aus dem Netzwerk erreichbar; `--host` ändert das bewusst nur auf ausdrücklichen Wunsch.

## Ausschlussliste — was nie erfasst wird

Passt das aktive Fenster auf ein Muster der Liste, speichert FokusRadar **nichts**: keinen Prozessnamen, keinen Titel, keinen Screenshot. Die Zeit fehlt dann bewusst in der Auswertung — genau dafür ist die Liste da.

```bash
fokusradar ausschluss liste
fokusradar ausschluss hinzufuegen --prozess "keepass*.exe"
fokusradar ausschluss hinzufuegen --titel "online-banking"
fokusradar ausschluss pruefen firefox.exe --titel "Sparkasse Online-Banking"
fokusradar ausschluss entfernen 7
```

Im Dashboard geht dasselbe unter **Ausschluss** per Formular. Prozess-Muster erlauben `*` und `?`, Titel-Muster sind Teiltreffer; Groß-/Kleinschreibung spielt keine Rolle.

Maßgeblich ist die Liste in der Datenbank. Die Datei [`config/exclusions.yaml`](config/exclusions.yaml) ist nur die **Startvorlage**: Sie wird einmalig übernommen, solange die Liste leer ist — eine gepflegte Liste überschreibt FokusRadar nie. Vorbelegt sind die üblichen Verdächtigen (Passwort-Manager, Banking, TAN-Eingabe).

### Smart Pause bei Videocalls

Solange ein Programm aus `pause_prozesse` im Vordergrund ist (Vorgabe: Teams, Zoom, Webex, Skype), pausiert die Erfassung komplett — kein Fenstereintrag, kein Screenshot. `fokusradar track -v` schreibt beim Umschalten „Erfassung ausgesetzt" bzw. „Erfassung läuft wieder" ins Terminal.

## Screenshots und lokale Texterkennung

**Standardmäßig aus.** Eingeschaltet wird das über `[screenshots] aktiv = true`. Dann nimmt FokusRadar alle paar Minuten (Vorgabe: 10) ein Bild auf, erkennt den Text lokal mit Tesseract, speichert **nur den Text** und löscht das Bild wieder:

```bash
fokusradar screenshots            # Zeitpunkte und Textanfänge
fokusradar screenshots --text     # den erkannten Text vollständig
```

| Einstellung | Vorgabe | Bedeutung |
|---|---|---|
| `aktiv` | `false` | Schalter für die ganze Funktion |
| `intervall_sekunden` | 600 | Abstand zwischen zwei Aufnahmen |
| `ocr` | `true` | lokale Texterkennung (ohne sie bleibt nur das Bild) |
| `ocr_sprachen` | `"deu+eng"` | Sprachen für Tesseract |
| `bild_loeschen` | `true` | Bild nach der Erkennung löschen — empfohlen |
| `verzeichnis` | leer | Ablage der Bilder; leer = neben der Datenbank |

Aufgenommen wird nur, wenn gerade auch erfasst wird: nicht bei Ausschluss, nicht bei Smart Pause, nicht während einer Pause und nicht, wenn kein erfassbares Fenster im Vordergrund ist. Ist `mss` oder Tesseract nicht installiert, sagen `status` und `track` das im Klartext und die Erfassung läuft ohne Screenshots weiter.

## Verschlüsselte Datenbank

Mit dem Extra `[krypto]` liegt die Datenbank als SQLCipher-Datei auf der Platte — ohne Schlüssel ist sie nicht lesbar, auch nicht mit einem SQLite-Betrachter.

```bash
pip install -e ".[krypto]"
fokusradar verschluesseln     # stellt eine vorhandene Datenbank um
```

Danach in der Konfiguration `[speicher] verschluesselt = true` setzen. Für eine **neue** Datenbank genügt dieser Schalter allein. Der Schlüssel steht in `schluessel.key` neben der Datenbank (Rechte 0600) oder in der Umgebungsvariablen `FOKUSRADAR_KEY`, die Vorrang hat.

`fokusradar verschluesseln` legt die Klartext-Fassung als `*.unverschluesselt` daneben; die bitte nach der Kontrolle löschen. Und ohne Umschweife: **Wer die Schlüsseldatei verliert, verliert die Daten.** Es gibt keine Hintertür.

## Cloud-Analyse über die Claude-API

**Standardmäßig aus.** Ohne `[cloud] aktiv = true` baut FokusRadar keine Netzwerkverbindung auf. Ist sie an, schickt es die verdichtete Zusammenfassung eines Tages an die Claude-API und bekommt zwei bis drei konkrete Vorschläge zurück — zu Fokus und zu effizienterer Bedienung einzelner Programme.

### Erst ansehen, dann senden

```bash
fokusradar cloud --zeigen          # zeigt die Nutzlast, sendet nichts
fokusradar cloud --zeigen --woche  # dasselbe für den Wochenrückblick
```

Das ist kein Beiwerk, sondern der empfohlene erste Schritt: Die Ausgabe ist **exakt** das, was das Gerät verlassen würde. Zusammengestellt wird sie an genau einer Stelle im Code — [`fokusradar/cloud/prompts.py`](fokusradar/cloud/prompts.py).

| Geht hinaus | Bleibt hier |
|---|---|
| Kennzahlen des Tages (Zeiten, Anteile, Wechsel pro Stunde) | Fenstertitel |
| Minuten je Kategorie | Screenshots |
| Top-Programme mit **Prozessnamen** und Aufrufzahl | die Datenbank, einzelne Fensterwechsel |
| Fokus-Sessions als Uhrzeit und Dauer | alles von der Ausschlussliste Erfasste |
| die lokalen Vorschläge als Kontext | OCR-Text — außer `ocr_mitsenden = true` |

### Einrichten

```bash
pip install -e ".[cloud]"
fokusradar config --anlegen        # legt auch eine .env-Vorlage an
```

Den Schlüssel (von [platform.claude.com](https://platform.claude.com/)) in die `.env` neben der Konfiguration eintragen oder als Umgebungsvariable setzen — die Umgebung hat Vorrang:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Dann `[cloud] aktiv = true` setzen. Die `.env` steht in `.gitignore` und wird mit Rechten 0600 angelegt; ein Schlüssel gehört weder ins Repository noch in die Datenbank.

### Aufrufen

```bash
fokusradar cloud                   # heute
fokusradar cloud --tag gestern
fokusradar cloud --woche           # Wochenrückblick
fokusradar cloud --erneut          # nochmal fragen, obwohl es schon Vorschläge gibt
```

Pro Tag wird nur einmal gefragt; die Vorschläge landen mit `source = 'cloud'` in der Datenbank und stehen im Dashboard neben den lokalen. Läuft die Erfassung durch, holt sie die Analyse ab `taeglich_ab` (Vorgabe 18:00) von selbst, plus einmal pro Woche den Rückblick am eingestellten Wochentag. Scheitert ein Aufruf, meldet der Tracker das und erfasst weiter — die Erfassung hängt nie an der Cloud.

### Modell und Aufwand

| Einstellung | Vorgabe | Bedeutung |
|---|---|---|
| `modell` | `claude-sonnet-5` | auch `claude-opus-5` (mehr Qualität) oder `claude-haiku-4-5` (günstiger) |
| `aufwand` | `medium` | `low`…`max`; steuert, wie gründlich das Modell nachdenkt |
| `max_tokens` | 2000 | Obergrenze der Antwortlänge |
| `taeglich_ab` | `"18:00"` | Uhrzeit für die automatische Analyse; leer = nur manuell |
| `woechentlich_am` | `"sonntag"` | Wochentag für den Rückblick; leer = keiner |
| `ocr_mitsenden` | `false` | OCR-Text mitschicken — bewusst aus |

Sonnet 5 als Vorgabe kommt aus dem Bauplan: gute Qualität für konkrete Workflow-Tipps bei vernachlässigbaren Kosten. Bei Haiku 4.5 lässt FokusRadar den Aufwand-Parameter automatisch weg, weil das Modell ihn nicht kennt.

### Kosten

```bash
fokusradar kosten
```

Zeigt jeden Aufruf mit Token-Verbrauch und geschätzten Kosten, die Summe und eine Hochrechnung auf den Monat. Die Preistabelle steht in [`fokusradar/cloud/costs.py`](fokusradar/cloud/costs.py) (Stand 14.08.2026):

| Modell | Eingabe | Ausgabe |
|---|---|---|
| Claude Haiku 4.5 | 1 $ / Mio. Token | 5 $ / Mio. Token |
| Claude Sonnet 5 | 2 $ / Mio. Token | 10 $ / Mio. Token |
| Claude Opus 5 | 5 $ / Mio. Token | 25 $ / Mio. Token |

Ein Tagesaufruf liegt bei etwa 1.500-3.000 Token hinein und einigen hundert hinaus — mit Sonnet 5 also im Bereich **weniger Cent pro Monat**.

Zwei Hinweise zu den Zahlen: Die 2 $/10 $ für Sonnet 5 sind ein **Einführungspreis bis 31.08.2026**, danach gelten 3 $/15 $ — der Bauplan rechnet noch mit dem Einführungspreis. Und die Beträge hier sind Schätzungen aus der Token-Zahl; maßgeblich ist die Abrechnung von Anthropic. Eigene Konditionen lassen sich über `preis_input`/`preis_output` hinterlegen.

## Android-Begleiter

Eine kleine App fürs Handy zählt, wie lange welche App im Vordergrund war, und schickt diese Zahlen im Heimnetz an das Dashboard. Damit steht die Bildschirmzeit des Handys in derselben Tagesansicht wie die des Rechners. Quelltext und Bauanleitung: [`android-companion/`](android-companion/README.md).

Was das Handy verlässt: **Paketname, App-Name, Sekunden, Aufrufe** — je App und Tag. Keine Inhalte, keine Benachrichtigungen, keine Bildschirmfotos. Und nur in Richtung des einen Rechners, dessen Adresse in der App steht.

### Einrichten

```bash
fokusradar android --token-neu     # Geheimnis erzeugen, landet in der config.toml
```

Danach `[android] aktiv = true` setzen und das Dashboard so starten, dass das Handy es erreicht:

```bash
fokusradar dashboard --host 0.0.0.0
```

`fokusradar android` zeigt Zustand, Endpunkt und die bekannten Geräte — und die Handy-Nutzung eines Tages:

```
Sync:     an
Token:    gesetzt (••••b7Qe)
Endpunkt: http://192.168.1.42:8760/api/android/nutzung

Geräte:
  Pixel-7              letzter Sync 14.08.2026 21:04   Daten bis 2026-08-14

Handy-Nutzung am 2026-08-14: 2h 13min
  Instagram                ablenkung           45min   24 Aufrufe
  Signal                   kommunikation       18min   31 Aufrufe
```

In der App auf dem Handy dieselbe Adresse und dasselbe Token eintragen, die Berechtigung „Zugriff auf Nutzungsdaten“ erteilen — fertig.

### Der Sync-Endpunkt

| | |
|---|---|
| `POST /api/android/nutzung` | nimmt die Zahlen entgegen |
| `GET /api/android/status` | Verbindungstest für die App |

Beide verlangen `Authorization: Bearer <token>`; verglichen wird in konstanter Zeit. **Ohne `[android] aktiv = true` gibt es die Endpunkte nicht** — das Dashboard antwortet mit 404, als wäre nie einer eingebaut worden. Ein falsches Token ergibt 401, unbrauchbare Daten 400.

Ein Sync schickt immer den vollen Stand der letzten Tage, keine Differenz; ein Tag wird beim Empfang komplett ersetzt. Zweimal senden verdoppelt also nichts, und ein paar Tage ohne WLAN holt der nächste Sync von allein nach.

Die Pakete laufen durch dieselben Regeln wie die Programme (`categories.yaml`): der Paketname steht an der Stelle des Prozesses, der App-Name an der Stelle des Fenstertitels. Gängige Pakete sind in den eingebauten Regeln schon einsortiert.

## Konfiguration

```bash
fokusradar config             # zeigt die geltenden Werte und ihre Herkunft
fokusradar config --anlegen   # legt eine Vorlage im Benutzerprofil an
```

Ohne Konfigurationsdatei gelten die Vorgabewerte — FokusRadar ist also sofort startklar. Die Vorlage liegt als [`config/fokusradar.example.toml`](config/fokusradar.example.toml) bei:

| Einstellung | Vorgabe | Bedeutung |
|---|---|---|
| `intervall_sekunden` | 3 | Abstand zwischen zwei Abfragen des aktiven Fensters |
| `idle_schwelle_sekunden` | 300 | Ab so viel Zeit ohne Eingabe gilt die Zeit als Pause |
| `aktivitaets_intervall_sekunden` | 60 | Takt der Aktivitäts-Messpunkte |
| `eingaben_zaehlen` | `"auto"` | Eingabe-*Anzahl* zählen, wenn `pynput` installiert ist |
| `fenstertitel_speichern` | `true` | `false` speichert nur Prozessnamen |
| `datenbank` | leer | leer = Standardpfad im Benutzerprofil |
| `fokus_mindestdauer_sekunden` | 600 | ab dieser Dauer gilt ein Block als Fokus-Session |
| `unterbrechung_toleranz_sekunden` | 60 | so lange darf ein Abstecher sein, ohne den Block zu teilen |
| `wechsel_schwelle_pro_stunde` | 40 | ab hier weist die Auswertung auf zu viele Wechsel hin |
| `ablenkung_schwelle_anteil` | 0.2 | ab diesem Anteil Ablenkungszeit gibt es einen Hinweis |
| `kategorien_datei` | leer | leer = `categories.yaml` neben der Konfiguration |
| `pause_prozesse` | Teams, Zoom, … | Smart Pause: Erfassung ruht, solange eines davon vorn ist |
| `verschluesselt` | `false` | Datenbank mit SQLCipher verschlüsseln |
| `schluessel_datei` | leer | leer = `schluessel.key` neben der Datenbank |
| `aktiv` (Screenshots) | `false` | Screenshots und OCR einschalten |
| `aktiv` (Cloud) | `false` | Cloud-Analyse einschalten — davor geht nichts hinaus |
| `modell` / `aufwand` | `claude-sonnet-5` / `medium` | Modell und Denk-Aufwand der Cloud-Analyse |
| `taeglich_ab` / `woechentlich_am` | `"18:00"` / `"sonntag"` | wann die Erfassung selbst fragt |
| `ocr_mitsenden` | `false` | OCR-Text an die Cloud mitsenden |
| `aktiv` (Android) | `false` | Sync-Endpunkt für das Handy einschalten |
| `token` (Android) | leer | gemeinsames Geheimnis, erzeugt von `fokusradar android --token-neu` |
| `host` / `port` | `127.0.0.1` / 8760 | Adresse des Dashboards |

Speicherorte (überschreibbar per `--config`/`--db` oder den Umgebungsvariablen `FOKUSRADAR_CONFIG`/`FOKUSRADAR_DB`):

| | Windows | Linux |
|---|---|---|
| Konfiguration | `%APPDATA%\FokusRadar\config.toml` | `~/.config/fokusradar/config.toml` |
| Regeldatei | `%APPDATA%\FokusRadar\categories.yaml` | `~/.config/fokusradar/categories.yaml` |
| Ausschluss-Vorlage | `%APPDATA%\FokusRadar\exclusions.yaml` | `~/.config/fokusradar/exclusions.yaml` |
| API-Schlüssel | `%APPDATA%\FokusRadar\.env` | `~/.config/fokusradar/.env` |
| Datenbank | `%LOCALAPPDATA%\FokusRadar\fokusradar.db` | `~/.local/share/fokusradar/fokusradar.db` |

## Unterstützte Systeme

| System | Fenster-Erfassung | Idle-Erkennung |
|---|---|---|
| **Windows** (Primärsystem) | Win32-API über `ctypes` — ohne Zusatzpakete | `GetLastInputInfo` |
| **Linux/X11** (Entwicklung, Tests) | `xdotool`, ersatzweise `xprop` | XScreenSaver, ersatzweise `xprintidle` |
| Wayland, macOS | noch nicht | noch nicht |

Fehlt ein Backend, läuft FokusRadar trotzdem: `status` und `track` nennen den Grund im Klartext, die übrigen Messwerte werden weiter geschrieben.

> Abweichung vom Bauplan: Statt `pywin32` nutzt die Windows-Erfassung direkt `ctypes`. Das erspart auf dem Zielsystem jede Installation und deckt alles ab, was Phase 1 braucht. `pywin32` bleibt als Extra `[windows]` für spätere Phasen vorgesehen.

## Aufbau

```
fokusradar/
├── fokusradar/
│   ├── agent.py            # Erfassungsschleife (Tracker)
│   ├── cli.py              # Kommandozeile
│   ├── config.py           # Konfiguration (TOML) und Standardpfade
│   ├── timeutil.py         # Zeitzonen, Tagesgrenzen, Formatierung
│   ├── capture/            # aktives Fenster, Idle-Zeit, Eingaben, Screenshots
│   ├── processing/         # Kategorien, Ausschlussliste, Fokus-/Ablenkungsanalyse
│   ├── storage/            # SQLite-Schema, Abfragen, Verschlüsselung
│   ├── cloud/              # Claude-API: Nutzlast, Aufruf, Kosten
│   ├── android/            # Gegenstelle für den Sync des Handys
│   └── dashboard/          # FastAPI-App + Jinja2-Templates
├── android-companion/      # die App fürs Handy (Kotlin, Gradle)
├── config/                 # Vorlagen: config, categories.yaml, exclusions.yaml
└── tests/
```

Die Erfassung steckt hinter zwei schmalen Schnittstellen (`WindowBackend`, `IdleBackend`), und die Schleife lässt sich Schritt für Schritt über `Tracker.tick(now)` ausführen. Deshalb laufen die Tests auf jedem System — ohne Bildschirm, ohne echte Uhr.

### Datenmodell

Das Schema folgt Abschnitt 6 des Bauplans und ist vollständig in Gebrauch: `window_events` und `activity_level` von der Erfassung, `daily_summaries` und `suggestions` von der Auswertung, `screenshots_meta` von der OCR-Kette und `exclusion_list` von der Ausschlussliste. Dazu kommen zwei Tabellen, die der Bauplan nicht ausdrücklich nennt: `api_usage` (Phase 4) — ohne sie ließe sich das geforderte Kosten-Tracking nicht führen — und `android_usage` (Phase 5) für die Zahlen des Handys, eine Zeile je Gerät, Tag und Paket.

Eine Ergänzung gibt es bei `window_events`: die Spalten `ended_at` und `duration_seconds`. FokusRadar schreibt **eine Zeile je zusammenhängender Fensternutzung** statt einer Zeile alle drei Sekunden. Das spart rund 99 % der Zeilen, macht die Fokus-Sessions aus Phase 2 zu einer einfachen Abfrage — und weil das Ende laufend fortgeschrieben wird, kostet ein Absturz höchstens ein Erfassungsintervall.

Zeitstempel stehen als ISO-8601 in UTC in der Datenbank und werden für Anzeige und Tagesgruppierung in die lokale Zeit umgerechnet. Damit stimmen Auswertungen auch über den Sommerzeit-Wechsel hinweg.

### Umgang mit Pausen

Meldet das System mehr als `idle_schwelle_sekunden` ohne Eingabe, wird die laufende Fensternutzung **rückwirkend auf den Zeitpunkt der letzten Eingabe** beendet. Eine Mittagspause landet so nicht als „drei Stunden konzentriert im Editor" in der Statistik.

## Tests

```bash
python -m pytest -q
```

## Fahrplan

- [x] **Phase 1 — Basis-Tracking:** aktives Fenster, Idle-Erkennung, SQLite, CLI für die Rohdaten
- [x] **Phase 2 — Kategorisierung & lokale Analyse:** `categories.yaml`, Ablenkungs-/Fokus-Erkennung, Tageszusammenfassung, erstes Dashboard
- [x] **Phase 3 — Screenshots & OCR:** periodische Screenshots, lokale OCR, Ausschlussliste, Smart Pause, DB-Verschlüsselung
- [x] **Phase 4 — Cloud-Hybrid:** Claude-API-Anbindung für die Vorschläge, Prompt-Vorlagen, Kosten-Tracking
- [x] **Phase 5 — Android-Begleiter:** App-Nutzungsstatistik via `UsageStatsManager`, Sync ins Heimnetz
- [ ] **Phase 6 — optional:** Android-Screen-Monitoring, Vision-Analyse einzelner Screenshots

## Hinweis

Gedacht für **eigene Geräte**. Auf einem Arbeitsrechner vorher klären, ob eine solche Erfassung erlaubt ist — und niemals ohne Wissen der Betroffenen auf fremden Geräten einsetzen.
