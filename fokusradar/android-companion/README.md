# FokusRadar-Begleiter (Android)

Die App zählt, wie lange welche App auf dem Handy im Vordergrund war, und
schickt diese Zahlen im Heimnetz an das FokusRadar-Dashboard auf dem Rechner.
Damit steht die Bildschirmzeit des Handys neben der des Rechners in derselben
Tagesansicht.

Was das Handy verlässt: **Paketname, App-Name, Sekunden, Anzahl der Aufrufe** —
je App und Tag. Keine Inhalte und keine Benachrichtigungen. Und es verlässt das
Handy nur in Richtung des einen Rechners, dessen Adresse in den Einstellungen
der App steht.

Bildschirmfotos schickt die App nur, wenn man sie eigens dafür einschaltet —
siehe [Bildschirm-Aufnahmen](#bildschirm-aufnahmen-optional) weiter unten.

## Voraussetzungen auf dem Rechner

```bash
fokusradar android --token-neu     # Geheimnis erzeugen (landet in config.toml)
```

Danach in der Konfiguration `[android] aktiv = true` setzen und das Dashboard so
starten, dass es im Heimnetz erreichbar ist:

```bash
fokusradar dashboard --host 0.0.0.0
```

`fokusradar android` zeigt anschließend die Adresse, die in die App gehört
(z. B. `http://192.168.1.42:8760`), und listet die bereits bekannten Geräte.

Ohne `aktiv = true` gibt es den Sync-Endpunkt nicht: das Dashboard antwortet mit
404, als wäre nie einer eingebaut worden.

## Bauen

Ein Gradle-Wrapper liegt hier bewusst nicht im Repository (die `gradle-wrapper.jar`
ist eine Binärdatei). Zwei Wege:

* **Android Studio**: Ordner `android-companion` öffnen, den Rest erledigt die IDE.
* **Kommandozeile** mit installiertem Gradle 8.7+ und Android SDK 34:

  ```bash
  cd android-companion
  gradle wrapper          # legt gradlew und die Wrapper-Jar an (einmalig)
  ./gradlew assembleDebug
  ```

  Die APK liegt danach unter `app/build/outputs/apk/debug/`.

Installieren mit `adb install -r app/build/outputs/apk/debug/app-debug.apk` oder
per Dateiübertragung aufs Handy.

Die App bringt **keine Google-Play-Dienste** mit; sie läuft genauso auf einem
Gerät mit microG oder ganz ohne Google-Anteile. Verwendet werden nur
`androidx.core`, `androidx.appcompat` und `androidx.work`.

## Einrichten auf dem Handy

1. App öffnen, **Adresse** und **Token** vom Rechner eintragen, Gerätename nach
   Geschmack ändern, **Speichern**.
2. **Berechtigung erteilen** — Android öffnet die Systemliste „Zugriff auf
   Nutzungsdaten“; dort den FokusRadar-Begleiter einschalten. Diese Berechtigung
   lässt sich nur von Hand vergeben, dafür gibt es keinen Dialog.
3. **Verbindung testen** — sagt, ob Adresse und Token stimmen.
4. **Jetzt senden** — überträgt die letzten sieben Tage.
5. Optional **Einmal täglich von allein senden** ankreuzen. Den genauen
   Zeitpunkt wählt Android selbst; ohne Netz wartet der Auftrag.

## Wie gemessen wird

Grundlage ist `UsageStatsManager.queryEvents`: das System meldet, wann welche App
in den Vordergrund kam und ihn wieder verließ. Daraus ergeben sich Vordergrundzeit
und Aufrufe je App — sauber auf Kalendertage geschnitten. Die fertige
Tagesaufstellung von `queryAndAggregateUsageStats` wäre bequemer, hält sich aber
nicht an Tagesgrenzen.

Ein Sync schickt immer den **vollen Stand** der letzten Tage, keine Differenz.
Der Rechner ersetzt die Zahlen eines Tages dabei komplett — zweimal senden
verdoppelt also nichts.

## Kategorien

Die Pakete laufen auf dem Rechner durch dieselben Regeln wie die Programme
(`categories.yaml`): der Paketname steht an der Stelle des Prozesses, der
App-Name an der Stelle des Fenstertitels. Ein paar gängige Pakete sind in den
eingebauten Regeln schon einsortiert; eigene Apps trägt man dort nach:

```yaml
  - name: ablenkung
    zaehlt_als: ablenkung
    prozesse:
      - com.instagram.android
      - de.meinspiel.app
```

## Bildschirm-Aufnahmen (optional)

Getrennt einzuschalten und standardmäßig aus: die App kann in großen Abständen
ein Bild des Bildschirms aufnehmen und an den Rechner schicken. Dort wird der
Text lokal erkannt, der Text gespeichert und das Bild gelöscht — genau wie bei
den Aufnahmen des Rechners. **Ins Internet geht davon nichts.**

So läuft es ab:

1. Abstand einstellen (Vorgabe 30 Minuten) und die Sperrliste durchsehen.
2. **Aufnahmen starten** — Android fragt selbst nach der Freigabe. Sie gilt nur
   für diese Sitzung und erlischt beim Beenden der App oder des Dienstes.
3. Solange aufgenommen wird, steht eine Benachrichtigung in der Leiste. Ein
   Tippen darauf beendet es sofort.

Zwei Filter greifen, bevor irgendetwas gespeichert wird:

* **auf dem Handy**, vor der Aufnahme: steht eine App aus der Sperrliste im
  Vordergrund, entsteht gar kein Bild. Vorbelegt sind Bank, Passwortspeicher,
  Authenticator und Messenger; die Liste lässt sich in der App ergänzen (ein
  Suchwort je Zeile, Teiltreffer genügt).
* **auf dem Rechner**, vor dem Schreiben: passt der Paketname auf die
  Ausschlussliste, wird das Bild verworfen, ohne es anzusehen und ohne es
  überhaupt auf die Platte zu legen.

Der Rechner nimmt nur an, wenn dort `[screenshots] aktiv = true` gesetzt ist —
sonst antwortet er mit 409. Wer am Rechner keine Screenshots will, bekommt auch
keine vom Handy untergeschoben.

Übertragen wird ein PNG mit höchstens 1280 Pixeln an der langen Kante; das
reicht für die Texterkennung und hält die Übertragung klein.

## Grenzen

* Android liefert Vordergrundzeit, keine „Bildschirm an“-Zeit. Musik im
  Hintergrund zählt also nicht mit, ein offener Browser im Vordergrund schon.
* Manche Hersteller-ROMs kürzen die Statistik älterer Tage. Wer lückenlos
  mitzählen will, lässt den täglichen Sync an.
* Der Verkehr im Heimnetz läuft unverschlüsselt (http): für eine Adresse wie
  192.168.x.x gibt es kein Zertifikat, das ein Handy prüfen könnte. Wer das
  ändern will, stellt einen Reverse-Proxy mit eigenem Zertifikat davor — siehe
  `app/src/main/res/xml/network_security_config.xml`.
