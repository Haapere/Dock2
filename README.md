# Dock2 — Dating App Automatisierung

Automatisierung für Dating Apps: Profil erstellen, automatisch swipen, KI-gestützter Chat.

**Unterstützte Plattformen:** Tinder · Bumble

---

## Schnellstart

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# ANTHROPIC_API_KEY in .env eintragen
```

### Konfiguration

`config.yaml` anpassen:
- `platform:` → `tinder` oder `bumble`
- `profile:` → Name, Bio, Fotos, Präferenzen
- `swiper.like_rate:` → 0.0–1.0 (z.B. 0.65 = 65% Likes)
- `anthropic_api_key:` → Claude API Key für Chat

---

## Befehle

| Befehl | Beschreibung |
|--------|-------------|
| `python main.py profil` | Profil erstellen / aktualisieren |
| `python main.py swipen` | Automatisch swipen |
| `python main.py swipen -n 50` | 50 Swipes |
| `python main.py chat` | KI-Chat Loop (dauernd) |
| `python main.py chat --einmalig` | Chat einmal prüfen |
| `python main.py komplett` | Alles: Profil → Swipen → Chat |
| `python main.py status` | Aktuelle Matches anzeigen |

### Andere Config-Datei

```bash
python main.py --config meine_config.yaml swipen
```

---

## Architektur

```
main.py                  # CLI Entry Point
src/
├── platforms/
│   ├── base.py          # Abstrakte Plattform-Schnittstelle
│   ├── tinder.py        # Tinder Automation
│   └── bumble.py        # Bumble Automation
├── profile/
│   └── creator.py       # Profil-Einrichtung
├── swiper/
│   └── auto_swiper.py   # Intelligentes Auto-Swipen
├── chat/
│   └── bot.py           # KI-Chat mit Claude
└── utils/
    ├── browser.py        # Playwright Browser-Management
    ├── config.py         # Konfiguration laden
    └── logger.py         # Logging mit Rich
```

---

## Session-Management

Nach dem ersten Login wird die Browser-Session in `sessions/session.json` gespeichert. Beim nächsten Start wird sie automatisch geladen — kein erneuter Login nötig.

## Anti-Erkennung

- Zufällige Verzögerungen zwischen Aktionen
- Menschliches Tipp-Verhalten
- Pausen nach je N Swipes
- `navigator.webdriver` deaktiviert

---

## Nebenprojekt: `surface-live/`

Anleitung und Skripte, um ein portables Linux vom USB-Stick auf einem Microsoft Surface zu betreiben — unabhängig vom Rest dieses Repos. Siehe [surface-live/README.md](surface-live/README.md).
