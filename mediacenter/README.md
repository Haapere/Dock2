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

ZIP auf den Mini-PC kopieren und **entpacken** (Rechtsklick → *Alle extrahieren*).
Dann im entpackten Ordner:

**`START.bat` doppelklicken.**

Das ist alles. Die Datei fordert die Administratorrechte selbst an, wechselt in
den richtigen Ordner und startet die Einrichtung.

Für den täglichen Gebrauch danach: **`MENUE.bat`** – eine Auswahl der
häufigsten Aufgaben, ohne Befehle zu tippen.

### Oder von Hand

PowerShell **als Administrator** öffnen. Wichtig: PowerShell startet als
Administrator immer in `C:\Windows\System32` – erst in den entpackten Ordner
wechseln, sonst findet Windows die Skripte nicht:

```powershell
cd "$env:USERPROFILE\Downloads\kodi-hires-mediacenter\mediacenter"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

Wenn du nicht mehr weißt, wohin du entpackt hast:

```powershell
Get-ChildItem "$env:USERPROFILE" -Recurse -Filter install.ps1 -ErrorAction SilentlyContinue |
  Select-Object -First 3 DirectoryName
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

Optional, aber für DJ-Sets der größte Hebel:

| | Skript | Wirkung |
|---|---|---|
| + | `scripts\07-setup-ytdlp.ps1` | yt-dlp und ffmpeg einrichten, SoundCloud-Go+-Zugang hinterlegen |
| + | `tools\dj-fetch.ps1` | Sets lokal holen statt streamen – siehe [docs/07-dj-sets.md](docs/07-dj-sets.md) |
| + | `tools\sc-library.ps1` | SoundCloud-Bibliothek lesen, Geschmacksprofil bauen |
| + | `tools\dj-suggest.ps1` | Daraus Quellen- und Download-Vorschläge ableiten |

Jeder Schritt lässt sich einzeln ausführen und wiederholen. Vor jeder
Änderung wird gesichert – Backups unter `%ProgramData%\KodiMediacenter\backup\`.

---

## Aufbau des Pakets

```
mediacenter/
├── START.bat                        Doppelklick: Setup starten (holt Adminrechte)
├── MENUE.bat                        Doppelklick: Auswahlmenü für den Alltag
├── install.ps1                      Master-Installer
├── config/
│   ├── advancedsettings.xml         RAM-Puffer gegen Aussetzer bei langen Sets
│   ├── kodi-settings.json           Deklarative Kodi-Einstellungen
│   └── dj-sources.json              Kuratierte Techno-Quellen
├── scripts/                         Die sieben Setup-Schritte
├── tools/
│   ├── KodiRpc.psm1                 JSON-RPC-Client für Kodi
│   ├── healthcheck.ps1              Systemprüfung
│   ├── switch-audio.ps1             HDMI ⇄ USB-DAC umschalten
│   ├── test-streams.ps1             Stream-URLs prüfen
│   ├── dj-fetch.ps1                 DJ-Sets lokal holen (yt-dlp)
│   ├── fetch-somafm.ps1             SomaFM-Kanäle live abrufen
│   ├── sc-library.ps1               SoundCloud-Bibliothek → Geschmacksprofil
│   └── dj-suggest.ps1               Vorschläge: Quellen + legale Downloads
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
| [docs/07-dj-sets.md](docs/07-dj-sets.md) | DJ-Sets herunterladen statt streamen – warum das robuster ist |
| [docs/08-vorschlaege.md](docs/08-vorschlaege.md) | Geschmacksprofil aus SoundCloud, legale Download-Vorschläge, Bandcamp |

---

## Vier Dinge, die man vorher wissen sollte

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

**4. Für lange DJ-Sets ist Herunterladen besser als Streamen.**
Keine Aussetzer, sofortiges Springen an jede Stelle, und dein SoundCloud-Go+-Abo
liefert 256 kbit/s auch in Kodi – was über die Add-ons nicht geht. Ein einziges
Werkzeug (`yt-dlp`) ersetzt dabei die Add-ons für Mixcloud, SoundCloud und
YouTube und wird wöchentlich gepflegt. Details in
[docs/07-dj-sets.md](docs/07-dj-sets.md).

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
.\tools\test-streams.ps1                       # die eingerichteten
.\tools\test-streams.ps1 -IncludeCandidates    # plus die ungeprüften Kandidaten
```

**DJ-Sets holen:**
```powershell
.\tools\dj-fetch.ps1 -List
.\tools\dj-fetch.ps1 -Source "HOER"
.\tools\dj-fetch.ps1 -Url "https://soundcloud.com/drumcode/..."
```

**Vorschläge aus der eigenen SoundCloud-Bibliothek:**
```powershell
.\tools\sc-library.ps1 -User "dein-name" -Deep
.\tools\dj-suggest.ps1 -Interactive
```

**SomaFM-Kanäle einbinden** (Kanalliste wird live abgerufen):
```powershell
.\tools\fetch-somafm.ps1 -ListOnly
.\tools\fetch-somafm.ps1 -IncludeFlac
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
