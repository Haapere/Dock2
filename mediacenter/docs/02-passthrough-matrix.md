# 2 – Kodi-Einstellungsmatrix: Musik als PCM, Film per Passthrough

Diese Seite ist die Referenz für den Abgleich von Hand. Alles hier lässt sich
auch mit `scripts\05-apply-audio-settings.ps1` automatisch setzen – die Matrix
dient zur Kontrolle und für den Fall, dass eine Einstellung abgelehnt wurde.

## Vorbereitung

Kodi zeigt die Audio-Einstellungen nur vollständig, wenn die Einstellungsebene
hoch genug steht:

*Einstellungen → System* → unten links das Zahnrad so oft anklicken, bis dort
**Experte** steht.

## Die Matrix

*Einstellungen → System → Audio*

| Einstellung | Wert | Begründung |
|---|---|---|
| **Audioausgabegerät** | `WASAPI: <Name des Receivers>` | DirectSound kann weder Exclusive noch Passthrough. Wenn hier nur DirectSound steht: Receiver aus oder HDMI nicht verbunden. |
| **Anzahl der Kanäle** | `2.0` | Musik ist Stereo. Bei Passthrough-Material ist dieser Wert ohne Wirkung – der Receiver dekodiert selbst. |
| **Ausgabekonfiguration** | `Best Match` | Samplerate folgt der Quelle, kein Resampling. Siehe [01-audio-engine.md](01-audio-engine.md). |
| **Lautstärkeregelungsschritte** | `90` | Kosmetik. |
| **Ausgabe von Stereo auf alle Kanäle** | `Aus` | Kein künstlicher Upmix. |
| **Resampling-Qualität** | `Hoch` | Greift nur, wenn doch einmal resampelt werden muss. |
| **Originallautstärke beim Downmix beibehalten** | `An` | Verhindert unterschiedlich laute Titel. |
| **Audiogerät wachhalten** | `Immer` | Sonst braucht der Receiver bei jedem Titel 1–2 Sekunden zum Einrasten und schneidet den Anfang ab. |
| **Geräusch mit geringer Lautstärke senden** | `Aus` | Nur einschalten, wenn der Receiver trotz „Immer" einschläft. Es ist ein leises Rauschen – für audiophilen Betrieb unschön. |
| **GUI-Klänge abspielen** | `Nie` | Menüklänge kollidieren mit dem Passthrough-Stream. |

### Passthrough-Block

| Einstellung | Wert | Anmerkung |
|---|---|---|
| **Passthrough erlauben** | `An` | Hauptschalter. |
| **Dolby-Digital-fähiger Receiver (AC3)** | `An` | Praktisch jeder AV-Receiver kann das. |
| **Dolby-Digital-Plus-fähig (E-AC3)** | `An` | ARD/ZDF-Mediatheken liefern teils E-AC3. |
| **DTS-fähiger Receiver** | `An` | |
| **TrueHD-fähiger Receiver** | `An` | **Nur wenn dein Receiver es kann** – sonst bleibt der Ton stumm. |
| **DTS-HD-fähiger Receiver** | `An` | dito |
| **Dolby-Digital-Transcodierung aktivieren** | `Aus` | Nur für optisch/SPDIF gedacht. Über HDMI macht es aus verlustfreiem Mehrkanalton ein 640-kbit/s-AC3. |

### Außerhalb des Audio-Menüs

*Einstellungen → Player → Videos* (Ebene Experte):

| Einstellung | Wert | Begründung |
|---|---|---|
| **Wiedergabe an Anzeige angleichen** | `Aus` | Passt sonst die Audiogeschwindigkeit an die Bildwiederholrate an – ein Resampling, das Bit-Perfect zerstört. |
| **Bildwiederholrate anpassen** | `Bei Start/Stopp` | Für Video sinnvoll, Audio bleibt unberührt. |

## Wann läuft was?

| Quelle | Format | Betriebsart | Was der Receiver anzeigt |
|---|---|---|---|
| Radio Paradise FLAC | FLAC 16/44,1 | PCM, Exclusive | `PCM 44.1 kHz` oder `Multi Ch In` |
| Lokale FLAC-Dateien 24/96 | FLAC 24/96 | PCM, Exclusive | `PCM 96 kHz` |
| YouTube mit DASH | Opus 48 kHz | PCM, Exclusive | `PCM 48 kHz` |
| Mixcloud / SoundCloud | AAC/MP3 → PCM | PCM, Exclusive | `PCM 44.1/48 kHz` |
| ARD/ZDF-Mediathek, Film mit Dolby | AC3 / E-AC3 | **Passthrough** | `Dolby Digital` |
| Blu-ray-Rip mit DTS-HD | DTS-HD MA | **Passthrough** | `DTS-HD Master Audio` |

Der Receiver ist dabei das ehrlichste Messgerät: Wenn im Display `PCM 44.1 kHz`
steht, während ein 44,1-kHz-FLAC läuft, stimmt die Kette.

## Abnahme – fünf Prüfungen

Nach dem Setup diese Reihenfolge durchgehen:

**1. Exclusive Mode greift**

Kodi starten, einen FLAC-Stream abspielen, dann parallel im Browser ein
YouTube-Video öffnen. Der Browser muss **stumm** bleiben und Windows meldet
meist „Das Gerät wird verwendet". Bleibt der Browser hörbar, läuft Kodi im
Shared Mode → `scripts\01-windows-audio.ps1` erneut ausführen und Windows
neu starten.

**2. Samplerate folgt der Quelle**

Einen 44,1-kHz-Stream starten, ins Display des Receivers schauen: `44.1 kHz`.
Dann ein 48-kHz-Video – das Display muss auf `48 kHz` wechseln.
Wechselt es nicht, steht „Ausgabekonfiguration" auf *Fixed*.

**3. Passthrough greift**

Einen Mediathek-Film mit Dolby-Ton starten. Der Receiver muss `Dolby Digital`
anzeigen, nicht `PCM`. Zeigt er PCM, dekodiert Kodi selbst – Passthrough-Haken
prüfen.

**4. Keine abgeschnittenen Titelanfänge**

Zwei Titel hintereinander starten. Wenn der zweite Titel im ersten
halben Sekündchen fehlt, steht „Audiogerät wachhalten" nicht auf *Immer*.

**5. Der Puffer arbeitet**

Während der Wiedergabe in Kodi <kbd>O</kbd> drücken (Codec-Info). Dort steht
der Cache-Füllstand. Bei einem Stream sollte er nach kurzer Zeit deutlich über
50 % stehen. Bleibt er bei wenigen Prozent, wurde `advancedsettings.xml` nicht
eingelesen – Kodi neu starten, Datei auf Tippfehler prüfen.

Die Punkte 1–5 prüft `tools\healthcheck.ps1` teilweise automatisch.

## Wenn dein Receiver TrueHD/DTS-HD nicht kann

Beide Haken abschalten. Kodi dekodiert dann selbst und schickt PCM – klanglich
gleichwertig, solange die Kanalzahl stimmt. Bleibt der Ton bei einem Film
stumm, ist fast immer einer dieser beiden Haken zu viel gesetzt.
