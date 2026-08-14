# FokusRadar

Ein Aktivitäts-Monitor für den eigenen Rechner: Er erfasst im Hintergrund, **welches Programm gerade aktiv ist** und **wie viel wirklich gearbeitet wird**, speichert das ausschließlich lokal — und leitet daraus später konkrete Verbesserungsvorschläge zu Fokus und Bedienung ab.

> **Stand: Phase 2 von 6.** Erfassung, Kategorisierung, lokale Auswertung mit Vorschlägen und das Dashboard stehen. Screenshots/OCR, Cloud-Analyse und der Android-Begleiter folgen in den nächsten Phasen (siehe [Fahrplan](#fahrplan)).

## Was erfasst wird — und was nicht

| Wird erfasst | Wird **nicht** erfasst |
|---|---|
| Prozessname des aktiven Fensters (`code.exe`) | Tastatureingaben, Passwörter, Zwischenablage |
| Fenstertitel (abschaltbar) | Fensterinhalte, Screenshots (erst Phase 3, dann konfigurierbar) |
| Zeitpunkt und Dauer jeder Fensternutzung | irgendetwas, das das Gerät verlässt |
| Sekunden seit der letzten Eingabe (Idle-Zeit) | *welche* Taste gedrückt wurde |
| Anzahl der Eingaben pro Messpunkt (optional) | — |

Alle Daten liegen in **einer lokalen SQLite-Datei**. Bis einschließlich Phase 3 gibt es keinerlei Netzwerkzugriff — keine Cloud, keine Telemetrie. Das Dashboard ist ein Server auf `localhost`, der nur die eigene Datenbank liest.

## Installation

Python 3.11 oder neuer genügt; für die Erfassung selbst sind **keine Zusatzpakete** nötig.

```bash
cd fokusradar
pip install -e .
```

Ohne Installation geht es auch direkt aus dem Ordner heraus: `python -m fokusradar ...`

Optional:

```bash
pip install -e ".[dashboard]"   # Weboberfläche (FastAPI, uvicorn, Jinja2)
pip install -e ".[input]"       # zählt zusätzlich die Eingabe-Frequenz (pynput)
pip install -e ".[dev]"         # Tests
```

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

Zwei Ansichten: **Tag** (Kennzahlen, Tagesverlauf als Zeitstrahl, Vorschläge, Kategorien, Fokus-Sessions, Programme) und **Woche** (sieben Tage im Vergleich). Dazu `GET /api/tag/<datum>` als JSON — genau die verdichtete Form, die ab Phase 4 an die Claude-API geht.

Die Seite lädt keine externen Skripte, Schriften oder Bilder und funktioniert offline. Sie hört auf `127.0.0.1`, ist also nicht aus dem Netzwerk erreichbar; `--host` ändert das bewusst nur auf ausdrücklichen Wunsch.

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
| `host` / `port` | `127.0.0.1` / 8760 | Adresse des Dashboards |

Speicherorte (überschreibbar per `--config`/`--db` oder den Umgebungsvariablen `FOKUSRADAR_CONFIG`/`FOKUSRADAR_DB`):

| | Windows | Linux |
|---|---|---|
| Konfiguration | `%APPDATA%\FokusRadar\config.toml` | `~/.config/fokusradar/config.toml` |
| Regeldatei | `%APPDATA%\FokusRadar\categories.yaml` | `~/.config/fokusradar/categories.yaml` |
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
│   ├── capture/            # aktives Fenster, Idle-Zeit, Eingabe-Zählung
│   ├── processing/         # Kategorisierung, Fokus-/Ablenkungsanalyse
│   ├── storage/            # SQLite-Schema und Abfragen
│   └── dashboard/          # FastAPI-App + Jinja2-Templates
├── config/                 # Vorlagen: fokusradar.example.toml, categories.yaml
└── tests/
```

Die Erfassung steckt hinter zwei schmalen Schnittstellen (`WindowBackend`, `IdleBackend`), und die Schleife lässt sich Schritt für Schritt über `Tracker.tick(now)` ausführen. Deshalb laufen die Tests auf jedem System — ohne Bildschirm, ohne echte Uhr.

### Datenmodell

Das Schema folgt Abschnitt 6 des Bauplans; die Tabellen späterer Phasen (`screenshots_meta`, `exclusion_list`) werden bereits angelegt. `daily_summaries` und `suggestions` füllt seit Phase 2 die Auswertung.

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
- [ ] **Phase 3 — Screenshots & OCR:** periodische Screenshots, lokale OCR, Ausschlussliste, Smart Pause, DB-Verschlüsselung
- [ ] **Phase 4 — Cloud-Hybrid:** Claude-API-Anbindung für die Vorschläge, Prompt-Vorlagen, Kosten-Tracking
- [ ] **Phase 5 — Android-Begleiter:** App-Nutzungsstatistik via `UsageStatsManager`
- [ ] **Phase 6 — optional:** Android-Screen-Monitoring, Vision-Analyse einzelner Screenshots

## Hinweis

Gedacht für **eigene Geräte**. Auf einem Arbeitsrechner vorher klären, ob eine solche Erfassung erlaubt ist — und niemals ohne Wissen der Betroffenen auf fremden Geräten einsetzen.
