# Hi-Res Mediencenter für BMax B3 Pro

Setup-Paket, das einen Windows-11-Mini-PC in ein audiophiles Kodi-Mediencenter
verwandelt: bit-perfekte Wiedergabe über HDMI an den AV-Receiver,
Passthrough für Film-Tonformate, Steuerung per Smartphone bei ausgeschaltetem
Fernseher.

**Zielsystem:** BMax B3 Pro · Intel Celeron N5095 · 8 GB RAM · Windows 11
**Signalweg:** PC (HDMI) → AV-Receiver (D/A + Verstärkung) → TV
**Zweitausgang:** USB-C DAC für Kopfhörer am Schreibtisch

---

## Schnellstart

Das Paket auf den Mini-PC kopieren, PowerShell **als Administrator** öffnen:

```powershell
cd <Pfad zum Ordner>\mediacenter
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

Der Installer führt alle sieben Schritte durch und hält an zwei Stellen an,
um Kodi zu beenden bzw. zu starten. Dauer: 10–25 Minuten.

Mit bekanntem Receiver-Namen geht es zielgenauer:

```powershell
.\install.ps1 -ReceiverName "Denon" -WebPassword "EigenesPasswort"
```

Danach:

```powershell
.\tools\healthcheck.ps1
```

Die Zugangsdaten für Yatse/Kore landen in
`%ProgramData%\KodiMediacenter\fernsteuerung.txt`.

---

## Was das Setup tut

| Schritt | Skript | Wirkung |
|---|---|---|
| 1 | `scripts\01-windows-audio.ps1` | WASAPI-Exklusivmodus freischalten, Signalverbesserungen abschalten |
| 2 | `scripts\02-windows-tuning.ps1` | Kein Standby, WLAN-Energiesparen aus, Firewallregeln, Kodi-Autostart |
| 3 | `scripts\03-install-kodi.ps1` | Kodi installieren (winget, sonst Direktdownload), Profil anlegen |
| 4 | `scripts\04-deploy-kodi-config.ps1` | `advancedsettings.xml` ausrollen, Webserver und Fernsteuerung aktivieren |
| 5 | `scripts\05-apply-audio-settings.ps1` | Audiogerät, „Best Match", Passthrough – per JSON-RPC, sprachunabhängig |
| 6 | `scripts\06-install-addons.ps1` | FLAC-Streams als Favoriten und `.strm`, Add-on-Pakete herunterladen |
| 7 | `tools\healthcheck.ps1` | Abschlussprüfung mit konkreter To-do-Liste |

Jeder Schritt lässt sich einzeln ausführen und wiederholen. Vor jeder
Änderung wird gesichert – Backups unter `%ProgramData%\KodiMediacenter\backup\`.

---

## Aufbau des Pakets

```
mediacenter/
├── install.ps1                      Master-Installer
├── config/
│   ├── advancedsettings.xml         RAM-Puffer gegen Aussetzer bei langen Sets
│   └── kodi-settings.json           Deklarative Kodi-Einstellungen
├── scripts/                         Die sechs Setup-Schritte
├── tools/
│   ├── KodiRpc.psm1                 JSON-RPC-Client für Kodi
│   ├── healthcheck.ps1              Systemprüfung
│   ├── switch-audio.ps1             HDMI ⇄ USB-DAC umschalten
│   └── test-streams.ps1             Stream-URLs prüfen
├── addons/
│   ├── sources.json                 Add-on-Quellen und Direkt-Streams
│   └── youtube-audio-hq.md          YouTube auf Opus/DASH trimmen
├── dsp/                             Equalizer-APO-Presets
├── tests/                           Testsuite (ändert nichts am System)
└── docs/                            Die ausführlichen Anleitungen
```

---

## Dokumentation

| Datei | Inhalt |
|---|---|
| [docs/01-audio-engine.md](docs/01-audio-engine.md) | Signalweg, Exklusivmodus, Puffer – warum welche Einstellung |
| [docs/02-passthrough-matrix.md](docs/02-passthrough-matrix.md) | Vollständige Einstellungsmatrix und fünf Abnahmeprüfungen |
| [docs/03-headless-remote.md](docs/03-headless-remote.md) | Betrieb ohne Fernseher, EDID-Problematik, Yatse/Kore |
| [docs/04-addons.md](docs/04-addons.md) | DJ-Sets, Mediatheken, was zuverlässig läuft und was nicht |
| [docs/05-equalizer-apo.md](docs/05-equalizer-apo.md) | Raummoden bändigen – und warum der Receiver das meist besser kann |
| [docs/06-troubleshooting.md](docs/06-troubleshooting.md) | Fehlersuche nach Symptom |

---

## Drei Dinge, die man vorher wissen sollte

**1. Das Windows-Standardformat ist für Kodi bedeutungslos.**
Viele Anleitungen empfehlen, in den Sound-Eigenschaften „24 Bit, 96 kHz"
einzustellen. Im Exklusivmodus übergeht Kodi diesen Wert und setzt die
Samplerate der Quelle direkt. Entscheidend ist allein der Haken
„Anwendungen die exklusive Kontrolle erlauben" – fehlt er, fällt Kodi
**still** auf Shared Mode zurück. Details in
[docs/01-audio-engine.md](docs/01-audio-engine.md).

**2. Equalizer APO und Bit-Perfect schließen sich aus.**
Equalizer APO arbeitet in der Windows-Audio-Engine, die der Exklusivmodus
gerade umgeht. Entweder – oder. Für Raumkorrektur ist das Einmesssystem des
AV-Receivers (Audyssey, YPAO, MCACC) fast immer die bessere Wahl, weil es
hinter dem digitalen Eingang arbeitet. Details in
[docs/05-equalizer-apo.md](docs/05-equalizer-apo.md).

**3. Add-ons für kommerzielle Dienste sind fragil.**
Sie greifen auf interne Schnittstellen zu, die die Anbieter jederzeit ändern.
Deshalb ist dieses Setup zweistufig: die FLAC-Streams von Radio Paradise
laufen als reine Direkt-URLs ohne jedes Add-on und überleben jedes Update.
Add-ons kommen obendrauf. Details in [docs/04-addons.md](docs/04-addons.md).

---

## Einzelne Werkzeuge

**Auf Kopfhörer umschalten und zurück:**
```powershell
.\tools\switch-audio.ps1 -Target dac
.\tools\switch-audio.ps1 -Target hdmi
.\tools\switch-audio.ps1 -Target status
```
Schaltet Windows **und** Kodi gemeinsam um und deaktiviert beim DAC den
Passthrough (ein Kopfhörer-DAC kann Dolby/DTS nicht dekodieren).
Als Desktop-Verknüpfung praktisch:
```
powershell.exe -ExecutionPolicy Bypass -File "<Pfad>\tools\switch-audio.ps1" -Target dac
```

**Streams prüfen:**
```powershell
.\tools\test-streams.ps1
```

**Audiogeräte auflisten:**
```powershell
.\scripts\01-windows-audio.ps1 -List              # wie Windows sie sieht
.\scripts\05-apply-audio-settings.ps1 -ShowDevices # wie Kodi sie sieht
```

**Windows-Audio zurücksetzen:**
```powershell
.\scripts\01-windows-audio.ps1 -Restore
```

---

## Sicherheitshinweise

- Kodi speichert das Fernsteuerungs-Passwort **im Klartext** in
  `guisettings.xml`. Das ist eine Eigenheit von Kodi und nicht änderbar –
  deshalb ein eigenes Passwort verwenden, das nirgends sonst benutzt wird.
- Die Firewallregeln sind auf `LocalSubnet` beschränkt. **Port 8080 niemals
  im Router weiterleiten** – JSON-RPC erlaubt weitreichende Eingriffe ins
  System. Von unterwegs nur per VPN.
- Die automatische Anmeldung richtet das Paket bewusst **nicht** selbst ein.
  Der Registry-Weg speichert das Windows-Passwort im Klartext; der sichere
  Weg über Sysinternals Autologon ist in
  [docs/03-headless-remote.md](docs/03-headless-remote.md) beschrieben.

---

## Tests

```powershell
.\tests\test-syntax.ps1    # Syntaxprüfung aller Skripte
.\tests\run-tests.ps1      # Logiktests, ändert nichts am System
```

Getestet wird unter anderem der WAVEFORMATEXTENSIBLE-Binärblob Byte für Byte,
der `guisettings.xml`-Merge (darf fremde Einträge nicht verlieren) und die
XML-Maskierung bei der Favoritenerzeugung.

## Stand der Prüfung

Alle Skripte sind mit dem PowerShell-Parser auf Syntax geprüft, die
plattformunabhängige Logik ist durch die Testsuite abgedeckt. **Ein Lauf auf
echter Windows-Hardware mit angeschlossenem AV-Receiver hat noch nicht
stattgefunden** – Registry-Zugriffe, winget, WASAPI-Geräteerkennung und
Kodis JSON-RPC lassen sich nur dort verifizieren. Deshalb legt jedes Skript
vor Änderungen ein Backup an und meldet Fehlschläge einzeln, statt
abzubrechen.
