# Schritt 3 — Das Surface vom Stick starten

Ziel: Linux läuft auf dem Surface Go 2. Dauer: ~5 Minuten.

---

## 3.1 Einmalig: USB-Boot in der Firmware erlauben

1. Surface **vollständig herunterfahren** (nicht nur Deckel zu).
2. **Lautstärke LAUTER gedrückt halten**, Power-Taste kurz drücken und loslassen. Lauter weiter halten, bis das Surface-Logo erscheint und die UEFI-Oberfläche kommt.
3. Unter *Boot configuration*:
   * **Enable Boot from USB Devices** → an
   * *USB Storage* in der Reihenfolge nach oben ziehen
4. Unter *Security*: **Secure Boot bleibt an.** Ubuntu ist von Microsoft signiert und bootet damit problemlos. Nur wenn du später den `linux-surface`-Kernel installierst, kommt ein zusätzlicher Schritt dazu — siehe [Schritt 4](04-surface-optimieren.md).
5. *Exit* → *Restart now*

---

## 3.2 Vom Stick booten

1. Surface aus.
2. Stick B in den USB-C-Port. (Kein USB-C-Stecker? Ein einfacher USB-C-Adapter reicht.)
3. **Lautstärke LEISER gedrückt halten**, Power kurz drücken und loslassen, Leiser weiter halten.
4. Es erscheint entweder direkt Ubuntu oder ein Bootmenü, in dem du den USB-Eintrag wählst.

Das brauchst du bei **jedem** Start vom Stick. Ohne gedrückte Leiser-Taste startet normal Windows — genau so soll es sein.

> Das Surface schiebt den Windows Boot Manager nach jedem Windows-Start wieder an die erste Stelle der Bootreihenfolge. Deshalb ist der Weg über die Leiser-Taste zuverlässiger als jede Einstellung in der Firmware — und er lässt Windows völlig in Ruhe.

---

## 3.3 Der Stick erscheint nicht im Bootmenü

Der Reihe nach:

1. **Anderer Port / Adapter?** Manche USB-C-Hubs melden sich der Firmware gegenüber zu spät. Stick möglichst direkt anstecken.
2. **EFI-Fallback vorhanden?** Im laufenden Linux (auf einem beliebigen PC) prüfen:
   ```bash
   ls /boot/efi/EFI/BOOT/BOOTX64.EFI
   ```
   Fehlt die Datei, wurde [Schritt 2.6](02-system-auf-stick-bauen.md#schritt-6) übersprungen — `sudo ./surface-setup.sh` nachholen.
3. **Umweg über Windows:** *Umschalt* halten und im Startmenü auf *Neu starten* klicken → *Ein Gerät verwenden* → USB-Eintrag. Klappt oft, wenn das Bootmenü zickt.
4. **„Enable Boot from USB Devices"** wirklich aktiviert? Punkt 3.1 nochmal durchgehen.

---

## 3.4 Erster Start

Direkt nach dem Anmelden:

```bash
cd ~/dock2/surface-live/scripts
./surface-check.sh
```

Der Bericht zeigt in einer Übersicht, was tatsächlich funktioniert — Touchscreen, Type Cover, WLAN, Akku, Sensoren, zram. Alles mit `✓` ist erledigt; alles mit `!` oder `✗` steht in [troubleshooting.md](troubleshooting.md).

Bericht zum Weiterschicken:

```bash
./surface-check.sh > ~/bericht.txt
```

Weiter mit [Schritt 4: optimieren](04-surface-optimieren.md).
