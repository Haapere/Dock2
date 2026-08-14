package de.fokusradar.begleiter

import android.content.Context
import android.util.Log
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.TimeUnit

/**
 * Täglicher Sync im Hintergrund.
 *
 * WorkManager entscheidet selbst, wann genau er läuft — das schont den Akku und
 * ist genau richtig, denn auf eine Minute kommt es hier nicht an. Ohne Netz
 * läuft er gar nicht erst los.
 */
class SyncWorker(
    context: Context,
    parameter: WorkerParameters,
) : Worker(context, parameter) {

    override fun doWork(): Result {
        val einstellungen = Settings(applicationContext)
        if (!einstellungen.ready) {
            return Result.success()  // noch nicht eingerichtet — nichts zu tun
        }
        val sammler = UsageCollector(applicationContext)
        if (!sammler.hasPermission()) {
            einstellungen.lastResult = "Sync ausgelassen: Berechtigung fehlt."
            return Result.success()  // erneutes Versuchen hilft hier nicht
        }

        return try {
            val antwort = SyncClient(einstellungen).send(sammler.collect())
            einstellungen.lastResult = "${zeitstempel()} — ${antwort.meldung()}"
            if (antwort.ok) Result.success() else Result.retry()
        } catch (fehler: Exception) {
            Log.w(TAG, "Hintergrund-Sync fehlgeschlagen", fehler)
            einstellungen.lastResult = "${zeitstempel()} — ${fehler.message}"
            Result.retry()
        }
    }

    private fun zeitstempel(): String =
        LocalDateTime.now().format(DateTimeFormatter.ofPattern("dd.MM. HH:mm"))

    companion object {
        private const val TAG = "FokusRadarWorker"
        private const val NAME = "taeglicher-sync"

        /** Täglichen Sync ein- oder ausschalten. */
        fun schedule(context: Context, aktiv: Boolean) {
            val verwalter = WorkManager.getInstance(context.applicationContext)
            if (!aktiv) {
                verwalter.cancelUniqueWork(NAME)
                return
            }
            val auftrag = PeriodicWorkRequestBuilder<SyncWorker>(1, TimeUnit.DAYS)
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build(),
                )
                .build()
            verwalter.enqueueUniquePeriodicWork(
                NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                auftrag,
            )
        }
    }
}
