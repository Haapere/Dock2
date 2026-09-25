# 6 – Fehlersuche

Erste Maßnahme bei jedem Problem:

```powershell
.\tools\healthcheck.ps1
```

Das Skript prüft die üblichen Verdächtigen und nennt zu jedem Fund den
passenden Befehl.

---

## Kein Ton

### Der Receiver zeigt gar kein Signal

1. Ist der Receiver auf den richtigen HDMI-Eingang geschaltet?
2. Meldet Windows das Gerät überhaupt?
   ```powershell
   .\scripts\01-windows-audio.ps1 -List
   ```
   Steht der Receiver nicht in der Liste oder als „nicht angeschlossen":
   HDMI-Kabel und EDID-Problematik prüfen → [03-headless-remote.md](03-headless-remote.md)
3. Meldet Kodi das Gerät?
   ```powershell
   .\scripts\05-apply-audio-settings.ps1 -ShowDevices
   ```

### Ton bei Musik, aber nicht bei Filmen

Klassischer Passthrough-Fehler: Kodi schickt ein Format, das der Receiver
nicht dekodieren kann. Fast immer ist **TrueHD** oder **DTS-HD** angehakt,
obwohl der Receiver das nicht beherrscht.

*Einstellungen → System → Audio* → beide Haken entfernen. Kodi dekodiert dann
selbst und schickt PCM.

### Ton nur auf zwei von fünf Lautsprechern

Bei PCM bestimmt Kodi die Kanalzahl. *Anzahl der Kanäle* auf `2.0` ist für
Musik richtig; bei Mehrkanalfilmen sorgt der Passthrough für den Rest. Läuft
ein Film als PCM statt Passthrough, steht die Kanalzahl zu niedrig.

---

## Aussetzer und Stottern

### Bei Streams, nach einigen Minuten

Der Puffer greift nicht. Prüfen:

1. Liegt `advancedsettings.xml` in `%APPDATA%\Kodi\userdata\`?
2. Ist sie gültiges XML? (`healthcheck.ps1` prüft das)
3. Wurde Kodi nach dem Kopieren **neu gestartet**? Die Datei wird nur beim
   Start gelesen.
4. In Kodi während der Wiedergabe <kbd>O</kbd> drücken: Der Cache-Füllstand
   sollte deutlich über 50 % liegen.

### Abbrüche kurz nach dem Start

Der Anbieter drosselt, weil Kodi zu schnell liest. In
`advancedsettings.xml` den `readfactor` von `20` auf `10` oder `6` senken,
Kodi neu starten.

### Aussetzer nur über WLAN

1. `02-windows-tuning.ps1` ausführen – schaltet die Energieverwaltung des
   Adapters ab. Das ist mit Abstand die häufigste Ursache.
2. Im Geräte-Manager nachsehen: *Netzwerkadapter → Eigenschaften →
   Energieverwaltung* → „Computer kann das Gerät ausschalten" darf **nicht**
   angehakt sein.
3. Wenn möglich: LAN-Kabel. Der N5095 hat einen Gigabit-Port, und ein Kabel
   löst diese Klasse von Problemen endgültig.

### Ruckeln im Menü, Ton läuft sauber

GPU-Last. In `advancedsettings.xml` ist `algorithmdirtyregions` bereits auf 3
gesetzt. Zusätzlich hilft ein schlankes Skin (Estuary ist bereits sparsam;
schwere Skins mit Videowänden überfordern den N5095).

---

## Klangqualität

### Der Exklusivmodus greift nicht

Test: FLAC in Kodi starten, parallel im Browser ein Video öffnen. Bleibt der
Browser **hörbar**, läuft Kodi im Shared Mode.

Abhilfe:
```powershell
.\scripts\01-windows-audio.ps1 -DeviceFilter "<Receivername>" -RestartAudio
```
Danach Kodi neu starten. Wenn das nicht hilft, den Haken von Hand setzen:
`Win+R` → `mmsys.cpl` → Gerät → *Eigenschaften* → *Erweitert* →
„Anwendungen die exklusive Kontrolle über dieses Gerät erlauben".

### Der Receiver zeigt immer 48 kHz, egal was läuft

*Ausgabekonfiguration* steht auf `Fixed`. Auf `Best Match` umstellen.

### Titelanfänge fehlen

*Audiogerät wachhalten* auf `Immer` stellen. Hilft das nicht, zusätzlich
*Geräusch mit geringer Lautstärke senden* einschalten – der Receiver schläft
dann nicht mehr ein.

### Lauter Knacks beim Titelwechsel

Der Receiver rastet auf eine neue Samplerate ein. Das ist normal bei
„Best Match". Wenn es stört: *Ausgabekonfiguration* auf `Optimized` – dann
wechselt Kodi seltener, gibt aber gelegentlich die native Rate auf.

---

## Fernsteuerung

### Yatse/Kore findet den PC nicht

1. Läuft Kodi überhaupt?
2. Ist das Netzwerk in Windows als **privat** eingestuft?
   *Einstellungen → Netzwerk → Eigenschaften → Netzwerkprofiltyp*
   Bei „Öffentlich" blockt die Firewall alle Regeln.
3. Firewallregeln vorhanden?
   ```powershell
   Get-NetFirewallRule -DisplayName "Kodi Mediacenter*"
   ```
4. Von Hand verbinden statt suchen: IP, Port 8080, Benutzername und Passwort
   aus `%ProgramData%\KodiMediacenter\fernsteuerung.txt`
5. Zeroconf in Kodi an? *Einstellungen → Dienste → Allgemein*

### Verbindung steht, aber Befehle kommen nicht an

Prüfen, ob JSON-RPC antwortet:
```powershell
Import-Module .\tools\KodiRpc.psm1 -Force
Invoke-KodiRpc -Method 'JSONRPC.Ping'
```
Antwort `pong` = alles in Ordnung, das Problem liegt in der App.

Fehler `401` = Benutzername/Passwort stimmen nicht.

### Nach Kodi-Neustart sind Einstellungen wieder weg

Kodi überschreibt `guisettings.xml` beim Beenden. Wenn du die Datei bearbeitet
hast, während Kodi lief, ist die Änderung verloren. Deshalb:

- `04-deploy-kodi-config.ps1` nur bei **beendetem** Kodi ausführen
- `05-apply-audio-settings.ps1` nur bei **laufendem** Kodi (geht über JSON-RPC,
  Kodi übernimmt und speichert selbst)

---

## Headless-Betrieb

### Ohne Fernseher kein Ton

EDID-Problem. Ausführlich in [03-headless-remote.md](03-headless-remote.md).
Kurz: Receiver einschalten reicht oft; sonst im Receiver
*HDMI Standby Through* aktivieren; als letzte Möglichkeit ein
HDMI-EDID-Emulator mit Audiodurchleitung.

### Kodi startet nicht automatisch

1. Verknüpfung vorhanden? `explorer shell:startup` – dort muss `Kodi.lnk` liegen
2. Meldet sich Windows automatisch an? Siehe
   [03-headless-remote.md](03-headless-remote.md), Abschnitt „Automatische
   Anmeldung". Ohne Autoanmeldung wartet der PC am Anmeldebildschirm.

---

## Alles zurückdrehen

### Windows-Audio

```powershell
.\scripts\01-windows-audio.ps1 -Restore
```
Stellt das Registry-Backup wieder her. Danach Windows neu starten.

### Kodi-Konfiguration

Die Backups liegen unter `%ProgramData%\KodiMediacenter\backup\` mit
Zeitstempel. Kodi beenden, gewünschte Datei zurück nach
`%APPDATA%\Kodi\userdata\` kopieren, Kodi starten.

### Kodi komplett neu aufsetzen

Kodi beenden, `%APPDATA%\Kodi` umbenennen (nicht löschen – als Sicherung),
Kodi starten. Es legt ein frisches Profil an. Danach ab Schritt 4:

```powershell
.\scripts\04-deploy-kodi-config.ps1
```

---

## Logdateien

| Was | Wo |
|---|---|
| Kodi-Log | `%APPDATA%\Kodi\kodi.log` |
| Kodi-Log des Vorlaufs | `%APPDATA%\Kodi\kodi.old.log` |
| Backups des Setups | `%ProgramData%\KodiMediacenter\backup\` |
| Zugangsdaten | `%ProgramData%\KodiMediacenter\fernsteuerung.txt` |

Für ausführliche Logs in `advancedsettings.xml` `<loglevel>` auf `1` setzen
und Kodi neu starten. Danach wieder auf `0` – das Log wächst sonst schnell.

Beim Suchen im Log sind diese Stichworte nützlich:

- `AESinkWASAPI` – alles rund um die Audioausgabe und den Exklusivmodus
- `Exclusive` – ob der Exklusivmodus zustande kam
- `CCurlFile` – Netzwerk- und Streamfehler
- `Cache` – Pufferverhalten
