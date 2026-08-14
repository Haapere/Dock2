package de.fokusradar.begleiter

import android.util.Log
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONArray
import org.json.JSONObject

/** Antwort des Rechners. */
data class SyncAntwort(
    val ok: Boolean,
    val code: Int,
    val text: String,
) {
    /** Kurze Meldung für die Oberfläche. */
    fun meldung(): String = when {
        ok -> text
        code == 401 -> "Token stimmt nicht — mit dem aus „fokusradar android“ vergleichen."
        code == 404 -> "Der Rechner nimmt nichts an: [android] aktiv = true fehlt noch."
        code == 503 -> "Auf dem Rechner ist kein Token hinterlegt."
        code == 0 -> "Rechner nicht erreichbar: $text"
        else -> "Fehler $code: $text"
    }
}

/**
 * Schickt die Zahlen an das FokusRadar-Dashboard im Heimnetz.
 *
 * Bewusst mit [HttpURLConnection] und `org.json` aus dem System: die App soll
 * ohne zusätzliche Netzwerk-Bibliothek auskommen. Es gibt genau zwei Aufrufe,
 * einen zum Prüfen und einen zum Senden.
 */
class SyncClient(private val settings: Settings) {

    /** Verbindung und Token prüfen (GET /api/android/status). */
    fun status(): SyncAntwort {
        val antwort = aufruf("GET", PFAD_STATUS, null)
        if (!antwort.ok) return antwort
        return SyncAntwort(true, antwort.code, "Verbindung steht, Token passt.")
    }

    /** Nutzungszahlen übertragen (POST /api/android/nutzung). */
    fun send(tage: List<DayUsage>): SyncAntwort {
        if (tage.isEmpty()) {
            return SyncAntwort(true, 200, "Nichts zu senden — keine Nutzung erfasst.")
        }
        val antwort = aufruf("POST", PFAD_NUTZUNG, baueRumpf(tage))
        if (!antwort.ok) return antwort
        return try {
            val daten = JSONObject(antwort.text)
            SyncAntwort(
                true,
                antwort.code,
                "Gesendet: ${daten.optInt("gespeichert")} Apps aus ${tage.size} Tag(en).",
            )
        } catch (unlesbar: Exception) {
            SyncAntwort(true, antwort.code, "Gesendet.")
        }
    }

    /** Die Zahlen in genau die Form bringen, die die Gegenstelle erwartet. */
    private fun baueRumpf(tage: List<DayUsage>): String {
        val listeTage = JSONArray()
        for (tag in tage) {
            val apps = JSONArray()
            for (app in tag.apps) {
                apps.put(
                    JSONObject()
                        .put("paket", app.packageName)
                        .put("name", app.label ?: JSONObject.NULL)
                        .put("sekunden", app.seconds)
                        .put("oeffnungen", app.opens),
                )
            }
            listeTage.put(
                JSONObject()
                    .put("datum", tag.day.toString())
                    .put("apps", apps),
            )
        }
        return JSONObject()
            .put("geraet", settings.deviceName)
            .put("tage", listeTage)
            .toString()
    }

    private fun aufruf(methode: String, pfad: String, rumpf: String?): SyncAntwort {
        val adresse = settings.serverUrl.trimEnd('/') + pfad
        var verbindung: HttpURLConnection? = null
        return try {
            verbindung = (URL(adresse).openConnection() as HttpURLConnection).apply {
                requestMethod = methode
                connectTimeout = VERBINDUNG_TIMEOUT
                readTimeout = ANTWORT_TIMEOUT
                setRequestProperty("Authorization", "Bearer ${settings.token}")
                setRequestProperty("Accept", "application/json")
                if (rumpf != null) {
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json; charset=utf-8")
                }
            }
            if (rumpf != null) {
                verbindung.outputStream.use { strom ->
                    strom.write(rumpf.toByteArray(Charsets.UTF_8))
                }
            }
            val code = verbindung.responseCode
            val strom = if (code in 200..299) verbindung.inputStream else verbindung.errorStream
            val text = strom?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            SyncAntwort(code in 200..299, code, lesbar(text))
        } catch (fehler: IOException) {
            Log.w(TAG, "Sync fehlgeschlagen", fehler)
            SyncAntwort(false, 0, fehler.message ?: "unbekannter Netzwerkfehler")
        } finally {
            verbindung?.disconnect()
        }
    }

    /** Aus der JSON-Antwort die Meldung holen, sonst den Rohtext kürzen. */
    private fun lesbar(text: String): String = try {
        val daten = JSONObject(text)
        daten.optString("detail").takeIf { it.isNotBlank() } ?: text
    } catch (keinJson: Exception) {
        text.take(200)
    }

    companion object {
        private const val TAG = "FokusRadarSync"
        private const val PFAD_STATUS = "/api/android/status"
        private const val PFAD_NUTZUNG = "/api/android/nutzung"
        private const val VERBINDUNG_TIMEOUT = 10_000
        private const val ANTWORT_TIMEOUT = 20_000
    }
}
