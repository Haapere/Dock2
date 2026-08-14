package de.fokusradar.begleiter

import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Process
import java.time.LocalDate
import java.time.ZoneId

/** Nutzung einer App an einem Tag. */
data class AppUsage(
    val packageName: String,
    val label: String?,
    val seconds: Long,
    val opens: Int,
)

/** Ein Tag mit den Apps, die an ihm im Vordergrund waren. */
data class DayUsage(
    val day: LocalDate,
    val apps: List<AppUsage>,
) {
    val seconds: Long get() = apps.sumOf { it.seconds }
}

/**
 * Liest die Nutzungsstatistik des Systems aus.
 *
 * Grundlage ist [UsageStatsManager.queryEvents]: das System meldet, wann welche
 * App in den Vordergrund kam und wann sie ihn wieder verließ. Daraus ergeben
 * sich Vordergrundzeit und Anzahl der Aufrufe je App und Tag. Die fertige
 * Tagesaufstellung von `queryAndAggregateUsageStats` wäre bequemer, liefert
 * aber keine sauberen Tagesgrenzen — deshalb hier die Ereignisse selbst.
 *
 * Was hier entsteht, sind Paketnamen und Sekunden. Inhalte, Benachrichtigungen
 * oder Bildschirminhalte liest die App nicht — dafür reicht die Berechtigung
 * auch gar nicht.
 */
class UsageCollector(private val context: Context) {

    /**
     * Hat der Nutzer die Berechtigung „Nutzungsdaten“ erteilt?
     *
     * Die vergibt man nur von Hand in den Systemeinstellungen; abfragen lässt
     * sie sich ausschließlich über den AppOps-Dienst.
     */
    fun hasPermission(): Boolean {
        val dienst = context.getSystemService(Context.APP_OPS_SERVICE) as? AppOpsManager
            ?: return false
        val zustand = dienst.unsafeCheckOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            Process.myUid(),
            context.packageName,
        )
        return zustand == AppOpsManager.MODE_ALLOWED
    }

    /** Die letzten [days] Tage einsammeln, heute zuerst. */
    fun collect(days: Int = STANDARD_TAGE): List<DayUsage> {
        val verwalter = context.getSystemService(Context.USAGE_STATS_SERVICE)
            as? UsageStatsManager ?: return emptyList()
        val zone = ZoneId.systemDefault()
        val heute = LocalDate.now(zone)
        val jetzt = System.currentTimeMillis()

        val ergebnis = mutableListOf<DayUsage>()
        for (versatz in 0 until days) {
            val tag = heute.minusDays(versatz.toLong())
            val beginn = tag.atStartOfDay(zone).toInstant().toEpochMilli()
            val ende = minOf(tag.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli(), jetzt)
            if (ende <= beginn) continue
            val apps = tagesnutzung(verwalter, beginn, ende)
            if (apps.isNotEmpty()) {
                ergebnis.add(DayUsage(tag, apps))
            }
        }
        return ergebnis
    }

    private fun tagesnutzung(
        verwalter: UsageStatsManager,
        beginn: Long,
        ende: Long,
    ): List<AppUsage> {
        val millis = HashMap<String, Long>()
        val aufrufe = HashMap<String, Int>()
        val offen = HashMap<String, Long>()

        val ereignisse = verwalter.queryEvents(beginn, ende)
        val ereignis = UsageEvents.Event()
        while (ereignisse.hasNextEvent()) {
            ereignisse.getNextEvent(ereignis)
            val paket = ereignis.packageName ?: continue
            when (ereignis.eventType) {
                UsageEvents.Event.ACTIVITY_RESUMED -> {
                    // Mehrere Aktivitäten derselben App gelten als ein Aufruf.
                    if (offen.put(paket, ereignis.timeStamp) == null) {
                        aufrufe[paket] = (aufrufe[paket] ?: 0) + 1
                    }
                }

                UsageEvents.Event.ACTIVITY_PAUSED,
                UsageEvents.Event.ACTIVITY_STOPPED,
                -> {
                    val start = offen.remove(paket) ?: continue
                    millis[paket] = (millis[paket] ?: 0) + (ereignis.timeStamp - start)
                }
            }
        }

        // Was am Tagesende (oder gerade jetzt) noch vorn war, zählt bis dahin.
        for ((paket, start) in offen) {
            millis[paket] = (millis[paket] ?: 0) + (ende - start)
        }

        val eigenes = context.packageName
        return millis.entries
            .asSequence()
            .filter { (paket, dauer) -> dauer > 0 && paket != eigenes }
            .map { (paket, dauer) ->
                AppUsage(
                    packageName = paket,
                    label = beschriftung(paket),
                    seconds = dauer / 1000,
                    opens = aufrufe[paket] ?: 0,
                )
            }
            .filter { it.seconds > 0 }
            .sortedByDescending { it.seconds }
            .take(MAX_APPS)
            .toList()
    }

    /**
     * Welche App steht gerade im Vordergrund? ``null``, wenn unbekannt.
     *
     * Wird vor jeder Bildschirm-Aufnahme gefragt (Phase 6), damit gesperrte
     * Apps gar nicht erst aufgenommen werden.
     */
    fun currentForegroundPackage(): String? {
        val verwalter = context.getSystemService(Context.USAGE_STATS_SERVICE)
            as? UsageStatsManager ?: return null
        val jetzt = System.currentTimeMillis()
        val ereignisse = verwalter.queryEvents(jetzt - VORDERGRUND_FENSTER, jetzt)
        val ereignis = UsageEvents.Event()
        var letztes: String? = null
        while (ereignisse.hasNextEvent()) {
            ereignisse.getNextEvent(ereignis)
            if (ereignis.eventType == UsageEvents.Event.ACTIVITY_RESUMED) {
                letztes = ereignis.packageName
            }
        }
        return letztes
    }

    /** Anzeigename einer App; unbekannt bleibt unbekannt. */
    fun beschriftung(paket: String): String? = try {
        val verwaltung = context.packageManager
        verwaltung.getApplicationLabel(verwaltung.getApplicationInfo(paket, 0)).toString()
    } catch (fehlt: PackageManager.NameNotFoundException) {
        null
    }

    companion object {
        /** So viele Tage schickt ein Sync mit — deckt auch ein paar Tage ohne WLAN ab. */
        const val STANDARD_TAGE = 7

        /** Mehr als das nimmt die Gegenstelle ohnehin nicht an. */
        private const val MAX_APPS = 200

        /** So weit wird für den Vordergrund zurückgeschaut (10 Minuten). */
        private const val VORDERGRUND_FENSTER = 10 * 60 * 1000L
    }
}
