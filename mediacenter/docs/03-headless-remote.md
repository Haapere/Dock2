# 3 – Betrieb ohne Fernseher (Headless) und Steuerung per Smartphone

Ziel: Musik läuft, das Smartphone steuert, der Fernseher bleibt aus.

## Das zentrale Problem: HDMI und EDID

Windows erkennt HDMI-Audiogeräte über EDID – eine Kennung, die das
angeschlossene Gerät liefert. Wird der Fernseher ausgeschaltet, geben viele
AV-Receiver das EDID des Fernsehers nicht mehr durch. Windows sieht dann kein
Wiedergabegerät mehr, und Kodi verstummt oder wechselt auf die interne
Soundkarte.

Das ist keine Kodi-Eigenheit, sondern die Funktionsweise von HDMI.

### Lösungsansätze in der Reihenfolge, in der man sie probiert

**1. Receiver einschalten, Fernseher aus lassen**

Bei den meisten Receivern reicht das bereits: Der eingeschaltete Receiver
liefert sein eigenes EDID, auch wenn der Fernseher aus ist. Einfach testen –
Fernseher aus, Musik über Yatse starten.

**2. Im Receiver das EDID-Verhalten umstellen**

Wenn Schritt 1 nicht reicht, im Receiver-Menü suchen nach:

- *HDMI Standby Through* / *HDMI Pass Through* → auf **An** oder **Auto**
- *Monitor Out* → fest auf den Ausgang setzen, an dem der Fernseher hängt,
  statt „Auto"
- *EDID Mode* / *EDID Select* → falls vorhanden, auf einen festen Wert statt
  „Auto" oder „Durchschleifen"

Die Bezeichnungen unterscheiden sich je nach Hersteller; im Handbuch nach
„Standby Through" suchen.

**3. HDMI-EDID-Emulator („Dummy Plug")**

Letzter Ausweg, wenn der Receiver sich nicht überreden lässt: ein kleiner
Adapter für wenige Euro, der zwischen PC und Receiver sitzt und ein festes
EDID liefert. Achte darauf, dass das Modell **Audio durchschleift** – reine
Display-Emulatoren (die den PC nur glauben lassen, ein Monitor hinge dran)
lösen das Audioproblem nicht.

**4. Receiver dauerhaft an lassen**

Moderne AV-Receiver verbrauchen im Leerlauf wenige Watt. Für den täglichen
Musikbetrieb oft die pragmatischste Lösung.

## Automatische Anmeldung

Damit Kodi ohne Fernseher startet, muss Windows sich nach dem Einschalten
selbst anmelden – sonst wartet der PC am Anmeldebildschirm, den niemand sieht.

**Empfohlener Weg: Sysinternals Autologon**

1. [Autologon](https://learn.microsoft.com/sysinternals/downloads/autologon)
   herunterladen
2. Als Administrator starten, Benutzername, Domäne (= PC-Name) und Passwort
   eintragen, *Enable* klicken

Autologon legt das Passwort **verschlüsselt** im LSA-Speicher ab, nicht im
Klartext. Das ist der Grund, warum `02-windows-tuning.ps1` die Autoanmeldung
**nicht** selbst einrichtet: der Registry-Weg
(`AutoAdminLogon` + `DefaultPassword`) speichert das Passwort für jeden
lesbar im Klartext.

**Sicherheitsabwägung:** Automatische Anmeldung bedeutet, wer physischen
Zugang zum Gerät hat, ist angemeldet. Für einen Wohnzimmer-PC ohne
persönliche Daten ist das vertretbar. Liegen auf dem Gerät sensible Daten,
lieber ein eigenes, rechtearmes Benutzerkonto für das Mediencenter anlegen.

**Alternative ohne Autoanmeldung:** Kodi als Aufgabe im Aufgabenplaner
„Beim Start" mit „Unabhängig von der Benutzeranmeldung ausführen" starten.
Funktioniert, hat aber Nachteile bei Audio- und Grafikzugriff – für Kodi
nicht empfohlen.

## Kodi-Autostart

Richtet `scripts\02-windows-tuning.ps1` ein: eine Verknüpfung im
Autostart-Ordner (`shell:startup`). Kontrolle:

```powershell
explorer shell:startup
```

Dort muss `Kodi.lnk` liegen.

## Die Fernsteuerungs-Schnittstellen

`scripts\04-deploy-kodi-config.ps1` aktiviert alle nötigen Dienste:

| Dienst | Port | Wofür |
|---|---|---|
| Webserver / JSON-RPC über HTTP | 8080/TCP | Hauptkanal für Yatse und Kore |
| JSON-RPC über TCP | 9090/TCP | schnellere Ereignismeldungen |
| EventServer | 9777/UDP | Tastatur- und Gestensteuerung |
| Zeroconf (mDNS) | 5353/UDP | damit die App den PC von selbst findet |
| UPnP | 1900/UDP | Netzwerkfreigabe der Bibliothek |

Kontrolle in Kodi: *Einstellungen → Dienste → Steuerung*. Dort müssen stehen:

- **Steuerung von Kodi über HTTP zulassen** → An
- **Port** → 8080
- **Benutzername / Passwort** → gesetzt
- **Authentifizierung erforderlich** → An
- **Steuerung durch Programme auf anderen Systemen zulassen** → An

Unter *Einstellungen → Dienste → Allgemein*:

- **Dienste anderen Systemen bekanntgeben (Zeroconf)** → An
- **Gerätename** → z. B. `Mediencenter`

## Yatse / Kore einrichten

Die Zugangsdaten stehen nach dem Setup in:

```
%ProgramData%\KodiMediacenter\fernsteuerung.txt
```

In der App:

1. **Kore**: *Kodi hinzufügen* → meist findet die App den PC per Zeroconf
   selbst. Sonst IP, Port 8080, Benutzername und Passwort eintragen.
2. **Yatse**: *Neuen Host hinzufügen* → *Suchen*, oder manuell
   dieselben Daten. Unter *Erweitert* zusätzlich den EventServer-Port 9777
   eintragen.

**Voraussetzung**: Das Heimnetz muss in Windows als **privates Netzwerk**
eingestuft sein, sonst blockt die Firewall die Regeln.
Prüfen: *Einstellungen → Netzwerk und Internet → WLAN/Ethernet →
Eigenschaften → Netzwerkprofiltyp → Privat*.

## Sicherheit

Der Kodi-Webserver ist **nicht** für das offene Internet gebaut:

- Das Passwort liegt im Klartext in `guisettings.xml` (Kodi-Eigenheit, nicht
  änderbar)
- Die Übertragung läuft unverschlüsselt über HTTP
- JSON-RPC erlaubt weitreichende Eingriffe ins System

Deshalb gilt:

- **Port 8080 niemals im Router weiterleiten.**
- Die Firewallregeln stehen bewusst auf `LocalSubnet` – nur das eigene
  Heimnetz.
- Von unterwegs nur über VPN ins Heimnetz (WireGuard auf der FritzBox o. ä.).
- Ein eigenes Passwort benutzen, das nirgends sonst verwendet wird.

## Praktisch: Wecken per WLAN

Damit der Mini-PC nicht durchlaufen muss, kann Wake-on-LAN helfen – Yatse
kann WOL-Pakete senden. Voraussetzungen:

1. Im BIOS des BMax: *Wake on LAN* / *Power on by PCI-E* aktivieren
2. Im Gerätemanager beim Netzwerkadapter unter *Energieverwaltung*:
   „Gerät kann den Computer aus dem Ruhezustand aktivieren" anhaken
3. In Yatse beim Host die MAC-Adresse eintragen

Das funktioniert allerdings nur aus dem Ruhezustand – den
`02-windows-tuning.ps1` bewusst abschaltet. Entweder Durchlaufbetrieb ohne
WOL, oder Ruhezustand zulassen und WOL nutzen; beides zusammen geht nicht.
