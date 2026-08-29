# Schritt 2 — Ubuntu auf Stick B installieren

Ziel: ein fertig installiertes, startbereites Linux auf Stick B. Dauer: ~30 Minuten.

Das läuft auf dem **Windows-PC**, nicht auf dem Surface: Der Go 2 hat nur einen USB-C-Port, du brauchst hier aber zwei Sticks gleichzeitig.

> **Der Windows-PC wird dabei nicht verändert.** Er startet nur einmal von Stick A und geht danach normal wieder in Windows. Wichtig ist ausschließlich, im Installer die richtige Zielplatte zu wählen — dazu unten mehr.

---

## Schritt 1 — Vom Stick A booten

Beide Sticks anstecken (A und B), PC neu starten und das Boot-Menü öffnen. Die Taste hängt vom Hersteller ab, sie wird kurz beim Einschalten eingeblendet:

| Hersteller | Taste |
|---|---|
| Lenovo | F12 |
| Dell | F12 |
| HP | F9 |
| Acer / Asus | F12 bzw. Esc |
| Medion | F11 |

Im Menü den Eintrag mit **„UEFI:"** davor wählen — nicht den ohne. Ein im Legacy-Modus gestarteter Installer erzeugt einen Stick, der am Surface nicht bootet.

Alternative aus Windows heraus: *Umschalt* gedrückt halten und auf *Neu starten* klicken → *Ein Gerät verwenden* → Stick A.

Im Ubuntu-Startmenü **„Try or Install Ubuntu"** wählen.

---

## Schritt 2 — Zielplatte identifizieren

Im Live-System ein Terminal öffnen (`Strg+Alt+T`) und schauen, welches Gerät Stick B ist:

```bash
lsblk -o NAME,SIZE,TRAN,MODEL,MOUNTPOINTS
```

```
NAME   SIZE TRAN   MODEL
sda    476G sata   Samsung SSD 860        ← interne Platte des PCs, FINGER WEG
sdb      8G usb    Ultra Fit              ← Stick A (das laufende Live-System)
sdc     64G usb    Samsung Flash Drive    ← Stick B, hier soll es hin
```

Merke dir Modellnamen und Größe von Stick B. Danach richtest du dich im Installer **nicht** nach `/dev/sdX` (die Bezeichnung kann sich ändern), sondern nach **Modell + Größe**.

---

## Schritt 3 — Installer durchklicken

*Install Ubuntu* starten:

| Seite | Auswahl |
|---|---|
| Sprache / Tastatur | Deutsch, Tastaturlayout German |
| Netzwerk | WLAN verbinden (spart hinterher Zeit) |
| Installationsart | *Interactive installation* |
| Umfang | *Default selection* reicht |
| Zusätzliche Software | „Drittanbieter-Software für Grafik und WLAN" **anhaken** |
| **Ziel** | ⚠️ *Erase disk and install Ubuntu* — und darüber im Auswahlfeld **Stick B** wählen (Modell + Größe abgleichen!) |

> ⚠️ **Die einzige gefährliche Stelle der ganzen Anleitung.** Steht dort die interne Platte des PCs, löschst du dessen Windows. Wenn du dir unsicher bist: Auswahlfeld aufklappen, Größe vergleichen — 64 GB ist dein Stick, 476 GB oder 1 TB ist die interne Platte.

Danach Benutzername und Passwort setzen. Verschlüsselung („Encrypt"): kann man machen, kostet auf dem schwachen Go-2-Prozessor aber spürbar Tempo. Ohne Verschlüsselung ist der Stick bei Verlust komplett lesbar — deine Entscheidung.

Installation läuft ~15–25 Minuten. Am Ende **„Continue Testing"** wählen, *nicht* neu starten.

---

## Schritt 4 — Ins neue System wechseln

Neu starten, Stick A abziehen, vom **Stick B** booten (wieder über das Boot-Menü des PCs). Erstmalig anmelden.

---

## Schritt 5 — Updates einspielen

```bash
sudo apt update && sudo apt full-upgrade -y
```

---

## Schritt 6 — Stick portabel machen

Jetzt kommt der Schritt, ohne den der Stick am Surface **gar nicht erst im Bootmenü auftaucht**: Der Installer hinterlegt den Bootloader in der Firmware des PCs, auf dem installiert wurde. Ein anderes Gerät kennt diesen Eintrag nicht und sieht den Stick als „nicht bootfähig". Die Lösung ist der Standard-Fallback-Pfad `EFI/BOOT/BOOTX64.EFI`, den jedes UEFI von sich aus findet.

Repository holen und Skript ausführen:

```bash
sudo apt install -y git
git clone <URL-dieses-Repos> ~/dock2
cd ~/dock2/surface-live/scripts
sudo ./surface-setup.sh
```

Kein Git zur Hand? Den Ordner `surface-live` einfach auf einen dritten Stick kopieren oder aus dem laufenden System herunterladen.

Erst anschauen, was passieren würde:

```bash
./surface-setup.sh --dry-run
```

Das Skript erledigt:

* **EFI-Fallback** `EFI/BOOT/BOOTX64.EFI` → der Stick bootet auf jedem UEFI-Gerät
* **os-prober aus** → sonst sammelt das Bootmenü die Windows-Einträge jedes Rechners ein, an dem der Stick hing
* **zram-Swap** (50 % des RAM, zstd-komprimiert) → der wichtigste Hebel bei 4 GB RAM
* **weniger Schreibzugriffe** (`noatime`, Logs im RAM) → schont den Stick und beschleunigt ihn
* **iio-sensor-proxy** → automatische Bildschirmdrehung am Tablet

Es weigert sich, auf einem nicht-USB-Datenträger zu arbeiten — falls du versehentlich im falschen System bist, passiert nichts.

Zum Schluss herunterfahren, Stick abziehen, weiter mit [Schritt 3: Surface booten](03-surface-booten.md).
