# Linux vom USB-Stick — Surface Go 2

Ein vollwertiges Linux, das vom USB-Stick startet. **Windows auf dem Surface bleibt unberührt** — es wird nichts installiert, nichts partitioniert, nichts überschrieben. Stick raus, Surface neu starten, und alles ist wie vorher.

Erkanntes Gerät: **Surface Go 2 (Modell 1926, 64 GB)** — Intel, 4 GB RAM.

---

## Warum kein „Live-System mit Persistenz"

Der naheliegende Weg wäre ein Live-ISO mit Persistenz-Partition. Der hat einen harten Haken: Ein Live-System bootet **immer** den Kernel aus dem ISO. Updates, Treiber und Kernel-Pakete landen zwar in der Persistenz-Datei, werden aber nie geladen. Das System bleibt auf dem Stand des ISO-Abbilds und lässt sich nicht reparieren.

Deshalb hier: eine **echte Installation auf den Stick**. Gleiche Bedienung, aber mit Updates, eigenen Programmen, echtem Dateisystem — und identisch startbar auf anderen Rechnern.

---

## Was du brauchst

| | |
|---|---|
| **Stick A** | ≥ 8 GB, beliebig — wird nur zum Installieren gebraucht |
| **Stick B** | ≥ 64 GB, **USB 3.x**, am besten mit USB-C-Stecker oder USB-C-SSD — das wird dein Linux |
| **Windows-PC** | zum Vorbereiten (dein zweiter PC) |
| **Zeit** | rund 70 Minuten, davon ~30 Minuten Warten |

> **Zur Stick-Qualität:** Billige USB-Sticks sind bei kleinen Schreibzugriffen extrem langsam — damit fühlt sich das System zäh an, egal wie gut es eingerichtet ist. Ein solider USB-3-Stick (z. B. Samsung Fit Plus) oder eine kleine USB-C-SSD macht den Unterschied zwischen „nutzbar" und „nervig".

Der Go 2 hat nur **einen** USB-C-Port. Deshalb wird auf dem Windows-PC gebaut (dort sind zwei Ports frei) und am Surface später nur der fertige Stick B eingesteckt. Type Cover läuft über die Pogo-Pins, Strom über Surface Connect — kein Hub nötig.

---

## Zwei Wege

Jeder Schritt geht von Hand oder automatisch. Automatisch heißt: Skript starten, Stick einstecken, warten.

| | Von Hand | Automatisch |
|---|---|---|
| **Stick A** (Installer) | ISO laden, Rufus | `Watch-Stick.ps1` — erkennt den Stick beim Einstecken und schreibt das ISO |
| **Stick B** (dein System) | Ubuntu-Installer durchklicken | `build-stick.sh --watch` — baut den Stick vollständig allein |

Windows kann Stick B nicht erzeugen: dafür braucht es einen laufenden Linux-Kernel, ext4 und GRUB. `build-stick.sh` läuft deshalb in der Live-Sitzung von Stick A — dort ist es sogar sicherer als der Klick-Installer, weil es sich weigert, auf einen nicht-USB-Datenträger oder auf das laufende System zu schreiben.

## Ablauf

| Schritt | Wo | Anleitung |
|---|---|---|
| 1. ISO laden, prüfen, Stick A schreiben | Windows-PC | [docs/01-vorbereitung-windows.md](docs/01-vorbereitung-windows.md) |
| 2. Stick B bauen | Windows-PC, von Stick A gebootet | [docs/02-system-auf-stick-bauen.md](docs/02-system-auf-stick-bauen.md) |
| 3. Surface vom Stick booten | Surface Go 2 | [docs/03-surface-booten.md](docs/03-surface-booten.md) |
| 4. Prüfen und feinschleifen | Surface Go 2 | [docs/04-surface-optimieren.md](docs/04-surface-optimieren.md) |
| Wenn etwas klemmt | | [docs/troubleshooting.md](docs/troubleshooting.md) |

**Distribution: Ubuntu 26.04 LTS.** Von Microsoft signierter Bootloader (Secure Boot darf anbleiben), guter Touch-Support, Updates bis 2031. Wer es leichter mag: Xubuntu oder Linux Mint XFCE — dieselben Skripte laufen dort ebenfalls.

---

## Die zwei Tastenkombinationen am Surface

| | |
|---|---|
| **Lautstärke LEISER + Power** | Bootmenü — hier den Stick auswählen. Das brauchst du bei jedem Start vom Stick. |
| **Lautstärke LAUTER + Power** | UEFI-Einstellungen — einmalig nötig, um „Boot from USB Devices" zu erlauben. |

Power-Taste kurz drücken und loslassen, die Lautstärketaste dabei gedrückt halten, bis das Menü erscheint.

---

## Was auf dem Go 2 läuft

| Funktioniert | Funktioniert nicht |
|---|---|
| Touchscreen, Surface Pen | **Kameras** (Treiber upstream unfertig) |
| Type Cover inkl. Trackpad | Hibernate (Standby geht) |
| WLAN + Bluetooth (Intel) | |
| Lagesensor, Bildschirmdrehung | |
| Akkuanzeige, Standby, microSD | |

Der Go 2 braucht den `linux-surface`-Spezialkernel **nicht** — der Standard-Kernel deckt alles ab. Das ist der Grund, warum **Secure Boot eingeschaltet bleiben kann**, was wiederum das BitLocker-Risiko vermeidet. Falls doch etwas fehlt, lässt sich der Surface-Kernel jederzeit nachrüsten: `sudo ./scripts/surface-setup.sh --surface-kernel`.

---

## Die Skripte

| Skript | Zweck |
|---|---|
| `scripts/build-stick.sh` | Baut Stick B komplett allein: partitionieren, System kopieren, Bootloader, Benutzer, Surface-Feinschliff. `--watch` wartet auf den eingesteckten Stick |
| `scripts/surface-detect.sh` | Erkennt Modell und Generation, sagt was dieses Gerät braucht (`--json` für Weiterverarbeitung) |
| `scripts/surface-setup.sh` | Das Hauptskript: macht den Stick auf fremden Geräten bootfähig, richtet zram und Schreibschutz-Tuning ein, optional den Surface-Kernel |
| `scripts/surface-check.sh` | Prüft am laufenden System, was tatsächlich funktioniert — rein lesend |
| `windows/Stick-vorbereiten.ps1` | Lädt das ISO auf dem Windows-PC und verifiziert die Prüfsumme |
| `windows/Watch-Stick.ps1` | Wartet auf den eingesteckten Stick und schreibt das ISO roh darauf (wie Rufus im DD-Modus) |

Alle Skripte kennen `--help`. `surface-setup.sh` und `build-stick.sh` kennen `--dry-run`: zeigt jeden Schritt, führt keinen aus.

```bash
./tests/test-scripts.sh    # Selbsttest ohne Surface-Hardware
```

---

## Sicherheitsnetz

* `build-stick.sh` bricht ab, wenn das Ziel **das laufende System trägt** — auch mit `--force`. Ohne `--force` lehnt es außerdem alles ab, was nicht per USB angeschlossen ist oder kleiner als 28 GB ist.
* `Watch-Stick.ps1` schreibt nie auf System- oder Startdatenträger, nie auf etwas, das nicht per USB hängt, und nie auf Datenträger über 128 GB (Sicherheitsnetz gegen externe Festplatten).
* `surface-setup.sh` weigert sich, auf einem **nicht-USB-Datenträger** zu arbeiten (verhindert, dass es versehentlich den Bootloader des Windows-PCs anfasst). Nur mit `--force` zu übergehen.
* Jede geänderte Konfigurationsdatei bekommt vorher eine `.surface-live.bak`-Kopie.
* Vor Schritt 2 wird der **BitLocker-Wiederherstellungsschlüssel** gesichert — siehe [docs/01](docs/01-vorbereitung-windows.md). Das kostet zwei Minuten und rettet im Zweifel den Windows-Zugang.

---

## Quellen

* [linux-surface — Installation and Setup](https://github.com/linux-surface/linux-surface/wiki/Installation-and-Setup)
* [linux-surface — Surface Go 2](https://github.com/linux-surface/linux-surface/wiki/Surface-Go-2)
* [linux-surface — Supported Devices and Features](https://github.com/linux-surface/linux-surface/wiki/Supported-Devices-and-Features)
* [Ubuntu Releases](https://releases.ubuntu.com/)
