# 4 – Add-ons für DJ-Sets, Hi-Fi-Streams und Mediatheken

## Die wichtigste Erkenntnis zuerst

Kodi-Add-ons für kommerzielle Dienste sind **inhärent fragil**. Sie greifen
auf interne Schnittstellen zu, die die Anbieter jederzeit ändern – meist ohne
Vorwarnung. Ein Add-on, das heute läuft, kann nach dem nächsten
SoundCloud-Update tot sein.

Deshalb ist dieses Setup in zwei Ebenen aufgebaut:

**Ebene 1 – bombenfest:** Direkte Stream-URLs als Favoriten und `.strm`-Dateien.
Kein Add-on, keine API, nichts, was kaputtgehen kann. Radio Paradise in FLAC
läuft hierüber und überlebt jedes Kodi-Update.

**Ebene 2 – komfortabel, aber wartungsbedürftig:** Add-ons für YouTube,
SoundCloud, Mixcloud, Mediatheken.

Wenn Ebene 2 ausfällt, läuft die Musik trotzdem weiter.

## Ebene 1: Direkt-Streams (bereits eingerichtet)

`scripts\06-install-addons.ps1` legt an:

- **Favoriten** in Kodi → in Yatse unter *Favoriten* sofort abrufbar
- **`.strm`-Dateien** unter `%USERPROFILE%\Music\Radio-Streams\`, eingebunden
  als Musikquelle „Radio-Streams"

Enthalten sind die FLAC-Streams von Radio Paradise (Main, Mellow, Rock,
Global) sowie NTS 1 und 2.

Neuen Stream hinzufügen: Textdatei mit der URL als einzigem Inhalt im
Ordner `Radio-Streams` ablegen, Endung `.strm`. Fertig.

Prüfen, ob alle Streams noch laufen:

```powershell
.\tools\test-streams.ps1
```

Falls Radio Paradise die URLs ändert: aktuelle Liste auf
<https://radioparadise.com/listen/stream-links>, danach `addons/sources.json`
anpassen und `06-install-addons.ps1` erneut ausführen.

### Zur Einordnung der Formate

| Quelle | Format | verlustfrei? |
|---|---|---|
| Radio Paradise FLAC | FLAC 16 Bit / 44,1 kHz | **ja** |
| Radio Paradise AAC-320 | AAC 320 kbit/s | nein |
| NTS | AAC | nein |
| YouTube mit DASH | Opus ~160 kbit/s | nein |
| Mixcloud | AAC/MP3 | nein |
| SoundCloud | AAC/MP3 | nein |

Radio Paradise ist damit die einzige wirklich verlustfreie Quelle in dieser
Liste – die anderen sind Streaming-Dienste, die grundsätzlich komprimiert
ausliefern. Das Setup holt aus jeder das technisch Beste heraus, aber aus
einem 160-kbit/s-Opus-Stream wird kein Hi-Res.

## Ebene 2: Add-ons

### Vorbereitung

Einmalig in Kodi: *Einstellungen → System → Add-ons →* **Unbekannte Quellen**
einschalten. Ohne diesen Schalter lassen sich keine ZIP-Dateien installieren.

`scripts\06-install-addons.ps1` lädt die verfügbaren ZIPs vorab nach
`%USERPROFILE%\Downloads\kodi-addons\` herunter.

### Aus dem offiziellen Kodi-Repository

*Einstellungen → Add-ons → Aus Repository installieren → Kodi Add-on Repository*

| Add-on | Kategorie | Priorität |
|---|---|---|
| **InputStream Adaptive** | VideoPlayer InputStream | **Pflicht** – ohne das gibt es kein DASH und damit kein Opus-Audio |
| **YouTube** | Video-Add-ons | **Pflicht** für DJ-Sets |
| **ARTE+7** | Video-Add-ons | empfohlen, Sprache auf Deutsch stellen |
| **SoundCloud** | Musik-Add-ons | optional, siehe Warnung unten |

### Aus ZIP-Dateien

*Einstellungen → Add-ons → Aus ZIP-Datei installieren*

| Add-on | Quelle | Einschätzung |
|---|---|---|
| **MediathekView** | [github.com/mediathekview/plugin.video.mediathekview](https://github.com/mediathekview/plugin.video.mediathekview) | Nicht mehr im offiziellen Repo. Durchsucht ARD, ZDF, Arte, 3Sat gemeinsam. Legt eine lokale Datenbank mit über 200.000 Einträgen an – der erste Import dauert auf dem N5095 einige Minuten. |
| **ARD und ZDF** | [github.com/rols1/Kodi-Addon-ARDundZDF](https://github.com/rols1/Kodi-Addon-ARDundZDF) | Schlanker, keine lokale Datenbank, zusätzlich Live-TV und Live-Radio. Wenn du nur ARD/ZDF brauchst: hiermit anfangen. |
| **Radio Paradise** | [codeberg.org/alxndr42/script.radioparadise](https://codeberg.org/alxndr42/script.radioparadise) | Optional. Bringt Titelanzeige und Cover-Slideshow zu den FLAC-Streams. Setzt Kodi 20+ voraus. |

### Die Problemfälle

**Mixcloud.** Das bekannte Add-on (`plugin.audio.mixcloud` von jackyNIX,
[GitHub](https://github.com/jackyNIX/xbmc-mixcloud-plugin)) wurde für ältere
Kodi-Generationen gebaut und läuft auf Kodi 21 häufig nicht mehr. Probier es
aus – wenn es scheitert, gibt es Alternativen:

1. **Der Set-Ersteller lädt meist auch auf YouTube hoch.** Für die meisten
   bekannten DJ-Sets ist das der einfachste Weg.
2. **Browser im Hintergrund**: Mixcloud im Edge/Chrome öffnen, Kodi parallel
   laufen lassen. Funktioniert – aber nur im Shared Mode, also **ohne**
   Bit-Perfect, weil Kodi das Gerät sonst exklusiv belegt.
3. **Mixcloud-Web-Player auf einem Zweitgerät** (Tablet) und per Bluetooth
   oder AirPlay an den Receiver. Klanglich schlechter, aber unkompliziert.

**SoundCloud.** Das offizielle Add-on funktioniert, fällt aber regelmäßig aus,
wenn SoundCloud seine API ändert. Bei Problemen: im Add-on eine eigene
Client-ID hinterlegen (in den Add-on-Einstellungen) oder abwarten, bis eine
neue Version erscheint.

## YouTube auf gutes Audio trimmen

Siehe die eigene Anleitung: [`addons/youtube-audio-hq.md`](../addons/youtube-audio-hq.md).

Kurzfassung: Ohne InputStream Adaptive liefert YouTube einen kombinierten
Stream mit AAC um 126 kbit/s. Mit DASH bekommt Kodi Zugriff auf die separate
Opus-Tonspur mit etwa 160 kbit/s – hörbar besser, besonders bei Bass und
Becken.

**Wichtig**: Das YouTube-Add-on braucht seit Jahren eigene API-Schlüssel aus
der Google Cloud Console. Ohne läuft es nur eingeschränkt. Die Einrichtung ist
in der Add-on-Dokumentation beschrieben und dauert etwa zehn Minuten.

## Wartung

Add-ons altern. Ein Vorschlag für die Routine:

- **Nach jedem Kodi-Update**: `tools\healthcheck.ps1` laufen lassen und die
  Add-ons kurz durchklicken.
- **Wenn ein Add-on ausfällt**: erst prüfen, ob eine neuere Version existiert
  (die Projektseiten stehen in `addons/sources.json`), dann erst suchen.
- **Was nie ausfällt**: die Direkt-Streams aus Ebene 1. Darum lohnt es sich,
  dort alles einzutragen, was du regelmäßig hörst.
