# FokusRadar

Ein Aktivitäts-Monitor für den eigenen Rechner: Er erfasst im Hintergrund, **welches Programm gerade aktiv ist** und **wie viel wirklich gearbeitet wird**, speichert das ausschließlich lokal — und leitet daraus später konkrete Verbesserungsvorschläge zu Fokus und Bedienung ab.

> **Stand: Phase 1 von 6.** Erfassung, Speicherung und Rohdaten-Anzeige stehen. Kategorisierung, Screenshots/OCR, Cloud-Analyse und der Android-Begleiter folgen in den nächsten Phasen (siehe [Fahrplan](#fahrplan)).

## Was erfasst wird — und was nicht

| Wird erfasst | Wird **nicht** erfasst |
|---|---|
| Prozessname des aktiven Fensters (`code.exe`) | Tastatureingaben, Passwörter, Zwischenablage |
| Fenstertitel (abschaltbar) | Fensterinhalte, Screenshots (erst Phase 3, dann konfigurierbar) |
| Zeitpunkt und Dauer jeder Fensternutzung | irgendetwas, das das Gerät verlässt |
| Sekunden seit der letzten Eingabe (Idle-Zeit) | *welche* Taste gedrückt wurde |
| Anzahl der Eingaben pro Messpunkt (optional) | — |

Alle Daten liegen in **einer lokalen SQLite-Datei**. In Phase 1 gibt es keinerlei Netzwerkzugriff — kein Server, keine Cloud, keine Telemetrie.

## Installation

Python 3.11 oder neuer genügt; für die Erfassung selbst sind **keine Zusatzpakete** nötig.

```bash
cd fokusradar
pip install -e .
```

Ohne Installation geht es auch direkt aus dem Ordner heraus: `python -m fokusradar ...`

Optional:

```bash
pip install -e ".[input]"   # zählt zusätzlich die Eingabe-Frequenz (pynput)
pip install -e ".[dev]"     # Tests
```

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
```

Beispielausgabe von `fokusradar zeiten`:

```
Zeit je Programm am 2026-08-13
Erfasste Zeit gesamt: 1h 47m

code.exe                    1h 25m  79.4%  ████████████████████████
firefox.exe                17m 02s  15.9%  █████
slack.exe                   5m 01s   4.7%  █
```

Tagesangaben verstehen `heute`, `gestern`, `-3` (vor drei Tagen) und `2026-08-13`.

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

Speicherorte (überschreibbar per `--config`/`--db` oder den Umgebungsvariablen `FOKUSRADAR_CONFIG`/`FOKUSRADAR_DB`):

| | Windows | Linux |
|---|---|---|
| Konfiguration | `%APPDATA%\FokusRadar\config.toml` | `~/.config/fokusradar/config.toml` |
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
│   └── storage/            # SQLite-Schema und Abfragen
├── config/fokusradar.example.toml
└── tests/
```

Die Erfassung steckt hinter zwei schmalen Schnittstellen (`WindowBackend`, `IdleBackend`), und die Schleife lässt sich Schritt für Schritt über `Tracker.tick(now)` ausführen. Deshalb laufen die Tests auf jedem System — ohne Bildschirm, ohne echte Uhr.

### Datenmodell

Das Schema folgt Abschnitt 6 des Bauplans; die Tabellen späterer Phasen (`screenshots_meta`, `daily_summaries`, `suggestions`, `exclusion_list`) werden bereits angelegt.

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
- [ ] **Phase 2 — Kategorisierung & lokale Analyse:** `categories.yaml`, Ablenkungs-/Fokus-Erkennung, Tageszusammenfassung, erstes Dashboard
- [ ] **Phase 3 — Screenshots & OCR:** periodische Screenshots, lokale OCR, Ausschlussliste, Smart Pause, DB-Verschlüsselung
- [ ] **Phase 4 — Cloud-Hybrid:** Claude-API-Anbindung für die Vorschläge, Prompt-Vorlagen, Kosten-Tracking
- [ ] **Phase 5 — Android-Begleiter:** App-Nutzungsstatistik via `UsageStatsManager`
- [ ] **Phase 6 — optional:** Android-Screen-Monitoring, Vision-Analyse einzelner Screenshots

## Hinweis

Gedacht für **eigene Geräte**. Auf einem Arbeitsrechner vorher klären, ob eine solche Erfassung erlaubt ist — und niemals ohne Wissen der Betroffenen auf fremden Geräten einsetzen.
