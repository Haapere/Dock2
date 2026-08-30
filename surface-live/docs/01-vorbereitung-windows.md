# Schritt 1 — Vorbereitung am Windows-PC

Ziel: ein geprüftes Ubuntu-ISO und ein bootfähiger **Stick A**. Dauer: ~20 Minuten, davon fast alles Download.

---

## 1.0 Die Skripte auf den PC holen

Die Dateien liegen auf GitHub, nicht auf deinem Rechner. PowerShell **als Administrator** öffnen (Startmenü → PowerShell → Rechtsklick → *Als Administrator ausführen*) und **diese eine Zeile** eingeben:

```powershell
irm https://raw.githubusercontent.com/Haapere/Dock2/refs/heads/claude/linux-live-surface-7ugch0/surface-live/windows/Start.ps1 | iex
```

Das war's. Der Einzeiler legt `C:\Users\<du>\surface-live` an, lädt beide Skripte hinein, entfernt die Windows-Downloadsperre und fragt dann, was laufen soll:

```
  1  ISO herunterladen und Checksumme vergleichen
  2  Stick schreiben (wartet, bis du ihn einsteckst)
  3  beides nacheinander
  4  nichts - ich mache von Hand weiter
```

> **Beim Kopieren aufpassen:** Nur die Zeile selbst einfügen — nichts, was mit `PS C:\...>` anfängt, und keine `#`-Kommentare aus der Anleitung. Solche Zeilen sind Terminal-*Ausgabe*, keine Befehle; PowerShell versucht sie trotzdem auszuführen und meldet dann Dinge wie `Get-Process: A positional parameter cannot be found`.

> **`irm … | iex`** lädt ein Skript aus dem Netz und führt es sofort aus. Bei deinem eigenen Repo ist das in Ordnung — bei fremden Quellen solltest du sowas nie blind ausführen.

### Wenn du lieber selbst tippst

```powershell
cd "$env:USERPROFILE\surface-live"
```

Danach `.\Stick-vorbereiten.ps1` oder `.\Watch-Stick.ps1` starten. `„… wurde nicht erkannt"` heißt immer: falscher Ordner. `Get-Location` zeigt, wo du stehst, `Get-ChildItem` was da liegt.

Alternativ das ganze Repo als ZIP: <https://github.com/Haapere/Dock2/archive/refs/heads/claude/linux-live-surface-7ugch0.zip> — entpacken, dann in `surface-live\windows` wechseln.

---

## 1.1 BitLocker-Wiederherstellungsschlüssel sichern

**Bevor du irgendetwas am Surface änderst.** Wenn Windows auf dem Surface verschlüsselt ist (bei Surface-Geräten Standard), kann eine geänderte Firmware-Einstellung dazu führen, dass Windows beim nächsten Start nach einem 48-stelligen Schlüssel fragt. Ohne den Schlüssel ist Windows verloren.

Am **Surface** (nicht am Zweit-PC):

1. Einstellungen → *Datenschutz und Sicherheit* → *Geräteverschlüsselung*
2. Wenn eingeschaltet: auf *BitLocker-Laufwerkverschlüsselung* → *Wiederherstellungsschlüssel sichern*
3. „In Ihrem Microsoft-Konto speichern" **und** zusätzlich ausdrucken oder auf einen anderen Stick legen

Später abrufbar unter <https://account.microsoft.com/devices/recoverykey>.

> Der hier beschriebene Weg lässt Secure Boot eingeschaltet und fasst die Windows-Installation nicht an — das Risiko ist gering. Trotzdem: zwei Minuten für den Schlüssel, dann ist es kein Thema mehr.

---

## 1.2 ISO herunterladen und prüfen

PowerShell im Ordner `surface-live/windows` öffnen:

```powershell
.\Stick-vorbereiten.ps1
```

Das Skript

* holt `SHA256SUMS` von releases.ubuntu.com,
* sucht darin das aktuellste Desktop-Image für amd64 (derzeit `ubuntu-26.04.1-desktop-amd64.iso`),
* lädt es in den Downloads-Ordner,
* und vergleicht die Prüfsumme.

Falls PowerShell die Ausführung blockiert:

```powershell
powershell -ExecutionPolicy Bypass -File .\Stick-vorbereiten.ps1
```

Schon eine ISO-Datei da? Dann nur prüfen:

```powershell
.\Stick-vorbereiten.ps1 -NurPruefen
```

**Wenn die Prüfsumme nicht stimmt:** Datei löschen und neu laden. Nicht auf den Stick schreiben — ein beschädigtes Abbild führt zu Installationsfehlern, die man später kaum zuordnen kann.

### Andere Distribution?

```powershell
.\Stick-vorbereiten.ps1 -Release 24.04     # ältere LTS
```

Xubuntu und Linux Mint liegen nicht auf releases.ubuntu.com — die ISOs dort direkt laden ([xubuntu.org](https://xubuntu.org/download/), [linuxmint.com](https://linuxmint.com/download.php)) und die Prüfsumme mit `Get-FileHash -Algorithm SHA256 <datei>` gegen die Seite des Anbieters vergleichen.

---

## 1.3 Stick A schreiben — automatisch

PowerShell **als Administrator** öffnen:

```powershell
.\Watch-Stick.ps1
```

Das Skript merkt sich die bereits angesteckten Datenträger und wartet. Sobald du Stick A einsteckst:

1. Modell, Größe und Laufwerksbuchstabe werden angezeigt,
2. geprüft wird: hängt per USB, ist kein System- oder Startdatenträger, Größe zwischen 7 und 128 GB,
3. nach deinem `JA` wird das ISO roh auf das Gerät geschrieben — derselbe Vorgang wie Rufus im DD-Modus.

```powershell
.\Watch-Stick.ps1 -Einmal          # nach dem ersten Stick beenden
.\Watch-Stick.ps1 -Automatisch     # ohne Rückfrage (nur wenn NUR der Zielstick steckt)
```

Nach dem Schreiben fragt Windows unter Umständen, ob der Datenträger formatiert werden soll — **nicht formatieren**. Windows kann die Linux-Partitionen schlicht nicht lesen.

Wenn du lieber selbst klickst, geht auch der Weg über Rufus:

## 1.3b Stick A schreiben (Rufus)

[Rufus](https://rufus.ie) herunterladen (die portable Variante reicht), starten:

| Feld | Wert |
|---|---|
| Laufwerk | **Stick A** — Bezeichnung und Größe kontrollieren |
| Startart | *Abbild* → das geprüfte ISO auswählen |
| Partitionsschema | **GPT** |
| Zielsystem | **UEFI (ohne CSM)** |
| Dateisystem | FAT32 (Standard) |
| Schreibmodus | *ISO-Abbild-Modus (empfohlen)* |

Rufus **löscht den gewählten Stick vollständig**. Zweimal hinschauen, welches Laufwerk ausgewählt ist.

Alternativ funktioniert [Ventoy](https://www.ventoy.net) genauso: einmal auf den Stick installieren, danach ISO-Dateien einfach draufkopieren. Praktisch, wenn du mehrere Distributionen ausprobieren willst.

---

## 1.4 Stick B bereitlegen

Stick B (≥ 64 GB, USB 3.x) **nicht** formatieren — der Installer macht das gleich selbst. Nur sicherstellen, dass nichts Wichtiges mehr drauf ist: **er wird komplett gelöscht.**

Weiter mit [Schritt 2](02-system-auf-stick-bauen.md).
