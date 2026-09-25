# 5 – Equalizer APO: Raummoden bändigen (optional)

## Die entscheidende Einschränkung – bitte zuerst lesen

**Equalizer APO wirkt nicht, wenn Kodi im WASAPI-Exklusivmodus spielt.**

Equalizer APO klinkt sich als Audio-Processing-Object in die Windows-
Audio-Engine ein. Der Exklusivmodus umgeht genau diese Engine – das ist sein
Sinn. Beides gleichzeitig geht technisch nicht.

Du hast also die Wahl:

| | Bit-Perfect (Exklusivmodus) | Mit Equalizer APO (Shared Mode) |
|---|---|---|
| Signalweg | unverändert bis zum Receiver | wird in Software gerechnet |
| Raumkorrektur | nur im Receiver möglich | flexibel in Windows |
| Passthrough (Dolby/DTS) | funktioniert | funktioniert **nicht** |
| Samplerate | folgt der Quelle | fest auf das Windows-Standardformat |

## Die bessere Lösung zuerst

Bevor du auf Bit-Perfect verzichtest: **Dein AV-Receiver kann das
wahrscheinlich besser.** Nahezu jeder Receiver der letzten fünfzehn Jahre
bringt ein Einmesssystem mit:

- Denon/Marantz → **Audyssey**
- Yamaha → **YPAO**
- Onkyo/Pioneer → **MCACC** oder **AccuEQ**
- Sony → **DCAC**

Diese Systeme messen mit einem mitgelieferten Mikrofon, korrigieren
Raummoden, Laufzeiten und Pegel – und arbeiten **hinter** dem digitalen
Eingang, also ohne den Bit-Perfect-Pfad zu stören. Zusätzlich gibt es meist
manuelle Klangregler und bei den größeren Modellen einen parametrischen EQ.

**Empfehlung: Erst einmessen, dann hören. In den meisten Wohnzimmern erübrigt
sich Equalizer APO danach.**

Equalizer APO lohnt sich, wenn:

- der Receiver kein Einmesssystem hat oder das Ergebnis nicht überzeugt,
- du am Schreibtisch über den **USB-C DAC** hörst (dort gibt es keinen
  Receiver, der korrigieren könnte),
- du mehrere Profile brauchst (laut/leise, Techno/Jazz) und schnell wechseln
  willst.

## Installation

1. [Equalizer APO](https://sourceforge.net/projects/equalizerapo/) herunterladen
   und installieren
2. Im **Configurator** (erscheint am Ende der Installation) die Geräte
   anhaken, für die es aktiv sein soll
3. Neustart

Den Configurator kann man später jederzeit erneut starten:
`C:\Program Files\EqualizerAPO\Configurator.exe`

## Die mitgelieferten Profile

Im Ordner `dsp/` liegen vier fertige Dateien. Sie gehören nach
`C:\Program Files\EqualizerAPO\config\`.

| Datei | Zweck |
|---|---|
| `00-neutral.txt` | Nullstellung als Vergleichsbasis |
| `10-raummoden-techno.txt` | Absenkung typischer Wohnzimmer-Moden im Bass |
| `20-nacht.txt` | leises Hören ohne Bassverlust, nachbarschaftsfreundlich |
| `30-kopfhoerer-dac.txt` | Profil für den USB-C DAC am Schreibtisch |
| `config.txt.beispiel` | Vorlage für die Hauptdatei |

Eingebunden werden sie über die Hauptdatei `config.txt`:

```
Device: HDMI
Include: 10-raummoden-techno.txt

Device: USB
Include: 30-kopfhoerer-dac.txt

Device:
```

Die `Device:`-Zeile bindet alles Folgende an ein Gerät, dessen Name den
angegebenen Text enthält. Eine leere `Device:`-Zeile hebt die Bindung wieder
auf. So bekommen Receiver und Kopfhörer unterschiedliche Korrekturen.

## Die Werte anpassen – und warum das nötig ist

**Die Frequenzen in `10-raummoden-techno.txt` sind ein Startpunkt, keine
Lösung.** Raummoden hängen von den Raummaßen ab, nicht vom Musikstil. Die
voreingestellten 45, 63 und 85 Hz treffen ein Wohnzimmer von etwa 4 × 5 m –
in deinem Raum liegen sie woanders.

### Mit Messmikrofon (genau)

1. [REW – Room EQ Wizard](https://www.roomeqwizard.com/) installieren, kostenlos
2. Messmikrofon (ein UMIK-1 für rund 100 € genügt) an die Hörposition
3. Sweep 20–200 Hz aufnehmen
4. Die zwei bis drei höchsten schmalen Spitzen ablesen
5. `Fc` im Preset auf genau diese Frequenzen setzen, `Gain` auf etwa die halbe
   gemessene Überhöhung

### Ohne Messmikrofon (brauchbar)

1. Einen langsamen Sinus-Sweep 30–120 Hz abspielen
2. An der Hörposition sitzen bleiben und notieren, bei welchen Frequenzen es
   deutlich lauter wird oder etwas im Raum mitschwingt
3. Diese Frequenzen mit −4 bis −6 dB und Q = 5 absenken

### Grundregeln

- **Nur absenken, nie anheben.** Eine Raummode ist eine Überhöhung durch
  Reflexion – eine Auslöschung lässt sich durch Anheben nicht füllen, man
  heizt nur den Verstärker.
- **Schmal arbeiten**: Q zwischen 4 und 10. Breite Eingriffe nehmen dem Bass
  die Substanz.
- **Preamp mitführen**: Jede Anhebung braucht dieselbe Absenkung im `Preamp`,
  sonst übersteuert die Kette digital. Da die Presets nur absenken, reichen
  −3 dB Reserve.
- **Ein Filter nach dem anderen.** Nach jeder Änderung hören, nicht fünf auf
  einmal setzen.

## Wenn du Equalizer APO nutzt: Kodi umstellen

Damit die Korrektur greift, muss Kodi den Exklusivmodus aufgeben:

1. In Kodi: *Einstellungen → System → Audio → Audioausgabegerät* →
   `DirectSound: <Gerät>` statt `WASAPI: <Gerät>`
2. **Passthrough erlauben** → Aus (funktioniert im Shared Mode nicht)
3. In den Windows-Sound-Eigenschaften das Standardformat auf
   `24 Bit, 48000 Hz` setzen – jetzt ist dieser Wert relevant, denn alles
   wird darauf umgerechnet

Zum Zurückschalten das Gegenteil, oder einfach:

```powershell
.\scripts\05-apply-audio-settings.ps1
```

Das Skript stellt WASAPI und Passthrough wieder her.

## Fehlersuche

| Symptom | Ursache |
|---|---|
| Kein Effekt hörbar | Kodi läuft im Exklusivmodus – siehe oben |
| Kein Ton mehr | Preamp zu niedrig, oder Filtersyntax fehlerhaft. `config.txt` leeren und schrittweise aufbauen |
| Knacken und Verzerrung | Digitale Übersteuerung – `Preamp` weiter absenken |
| Nur ein Kanal betroffen | Eine `Channel:`-Zeile in der Konfiguration steht falsch |
| Effekt auf dem falschen Gerät | `Device:`-Zeile passt nicht zum Gerätenamen im Configurator |
