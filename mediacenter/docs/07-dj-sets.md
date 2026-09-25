# 7 – DJ-Sets: die robustere Architektur

## Die Kernerkenntnis

Du hast gefragt, wie die Add-on-Basis robuster wird. Die ehrliche Antwort ist,
dass **kein Add-on** das Problem löst – weil das Problem nicht am Add-on hängt,
sondern am Streaming.

Bei einem dreistündigen Set ist Streamen der schlechtere Weg:

| Problem | Beim Streamen | Bei lokaler Datei |
|---|---|---|
| Netzdelle nach 2 Stunden | Aussetzer mitten im Mix | nichts passiert |
| An Minute 140 springen | nachpuffern, Wartezeit | sofort |
| Anbieter ändert seine API | Add-on tot, Set weg | Datei bleibt |
| Qualität | schwankt | einmal beste Fassung geholt |
| Dein Go+-Abo (256 kbit/s) | nur in der SoundCloud-App | auch in Kodi |

Wir haben im Setup 200 MB RAM-Puffer gegen Aussetzer gebaut. Das ist gut –
aber eine lokale Datei braucht gar keinen Puffer.

**Der Vorschlag: Sets herunterladen, Kodi spielt lokal.** Kodi ist darin
exzellent, und alle Fragilität verschwindet auf einen Schlag.

## yt-dlp statt fünf Add-ons

Statt je ein Add-on für Mixcloud, SoundCloud und YouTube – jedes mit eigenem
Ausfallrisiko – gibt es **ein** Werkzeug für alle: `yt-dlp`.

Warum das robuster ist:

- Deckt über tausend Plattformen ab, darunter alle deine Quellen
- Wird wöchentlich aktualisiert; ändert eine Plattform ihre API, ist der Fix
  meist in Tagen da (bei Kodi-Add-ons vergehen oft Monate, manchmal nie)
- Aktualisiert sich selbst: `yt-dlp -U`
- Kennt SoundCloud Go+ und holt damit die 256 kbit/s, die du bereits bezahlst

Das Mixcloud-Add-on, das auf Kodi 21 nicht mehr läuft, ist damit schlicht
überflüssig.

## Einrichtung

```powershell
.\scripts\07-setup-ytdlp.ps1 -SetupSoundCloud
```

Installiert yt-dlp und ffmpeg und führt durch das Hinterlegen der
SoundCloud-Zugangsdaten. Zwei Wege stehen zur Wahl:

- **Cookies aus dem Browser** – einfach, hält solange du angemeldet bleibst
- **OAuth-Token** – stabiler, hält Monate

Für das Token: soundcloud.com öffnen, <kbd>F12</kbd>, Reiter *Netzwerkanalyse*,
Filter `api-v2`, eine Anfrage anklicken, in den Anfrageheadern die Zeile
`Authorization: OAuth 2-...` suchen, den Teil nach `OAuth ` kopieren.

Das Token ist ein vollwertiger Kontozugang. Das Skript beschränkt die Datei
auf dein Benutzerkonto – weitergeben solltest du es trotzdem nie.

## Sets holen

```powershell
.\tools\dj-fetch.ps1 -List                    # konfigurierte Quellen
.\tools\dj-fetch.ps1 -Source "HOER" -Max 2    # eine Quelle
.\tools\dj-fetch.ps1 -All                     # alles durchgehen
.\tools\dj-fetch.ps1 -Url "https://soundcloud.com/drumcode/..."   # einzeln
```

Die Sets landen unter `%USERPROFILE%\Music\DJ-Sets\<Quelle>\`, benannt nach
Datum und Titel, mit eingebetteten Metadaten und Cover.

Zwei Dinge halten das aufgeräumt:

- **Archivdatei** – bereits Geholtes wird übersprungen, ein zweiter Lauf holt
  nur Neues
- **Mindestlänge** – Voreinstellung 20 Minuten, damit Trailer und
  Ankündigungen draußen bleiben

## Quellen anpassen

In [`config/dj-sources.json`](../config/dj-sources.json) stehen acht Quellen als
Startpunkt – HÖR Berlin, Boiler Room, Cercle, Awakenings, Drumcode, Slam Radio
und zwei hearthis.at-Kategorien.

**Trag ein, was du wirklich hörst.** Ein Eintrag braucht nur Name, Plattform
und URL:

```json
{
  "name": "Mein Lieblingslabel",
  "platform": "soundcloud",
  "url": "https://soundcloud.com/label/tracks",
  "genre": "Techno",
  "maxPerSource": 5
}
```

Als URL funktioniert alles, was yt-dlp versteht: YouTube-Kanäle, Playlists,
SoundCloud-Profile, einzelne Tracks, Mixcloud-Profile.

### hearthis.at

Für Techno die vielleicht unterschätzteste Quelle: sehr viele Sets stehen dort
ausdrücklich als **freier Download** bereit – rechtlich sauber und oft in
besserer Qualität als der Stream.

Kategorieseiten lassen sich nicht automatisch abrufen, einzelne Sets schon:

```powershell
.\tools\dj-fetch.ps1 -Url "https://hearthis.at/<künstler>/<set>/"
```

## Nachts automatisch holen

Damit morgens die neuen Sets da sind – Aufgabenplanung einrichten:

```powershell
$action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument '-ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Pfad\zu\mediacenter\tools\dj-fetch.ps1" -All'
$trigger = New-ScheduledTaskTrigger -Daily -At 4am
Register-ScheduledTask -TaskName 'DJ-Sets holen' -Action $action -Trigger $trigger `
    -Description 'Holt neue DJ-Sets und legt sie in die Kodi-Bibliothek'
```

Danach noch die Kodi-Bibliothek einlesen lassen – am einfachsten mit einer
zweiten Aufgabe kurz danach:

```powershell
Import-Module .\tools\KodiRpc.psm1 -Force
Invoke-KodiRpc -Method 'AudioLibrary.Scan'
```

## Platzbedarf

Ein einstündiges Set liegt bei etwa 70–120 MB, ein dreistündiges bei 250–350 MB.
Bei acht Quellen mit je drei Sets pro Lauf sind das grob 5–8 GB pro Woche.

Die SSD des BMax ist damit in ein paar Monaten voll. Zwei Gegenmittel:

- `maxPerSource` niedrig halten (2–3 reicht meist)
- Alte Sets aufräumen, etwa alles älter als 90 Tage:

```powershell
Get-ChildItem "$env:USERPROFILE\Music\DJ-Sets" -Recurse -File |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-90) } |
    Remove-Item -WhatIf
```

Das `-WhatIf` erst entfernen, wenn die Liste passt.

## Zur Rechtslage

Sets mit ausdrücklichem **Free Download** (auf hearthis.at sehr verbreitet, auf
SoundCloud per Download-Button) sind unproblematisch – das ist der vorgesehene
Weg.

Bei allem anderen ist die Sache eine Grauzone: Ein Go+-Abo bezahlt das Hören in
der App, nicht das Anlegen einer eigenen Kopie. Praktisch tut die
Offline-Funktion der App dasselbe, nur in deren eigenem Format. Für den
privaten Gebrauch auf dem eigenen Gerät ist das der übliche Umgang;
weiterverbreiten darf man es nicht.

Wo ein Free-Download angeboten wird, lohnt er sich doppelt: sauber und
meist die bessere Datei.

## Was mit den Streams bleibt

Die Direkt-Streams aus [04-addons.md](04-addons.md) behältst du natürlich –
Radio läuft nebenbei, ohne dass man etwas holen muss. Die Aufteilung wird nur
klarer:

| Zweck | Weg |
|---|---|
| Radio nebenbei | FLAC-Streams als Favoriten |
| Entdecken, zappen | YouTube-Add-on im Audio-Only-Modus |
| Sets, die du wirklich hörst | herunterladen mit `dj-fetch.ps1` |

Das YouTube-Add-on bleibt also sinnvoll – zum Stöbern. Was hängenbleibt,
wandert per `-Url` in die lokale Sammlung.
