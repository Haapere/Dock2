# 8 – Geschmacksprofil und Download-Vorschläge

## Was das macht

Zwei Werkzeuge, die zusammenarbeiten:

**`sc-library.ps1`** liest deine SoundCloud-Bibliothek – Likes, Reposts,
Playlists, Gefolgte – und baut daraus ein Geschmacksprofil: wer kommt bei dir
oft vor, welche Genres dominieren, welche Titel stehen unter freier Lizenz.

**`dj-suggest.ps1`** macht daraus Vorschläge: neue Quellen für die Set-Liste
und legale Downloads in möglichst hoher Qualität.

Beides läuft wiederholt. Das Profil wächst mit jedem Lauf, und was einmal
vorgeschlagen wurde, kommt nicht wieder.

## Einrichtung

Voraussetzung ist der yt-dlp-Unterbau aus [07-dj-sets.md](07-dj-sets.md).
Die Anmeldung von dort wird mitbenutzt.

```powershell
.\tools\sc-library.ps1 -User "dein-soundcloud-name"
```

Der Name steht in der Adresszeile deines Profils: `soundcloud.com/DEIN-NAME`.
Er wird gespeichert, beim nächsten Mal reicht `.\tools\sc-library.ps1`.

Der erste Lauf dauert Sekunden und liest Likes und Reposts. Danach:

```powershell
.\tools\dj-suggest.ps1
```

## Die drei Arten von Vorschlägen

### 1. Neue Quellen

Künstler und Labels, die in deiner Bibliothek oft vorkommen, aber noch nicht
in `config\dj-sources.json` stehen. Dabei wird unterschieden:

- **Sets** – durchschnittlich über 20 Minuten. Das ist, was du suchst.
- **Einzeltracks** – kürzer. Interessant, aber keine Sets.

Übernehmen:

```powershell
.\tools\dj-suggest.ps1 -Interactive   # jeden Vorschlag einzeln entscheiden
.\tools\dj-suggest.ps1 -Apply         # alle set-artigen auf einmal
```

`-Apply` nimmt bewusst nur die set-artigen Quellen – sonst füllt sich die
Liste mit Künstlern, von denen du einen einzelnen Track magst. Abgelehnte
Vorschläge werden gemerkt und nicht erneut gezeigt. Vor jeder Änderung an
`dj-sources.json` wird eine Sicherung angelegt.

Danach holt `dj-fetch.ps1 -All` die neuen Quellen mit.

### 2. Legale Downloads auf SoundCloud

Zwei Fälle, beide ausdrücklich vom Rechteinhaber freigegeben:

**Original-Download.** Viele Künstler geben die hochgeladene Datei zum
Download frei – häufig WAV oder AIFF, also unkomprimiert. Das ist die beste
Qualität, die auf SoundCloud überhaupt existiert, deutlich über den
256 kbit/s, die dein Go+-Abo beim Streamen liefert.

SoundCloud verrät das nur bei der vollen Abfrage eines Titels, deshalb der
zweite Durchgang:

```powershell
.\tools\sc-library.ps1 -Deep -DeepLimit 100
```

Das dauert etwa eine Sekunde pro Titel und wird zwischengespeichert – beim
nächsten Lauf werden nur neue Titel geprüft. Geholt wird dann ganz normal:

```powershell
.\tools\dj-fetch.ps1 -Url "<die URL>"
```

yt-dlp nimmt automatisch die Originaldatei, wenn es eine gibt.

**Freie Lizenzen.** Titel unter Creative Commons sind ausdrücklich zur
Weiterverwendung freigegeben. Die Lizenz steht im Bericht dabei –
`cc-by-nc` heißt etwa: nutzen ja, kommerziell nein.

### 3. Bandcamp

Für Techno die beste legale Quelle überhaupt. Das Skript prüft, welche deiner
häufigsten Künstler dort eine Seite haben.

Warum das der stärkste Punkt der ganzen Liste ist:

| | Qualität | Kosten |
|---|---|---|
| SoundCloud Go+ Stream | 256 kbit/s AAC | 12 €/Monat, Musik gehört dir nicht |
| YouTube mit DASH | ~160 kbit/s Opus | kostenlos |
| **Bandcamp-Kauf** | **FLAC / WAV / AIFF, verlustfrei** | pro Album, gehört dir |

Dazu kommt: Bei Bandcamp geht der Großteil direkt an die Künstler – bei
Streaming-Diensten sind es Bruchteile eines Cents pro Abspielvorgang.

Für einen Techno-Hörer, der ohnehin 12 € im Monat zahlt, ist das eine echte
Alternative: ein bis zwei Alben monatlich, dafür verlustfrei und dauerhaft.

## Wie das Profil mit der Zeit besser wird

Jeder Lauf schreibt in
`%LOCALAPPDATA%\KodiMediacenter\taste-profile.json`:

- Neue Likes kommen dazu, die Zähler wachsen
- Gefolgte zählen dreifach – wem du folgst, ist eine bewusstere Entscheidung
  als ein einzelner Like
- Ergebnisse des Deep-Scans werden zwischengespeichert

Dadurch werden die Vorschläge mit der Zeit treffsicherer: Ein Künstler, den
du zwei Monate lang immer wieder likest, rutscht nach oben; ein einmaliger
Ausreißer bleibt unter der Schwelle (`-MinCount`, Standard 2).

Sinnvolle Routine – etwa wöchentlich:

```powershell
.\tools\sc-library.ps1 -Deep -DeepLimit 40
.\tools\dj-suggest.ps1 -Interactive
```

Oder als geplante Aufgabe, zusammen mit `dj-fetch.ps1` aus
[07-dj-sets.md](07-dj-sets.md).

## Der Bericht

Jeder Lauf schreibt
`%LOCALAPPDATA%\KodiMediacenter\vorschlaege.md` – eine Markdown-Datei mit
allen Vorschlägen als anklickbare Links. Praktisch, wenn du in Ruhe durch die
Bandcamp-Seiten stöbern willst.

## Grenzen

**Die Bandcamp-Suche ist inoffiziell.** Sie nutzt die Schnittstelle hinter dem
Suchfeld von bandcamp.com. Die ist nicht dokumentiert und kann sich ändern.
Fällt sie aus, laufen die übrigen Vorschläge weiter; mit `-SkipBandcamp`
lässt sie sich abschalten.

**Namensabgleich ist unscharf.** Ein Künstler, der auf SoundCloud anders heißt
als auf Bandcamp, wird nicht gefunden. Das Skript verlangt bewusst eine genaue
Namensübereinstimmung – lieber ein Treffer weniger als ein falscher.

**Der Deep-Scan ist langsam.** Eine Sekunde pro Titel, mit Pause dazwischen,
damit SoundCloud nicht drosselt. Bei 500 Likes ist das ein Kaffee lang.
Deshalb `-DeepLimit` und der Zwischenspeicher.

**Es liest nur, was öffentlich oder deins ist.** Private Playlists anderer
Leute sieht das Skript nicht, und ohne hinterlegte Anmeldung sieht es auch
deine eigenen nicht.
