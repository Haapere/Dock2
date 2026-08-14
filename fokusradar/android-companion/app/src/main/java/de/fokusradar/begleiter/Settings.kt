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

    // -- Bildschirm-Aufnahmen (Phase 6) --------------------------------------

    /**
     * Läuft die Bildschirm-Aufnahme gerade?
     *
     * Bewusst kein dauerhafter Schalter: Android verlangt vor jedem Start die
     * Zustimmung des Nutzers erneut, also endet auch diese Einstellung mit dem
     * Dienst.
     */
    var screenEnabled: Boolean
        get() = speicher.getBoolean(SCHLUESSEL_BILD, false)
        set(wert) = speicher.edit().putBoolean(SCHLUESSEL_BILD, wert).apply()

    /** Abstand zwischen zwei Aufnahmen in Minuten. */
    var screenIntervalMinutes: Int
        get() = speicher.getInt(SCHLUESSEL_TAKT, STANDARD_TAKT)
        set(wert) = speicher.edit()
            .putInt(SCHLUESSEL_TAKT, wert.coerceIn(MIN_TAKT, MAX_TAKT))
            .apply()

    /**
     * Apps, von denen nie eine Aufnahme entsteht — ein Paketname je Zeile.
     *
     * Das ist die Ausschlussliste des Handys. Sie greift **vor** der Aufnahme:
     * steht eine dieser Apps im Vordergrund, entsteht gar kein Bild.
     */
    var blockedPackages: String
        get() = speicher.getString(SCHLUESSEL_GESPERRT, STANDARD_GESPERRT)
            ?: STANDARD_GESPERRT
        set(wert) = speicher.edit().putString(SCHLUESSEL_GESPERRT, wert.trim()).apply()

    /** Ist diese App gesperrt? Teiltreffer, damit `com.bank` die ganze Familie deckt. */
    fun isBlocked(paket: String): Boolean {
        val name = paket.lowercase()
        return blockedPackages.lineSequence()
            .map { it.trim().lowercase() }
            .filter { it.isNotEmpty() }
            .any { name.contains(it) }
    }

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
        private const val SCHLUESSEL_BILD = "bildschirm"
        private const val SCHLUESSEL_TAKT = "bildschirm_takt"
        private const val SCHLUESSEL_GESPERRT = "gesperrte_apps"

        const val STANDARD_TAKT = 30
        const val MIN_TAKT = 5
        const val MAX_TAKT = 240

        /**
         * Vorbelegung der Sperrliste. Bank, Passwortspeicher und Messenger sind
         * das, was man am wenigsten auf einem Bildschirmfoto haben will —
         * deshalb stehen sie von Anfang an drin und nicht erst, wenn es zu spät
         * ist.
         */
        const val STANDARD_GESPERRT = """bank
sparkasse
volksbank
paypal
keepass
bitwarden
lastpass
com.whatsapp
org.thoughtcrime.securesms
org.telegram
com.google.android.apps.authenticator"""
    }
}
