# Schritt 4 — Feinschliff auf dem Surface

Das meiste hat `surface-setup.sh` schon erledigt. Hier steht, was optional dazukommt — und wie der `linux-surface`-Kernel funktioniert, falls du ihn brauchst.

---

## 4.1 Braucht der Go 2 den linux-surface-Kernel?

**Nein.** Laut linux-surface-Wiki laufen auf dem Surface Go 2 Touchscreen, Stift, Type Cover, Trackpad, WLAN/Bluetooth, Sensoren, Akku und Standby bereits mit dem Standard-Kernel. Nicht unterstützt sind die **Kameras** — daran ändert auch der Spezialkernel nichts.

Das ist ein echter Vorteil: Der Standard-Kernel ist signiert, **Secure Boot kann anbleiben**, und du musst die Firmware des Surface nicht anfassen.

Verlass dich aber nicht auf die Tabelle, sondern auf den tatsächlichen Befund:

```bash
./surface-check.sh
```

---

## 4.2 Wenn doch etwas fehlt: Surface-Kernel nachrüsten

```bash
sudo ./surface-setup.sh --surface-kernel
```

Das Skript

1. importiert den Signaturschlüssel des Projekts nach `/usr/share/keyrings/linux-surface.gpg`,
2. trägt `https://pkg.surfacelinux.com/debian release main` als Paketquelle ein,
3. installiert `linux-image-surface`, `linux-headers-surface` und `iptsd`,
4. installiert bei aktivem Secure Boot zusätzlich `linux-surface-secureboot-mok`,
5. aktualisiert GRUB.

`libwacom-surface` wird auf Ubuntu 26.04 bewusst **ausgelassen** — das Paket hat dort einen bekannten Fehler.

### Der MokManager-Bildschirm

Der Surface-Kernel ist nicht von Microsoft signiert, sondern vom linux-surface-Projekt. Bei aktivem Secure Boot musst du dessen Schlüssel einmalig in der Firmware hinterlegen. Beim **nächsten Start** erscheint ein blauer Bildschirm:

1. *Enroll MOK* → *Continue* → *Yes*
2. Passwort: **`surface`**
3. *Reboot*

> Die Tastatur liegt an dieser Stelle im **US-Layout**. Bei `surface` macht das keinen Unterschied — merk es dir trotzdem für den Fall, dass du ein eigenes Passwort setzt.

Verpasst? Nachholen mit `sudo mokutil --import /var/lib/shim-signed/mok/MOK.der`, dann neu starten.

Prüfen, ob der Kernel läuft:

```bash
uname -r        # muss auf -surface enden
mokutil --sb-state
```

Rückgängig machen: `sudo mokutil --delete /var/lib/shim-signed/mok/MOK.der`, danach `sudo apt remove linux-image-surface`.

---

## 4.3 Sinnvolle Handgriffe für ein 10,5-Zoll-Tablet

**Bildschirmtastatur beim Abnehmen des Type Covers**
GNOME blendet sie automatisch ein. Manuell erzwingen: *Einstellungen → Barrierefreiheit → Bildschirmtastatur*.

**Skalierung** — 1920×1280 auf 10,5 Zoll ist ohne Anpassung sehr klein:
*Einstellungen → Anzeigegeräte → Skalierung 125 % oder 150 %*

**Bildschirmdrehung** kommt von `iio-sensor-proxy` (installiert `surface-setup.sh` mit). Test:
```bash
monitor-sensor       # Gerät drehen, es müssen Meldungen kommen
```

**Akkulaufzeit:** Standby läuft im Modern-Standby-Modus (s0ix) — Aufwachen ist schnell, der Verbrauch im Standby aber höher als bei Windows. Bei längeren Pausen lieber herunterfahren.

**Bluetooth-Stromsparfalle:** Auf manchen Surface-Modellen verhindert ein gekoppeltes Bluetooth-LE-Gerät (auch der Surface Pen) den Stromsparmodus. Wenn der Akku unerklärlich schnell leer wird: Bluetooth-Geräte entkoppeln und vergleichen.

---

## 4.4 Sichern

Der Stick ist normale Hardware und kann ausfallen. Ein Abbild ziehen (auf einem Linux-PC, Stick nicht eingehängt):

```bash
sudo dd if=/dev/sdX of=surface-stick.img bs=4M status=progress conv=fsync
```

Zurückspielen mit vertauschtem `if`/`of`. Für den Alltag reicht meist, `/home` auf eine microSD-Karte zu sichern — die passt gleichzeitig in den Kartenleser des Go 2.
