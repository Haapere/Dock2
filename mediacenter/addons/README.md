# Add-on-Quellen

Die maschinenlesbare Liste steht in [`sources.json`](sources.json) und wird
von `scripts/06-install-addons.ps1` ausgewertet. Die ausführliche Einordnung –
was zuverlässig läuft, was nicht, und was man stattdessen tun kann – steht in
[`../docs/04-addons.md`](../docs/04-addons.md).

## Aufbau von `sources.json`

| Abschnitt | Bedeutung |
|---|---|
| `official` | Add-ons aus dem offiziellen Kodi-Repository, direkt in Kodi installierbar |
| `repositories` | Add-ons aus eigenen Repositories oder als Einzel-ZIP |
| `directStreams` | Stream-URLs, die ohne jedes Add-on funktionieren |

Jeder Eintrag trägt `purpose` (wofür), `homepage` (zum Nachprüfen) und – bei
den fragileren – `risk` und `notes`.

## Die Zwei-Ebenen-Strategie

**Ebene 1 – `directStreams`** ist der stabile Kern. Diese URLs werden als
Kodi-Favoriten und als `.strm`-Dateien angelegt. Kein Add-on, keine API,
nichts, was durch ein Update kaputtgehen kann. Radio Paradise liefert hierüber
echtes FLAC 16 Bit / 44,1 kHz.

**Ebene 2 – Add-ons** bringen Komfort und Auswahl, brauchen aber Pflege.
Wenn ein Add-on ausfällt, läuft Ebene 1 unbeeindruckt weiter.

## Wartung

Stream-URLs prüfen:

```powershell
.\tools\test-streams.ps1
```

Ändert Radio Paradise die URLs, steht die aktuelle Liste auf
<https://radioparadise.com/listen/stream-links>. Danach `sources.json`
anpassen und `scripts\06-install-addons.ps1` erneut ausführen.

Eigenen Stream ergänzen: entweder in `sources.json` unter
`directStreams.items` eintragen, oder direkt eine `.strm`-Datei mit der URL
als einzigem Inhalt in `%USERPROFILE%\Music\Radio-Streams\` ablegen.

## Zur Aktualität der Quellenangaben

Die Projektseiten in `sources.json` waren zum Zeitpunkt der Erstellung
erreichbar. Inoffizielle Kodi-Add-ons altern jedoch schnell: Vor der
Installation lohnt ein kurzer Blick auf die `homepage`, ob das Projekt noch
gepflegt wird. Besonders betroffen sind Mixcloud (auf Kodi 21 häufig
funktionslos) und SoundCloud (fällt bei API-Änderungen regelmäßig aus).
