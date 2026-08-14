package de.fokusradar.begleiter

import android.content.Context
import android.os.Build

/**
 * Einstellungen des Begleiters — Adresse des Rechners, gemeinsames Geheimnis,
 * Gerätename.
 *
 * Alles liegt in den privaten Einstellungen der App auf dem Handy. Ein Konto
 * gibt es nicht, angemeldet wird sich nirgends.
 */
class Settings(context: Context) {

    private val speicher = context.applicationContext
        .getSharedPreferences(NAME, Context.MODE_PRIVATE)

    /** Basisadresse des Dashboards, z. B. `http://192.168.1.42:8760`. */
    var serverUrl: String
        get() = speicher.getString(SCHLUESSEL_URL, "") ?: ""
        set(wert) = speicher.edit().putString(SCHLUESSEL_URL, wert.trim().trimEnd('/')).apply()

    /** Gemeinsames Geheimnis aus `fokusradar android --token-neu`. */
    var token: String
        get() = speicher.getString(SCHLUESSEL_TOKEN, "") ?: ""
        set(wert) = speicher.edit().putString(SCHLUESSEL_TOKEN, wert.trim()).apply()

    /** Name, unter dem dieses Handy im Dashboard auftaucht. */
    var deviceName: String
        get() = speicher.getString(SCHLUESSEL_GERAET, null)?.takeIf { it.isNotBlank() }
            ?: (Build.MODEL ?: "Handy")
        set(wert) = speicher.edit().putString(SCHLUESSEL_GERAET, wert.trim()).apply()

    /** Einmal am Tag von allein senden? */
    var autoSync: Boolean
        get() = speicher.getBoolean(SCHLUESSEL_AUTO, false)
        set(wert) = speicher.edit().putBoolean(SCHLUESSEL_AUTO, wert).apply()

    /** Ergebnis des letzten Sync — nur zur Anzeige. */
    var lastResult: String
        get() = speicher.getString(SCHLUESSEL_LETZTES, "") ?: ""
        set(wert) = speicher.edit().putString(SCHLUESSEL_LETZTES, wert).apply()

    /** Steht genug in den Einstellungen, um überhaupt senden zu können? */
    val ready: Boolean
        get() = serverUrl.isNotBlank() && token.isNotBlank()

    companion object {
        private const val NAME = "fokusradar"
        private const val SCHLUESSEL_URL = "server_url"
        private const val SCHLUESSEL_TOKEN = "token"
        private const val SCHLUESSEL_GERAET = "geraet"
        private const val SCHLUESSEL_AUTO = "auto_sync"
        private const val SCHLUESSEL_LETZTES = "letztes_ergebnis"
    }
}
