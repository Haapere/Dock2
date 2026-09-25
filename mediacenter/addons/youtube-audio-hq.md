# YouTube auf bestmögliches Audio einstellen

## Warum das nötig ist

YouTube liefert zwei Arten von Streams:

1. **Kombiniert** (progressive): Bild und Ton in einer Datei, Ton als AAC mit
   etwa 126 kbit/s. Das ist der Fallback, den Kodi ohne weitere Add-ons nimmt.
2. **Getrennt** (DASH): Bild und Ton separat. Die Tonspur liegt als **Opus**
   mit etwa 160 kbit/s vor – bei gleicher Bitrate deutlich besser als AAC, und
   hier ist die Bitrate auch noch höher.

Für mehrstündige DJ-Sets ist der Unterschied hörbar, vor allem bei Becken,
Hi-Hats und im Tiefbass.

Damit Kodi an die DASH-Streams kommt, braucht es **InputStream Adaptive**.

## Schritt 1: InputStream Adaptive installieren

*Einstellungen → Add-ons → Aus Repository installieren → Kodi Add-on Repository
→ VideoPlayer InputStream → InputStream Adaptive → Installieren*

Prüfen, dass es **aktiviert** ist: *Einstellungen → Add-ons → Meine Add-ons →
VideoPlayer InputStream → InputStream Adaptive* – dort muss „Deaktivieren"
stehen (das heißt: es ist an).

## Schritt 2: YouTube-Add-on konfigurieren

*Einstellungen → Add-ons → Meine Add-ons → Video-Add-ons → YouTube →
Konfigurieren* (Einstellungsebene auf **Experte** stellen)

### Reiter „Wiedergabe"

| Einstellung | Wert |
|---|---|
| **MPEG-DASH verwenden** | An |
| **InputStream Adaptive verwenden** | An |
| **Videoqualität** | nach Geschmack; für reine Audiowiedergabe unerheblich |
| **Nur Audio** (`Audio only`) | An, wenn der Fernseher aus bleiben soll |
| **Bevorzugter Audio-Codec** | Opus, falls die Option vorhanden ist |

Die Option **Nur Audio** ist der Schlüssel für den Headless-Betrieb: Kodi lädt
dann gar keine Videospur, was auf dem N5095 spürbar CPU spart und den
Netzwerkbedarf halbiert. Für DJ-Sets, bei denen das Bild ohnehin nur ein
Standbild ist, ist das die richtige Einstellung.

Falls die Option in deiner Version anders heißt: Sie steht im Bereich
*Wiedergabe* oder *Stream-Auswahl* und enthält „Audio".

### Reiter „API"

Hier kommen die eigenen Schlüssel hinein. Ohne sie ist das Add-on stark
eingeschränkt oder funktionslos – das ist keine Schikane des Entwicklers,
sondern Folge der YouTube-Kontingentregeln.

Einrichtung, etwa zehn Minuten:

1. [Google Cloud Console](https://console.cloud.google.com/) öffnen, Projekt
   anlegen
2. *APIs & Dienste → Bibliothek* → **YouTube Data API v3** aktivieren
3. *Anmeldedaten* → **API-Schlüssel** erstellen
4. *Anmeldedaten* → **OAuth-Client-ID** erstellen, Typ „TV und eingeschränkte
   Eingabegeräte"
5. API-Schlüssel, Client-ID und Client-Secret im YouTube-Add-on unter *API*
   eintragen

Die aktuelle Schritt-für-Schritt-Anleitung steht im
[Add-on-Wiki](https://github.com/anxdpanic/plugin.video.youtube/wiki).

## Schritt 3: Prüfen, ob es greift

Ein Video starten, dann in Kodi <kbd>O</kbd> drücken (Codec-Info).

- **Richtig**: Audio-Codec `opus`, Bitrate um 160 kbit/s
- **Falsch**: Audio-Codec `aac`, Bitrate um 126 kbit/s → DASH greift nicht,
  InputStream Adaptive prüfen

## Zur Erwartungshaltung

Opus bei 160 kbit/s ist gutes verlustbehaftetes Audio – aber es bleibt
verlustbehaftet. Die Kette ist damit so gut, wie die Quelle es zulässt; der
Unterschied zum FLAC-Stream von Radio Paradise bleibt hörbar.

Der Aufwand lohnt trotzdem: Der Sprung von AAC 126 auf Opus 160 ist der
größte, den man bei YouTube-Material überhaupt erreichen kann.
