# Wenn etwas klemmt

Erste Anlaufstelle ist immer `./surface-check.sh` — der Bericht sagt, welcher Abschnitt hier gemeint ist.

---

## Booten

**Der Stick erscheint nicht im Bootmenü des Surface**
Häufigste Ursache: Der EFI-Fallback fehlt. Prüfen mit `ls /boot/efi/EFI/BOOT/BOOTX64.EFI`, beheben mit `sudo ./surface-setup.sh`. Weitere Ursachen in [03-surface-booten.md](03-surface-booten.md#33-der-stick-erscheint-nicht-im-bootmenü).

**Es startet immer Windows**
Beim Einschalten *Lautstärke LEISER* gedrückt halten. Ohne die Taste ist Windows-Start korrektes Verhalten — das Surface setzt den Windows Boot Manager nach jedem Windows-Start wieder an die erste Stelle.

**Windows verlangt plötzlich den BitLocker-Wiederherstellungsschlüssel**
Ausgelöst durch eine geänderte Firmware-Einstellung (typischerweise Secure Boot). Schlüssel unter <https://account.microsoft.com/devices/recoverykey> abrufen, eingeben — Windows startet danach normal. Anschließend Secure Boot wieder einschalten, dann fragt es nicht erneut.

**Hängt beim Booten an einem schwarzen Bildschirm mit Cursor**
Im GRUB-Menü `e` drücken, in der `linux`-Zeile hinter `quiet splash` ein `nomodeset` ergänzen, `Strg+X` zum Starten. Hilft das, ist es ein Grafiktreiber-Thema — dann `sudo apt full-upgrade` und einen neueren Kernel versuchen.

**GRUB zeigt Windows-Einträge fremder Rechner**
`GRUB_DISABLE_OS_PROBER=true` fehlt. `sudo ./surface-setup.sh` ausführen, das setzt es und aktualisiert GRUB.

---

## Eingabe

**Touchscreen reagiert nicht**
Am Go 2 sollte er ab Werk laufen. Prüfen:
```bash
grep -i touch /proc/bus/input/devices
```
Nichts dabei? `sudo ./surface-setup.sh --surface-kernel` installiert Kernel und `iptsd`. Danach `systemctl status iptsd`.

**Touch trifft neben den Fingern / Achsen vertauscht**
Meist nach einer Drehung. `monitor-sensor` prüft den Lagesensor; läuft `iio-sensor-proxy` nicht, nachinstallieren: `sudo apt install iio-sensor-proxy`.

**Type Cover tot**
Erst abziehen und neu anstecken (die Pogo-Pins brauchen manchmal einen zweiten Anlauf). Bleibt es dabei: `sudo ./surface-setup.sh --surface-kernel`. Für die Zwischenzeit hilft die Bildschirmtastatur (*Einstellungen → Barrierefreiheit*).

**Trackpad scrollt zu empfindlich**
*Einstellungen → Maus und Tastfeld → Zeigergeschwindigkeit*; natürliches Scrollen lässt sich dort ebenfalls umstellen.

---

## Funk und Strom

**Kein WLAN**
```bash
ip link                       # ist ein wl...-Interface da?
rfkill list                   # per Software oder Hardware blockiert?
sudo rfkill unblock all
dmesg | grep -i firmware      # fehlende Firmware-Dateien?
```
Der Go 2 nutzt Intel-WLAN und läuft ab Werk. Bei älteren Surface-Modellen mit Marvell-Chip: `sudo apt install --reinstall linux-firmware`.

**Akku wird im Standby schnell leer**
Modern Standby (s0ix) verbraucht mehr als ein klassischer Suspend. Prüfen mit `cat /sys/power/mem_sleep`. Zusätzlich: gekoppelte Bluetooth-LE-Geräte (auch der Surface Pen) können auf manchen Modellen das Stromsparen blockieren — testweise entkoppeln.

**Akkustand wird nicht angezeigt**
```bash
ls /sys/class/power_supply/
```
Fehlt `BAT1`, hilft der Surface-Kernel.

---

## System

**Alles ist zäh**
Meistens der Stick, nicht das System. Messen:
```bash
sudo hdparm -t /dev/sdX       # sequenziell lesen
```
Unter ~30 MB/s ist der Stick der Flaschenhals — dagegen hilft nur bessere Hardware (USB-3-Stick oder USB-C-SSD). Sonst prüfen, ob zram läuft: `zramctl`, notfalls `sudo ./surface-setup.sh`.

**Speicher voll**
```bash
df -h /
sudo apt autoremove --purge && sudo apt clean
journalctl --vacuum-size=32M
```

**Kamera funktioniert nicht**
Bekannt und ungelöst: Die Surface-Kameras brauchen Treiber, die upstream noch nicht fertig sind. Das gilt für alle gängigen Surface-Modelle. Workaround: eine USB-Webcam.

**Nach einem Kernel-Update bootet es nicht mehr**
Im GRUB-Menü *Advanced options* → den vorherigen Kernel wählen. Läuft das System wieder, den kaputten Kernel entfernen: `sudo apt remove linux-image-<version>`.

---

## ARM-Surfaces

Betrifft **Surface Pro X**, Surface Pro 9 5G und die Copilot+-Modelle mit Snapdragon-Prozessor — **nicht** deinen Go 2.

Diese Geräte haben eine ARM-CPU. Gewöhnliche Linux-ISOs sind für x86 gebaut und booten dort grundsätzlich nicht. Es gibt Projekte für einzelne Modelle (etwa Ubuntu Concept für Snapdragon X), aber keinen Weg, der dieser Anleitung entspricht: kein signierter Bootloader, unvollständige Treiber, kein Live-Betrieb vom Stick. `surface-detect.sh` erkennt solche Geräte und sagt es ausdrücklich, statt eine Anleitung anzubieten, die nicht funktioniert.

---

## Nichts passt?

`./surface-check.sh > bericht.txt` und den Bericht mitschicken. Dazu:

```bash
uname -a
lsb_release -a
journalctl -p err -b --no-pager | tail -40
```
