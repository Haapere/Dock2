# 1 – Audio-Engine: der Signalweg im Detail

Ziel: das Bit, das im FLAC-Stream steht, erreicht den D/A-Wandler des
AV-Receivers unverändert. Kein Resampling, keine Lautstärkeänderung in
Software, keine „Verbesserungen".

## Der Weg des Signals

```
FLAC/Opus-Stream
        │
        ▼
   Kodi-Decoder                    ← entpackt auf PCM
        │
        ▼
   Kodi AudioEngine (AE)           ← hier wird entschieden: Bit-perfect oder nicht
        │
        ▼
   WASAPI Exclusive Mode           ← umgeht den Windows-Mixer vollständig
        │
        ▼
   HDMI-Ausgang Mini-PC
        │
        ▼
   AV-Receiver: D/A-Wandlung + Verstärkung
        │
        ▼
   Lautsprecher
```

Der entscheidende Punkt ist die dritte Stufe. Windows kennt zwei
Betriebsarten:

| | Shared Mode | Exclusive Mode |
|---|---|---|
| Wer mischt | Windows-Mixer | niemand |
| Samplerate | fest, wie in den Sound-Eigenschaften eingestellt | die des Quellmaterials |
| Andere Programme | können parallel Ton ausgeben | werden stummgeschaltet |
| Resampling | ja, bei jeder abweichenden Quelle | nein |
| Equalizer APO wirkt | ja | **nein** |

Für Hi-Res ist nur der Exclusive Mode richtig. Er wird von Kodi angefordert –
aber Windows lässt ihn nur zu, wenn am Gerät der Haken
**„Anwendungen die exklusive Kontrolle über dieses Gerät erlauben"** gesetzt
ist. Fehlt der Haken, fällt Kodi **still** auf Shared Mode zurück. Es gibt
keine Fehlermeldung – nur schlechteren Klang.

Genau das setzt `scripts/01-windows-audio.ps1`.

## Ein häufiges Missverständnis

In vielen Anleitungen steht, man solle in den Windows-Sound-Eigenschaften
„24 Bit, 96000 Hz" als Standardformat einstellen. Das ist für Kodi
**wirkungslos**: im Exclusive Mode wird dieses Format übergangen, Kodi setzt
die Samplerate des Quellmaterials direkt am Gerät.

Das Standardformat gilt nur für alles andere – Browser, Systemklänge,
Desktop-Player. Deshalb ist der Parameter `-SetDefaultFormat` im Skript
optional und standardmäßig aus: er schreibt einen Binärblob in die Registry,
was ein kleines Risiko trägt und für Kodi nichts bringt.

Wenn du ihn trotzdem willst (etwa weil du auch im Browser hörst):

```powershell
.\scripts\01-windows-audio.ps1 -DeviceFilter "Denon" -SetDefaultFormat -SampleRate 96000 -BitDepth 24
```

## Warum „Best Match" und nicht „Fixed"

Kodi bietet unter *Einstellungen → System → Audio → Ausgabekonfiguration*
drei Modi:

- **Fixed** – alles wird auf eine feste Samplerate umgerechnet. Ein
  44,1-kHz-FLAC landet dann auf 48 kHz. Das ist ein Resampling-Schritt, den
  wir gerade vermeiden wollen.
- **Best Match** – Kodi setzt die Samplerate des Quellmaterials, sofern das
  Gerät sie kann. **Das ist die richtige Wahl.**
- **Optimized** – wie Best Match, wechselt die Rate aber seltener. Kann bei
  Receivern helfen, die beim Umschalten laut klicken; kostet aber
  gelegentlich die native Rate.

Radio Paradise liefert 44,1 kHz, YouTube-Opus liegt bei 48 kHz. Mit
„Best Match" bekommt jeder Stream seine eigene Rate, und der Receiver schaltet
entsprechend um.

## RAM-Puffer gegen Aussetzer

Mehrstündige DJ-Sets sind der härteste Fall: eine einzige Netzwerkdelle
reicht für einen Aussetzer mitten im Mix. Die mitgelieferte
`advancedsettings.xml` setzt deshalb:

```xml
<cache>
  <buffermode>1</buffermode>       <!-- alle Quellen puffern, nicht nur "Internet" -->
  <memorysize>209715200</memorysize>  <!-- 200 MiB Vorwärtspuffer -->
  <readfactor>20</readfactor>      <!-- 20-fache Wiedergabegeschwindigkeit lesen -->
</cache>
```

`memorysize` ist der **Vorwärtspuffer**; Kodi belegt bis zum Dreifachen davon
im RAM, also rund 600 MiB. Bei 8 GB ist das unkritisch.

Faustformel für die Vorlaufzeit:

```
Vorlauf in Sekunden ≈ memorysize × 8 / Bitrate
```

Bei 200 MiB und einem 1000-kbit/s-FLAC-Stream sind das rund 25 Minuten
Vorlauf – mehr als genug Reserve für jede WLAN-Delle.

`buffermode 1` ist bewusst gewählt: Add-on-Streams (Mixcloud, SoundCloud,
YouTube-DASH) werden von Kodi nicht immer als „echter Internet-Stream"
erkannt und liefen sonst ungepuffert.

Wenn ein Anbieter bei zu schnellem Lesen drosselt – erkennbar an Abbrüchen
kurz nach dem Start – `readfactor` auf `10` oder `6` senken.

## Was noch stört

| Einstellung | Wert | Warum |
|---|---|---|
| Signalverbesserungen / Enhancements | aus | Raumklang, Bassverstärkung und Loudness rechnen am Signal herum |
| „An Anzeige angleichen" (`usedisplayasclock`) | aus | resampelt Audio auf die Bildwiederholrate |
| Stereo-Upmix | aus | erzeugt aus 2.0 künstlich Mehrkanal |
| GUI-Klänge | nie | kollidieren mit dem Passthrough-Kanal |
| „Gerät wachhalten" | immer | sonst schneidet der Receiver Titelanfänge ab |

Alle diese Werte setzt `scripts/05-apply-audio-settings.ps1` automatisch.

## Windows-Lautstärke

Im Exclusive Mode ist der Windows-Lautstärkeregler wirkungslos – gut so. Die
Lautstärke regelt der AV-Receiver, analog nach der D/A-Wandlung, ohne
Bitverlust.

Auch **Kodis** eigenen Lautstärkeregler auf 100 % lassen: Kodi rechnet
Lautstärke in Software, jede Absenkung unter 100 % kostet Auflösung. In Yatse
also nicht die Kodi-Lautstärke regeln, sondern den Receiver (viele Receiver
lassen sich per HDMI-CEC oder eigener App fernsteuern).
