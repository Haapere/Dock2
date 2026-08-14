package de.fokusradar.begleiter

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.util.DisplayMetrics
import android.util.Log
import android.view.WindowManager
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors
import kotlin.math.max

/**
 * Nimmt in großen Abständen ein Bild des Bildschirms auf und schickt es an den
 * Rechner im Heimnetz.
 *
 * Der Dienst läuft im Vordergrund und **muss** eine Benachrichtigung zeigen —
 * das ist Absicht: solange aufgenommen wird, ist das sichtbar, und ein Tippen
 * auf die Benachrichtigung beendet es sofort. Android verlangt außerdem vor
 * jedem Start die ausdrückliche Zustimmung des Nutzers; die gilt nur für diese
 * eine Sitzung und überlebt keinen Neustart.
 *
 * Was mit dem Bild passiert, entscheidet der Rechner: dort läuft die
 * Texterkennung, dort greift die Ausschlussliste, dort wird das Bild wieder
 * gelöscht. Ins Internet geht es nie.
 */
class ScreenCaptureService : Service() {

    private lateinit var einstellungen: Settings
    private lateinit var sammler: UsageCollector

    private var projektion: MediaProjection? = null
    private var anzeige: VirtualDisplay? = null
    private var leser: ImageReader? = null

    private val hintergrund = Executors.newSingleThreadExecutor()
    private lateinit var aufnahmeThread: HandlerThread
    private lateinit var takt: Handler

    /** Beendet den Dienst, wenn der Nutzer die Freigabe zurückzieht. */
    private val rueckzug = object : MediaProjection.Callback() {
        override fun onStop() {
            stopSelf()
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        einstellungen = Settings(this)
        sammler = UsageCollector(this)
        aufnahmeThread = HandlerThread("fokusradar-aufnahme").apply { start() }
        takt = Handler(aufnahmeThread.looper)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == AKTION_STOPP) {
            stopSelf()
            return START_NOT_STICKY
        }

        // Erst die Benachrichtigung, dann die Projektion: Android verlangt das
        // in dieser Reihenfolge, sonst wird der Dienst sofort beendet.
        starteImVordergrund()

        if (projektion != null) {
            // Schon am Laufen. Ein zweiter Start würde eine zweite Projektion
            // anlegen und den Takt verdoppeln — also einfach weitermachen.
            Log.i(TAG, "Läuft bereits — zweiter Start wird übergangen")
            return START_NOT_STICKY
        }

        val ergebnisCode = intent?.getIntExtra(EXTRA_CODE, 0) ?: 0
        val daten: Intent? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            intent?.getParcelableExtra(EXTRA_DATEN, Intent::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent?.getParcelableExtra(EXTRA_DATEN)
        }
        if (daten == null) {
            Log.w(TAG, "Ohne Freigabe gestartet — Dienst wird beendet")
            stopSelf()
            return START_NOT_STICKY
        }

        val verwalter = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        try {
            projektion = verwalter.getMediaProjection(ergebnisCode, daten).also {
                it.registerCallback(rueckzug, takt)
            }
            richteAufnahmeEin()
        } catch (fehler: Exception) {
            // Eine abgelaufene oder schon verbrauchte Freigabe darf den Dienst
            // nicht abstürzen lassen — sie beendet ihn nur.
            Log.w(TAG, "Freigabe nicht nutzbar", fehler)
            einstellungen.lastResult = "Bildschirm-Aufnahme nicht gestartet: ${fehler.message}"
            stopSelf()
            return START_NOT_STICKY
        }
        takt.post(schleife)
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        takt.removeCallbacksAndMessages(null)
        anzeige?.release()
        leser?.close()
        projektion?.unregisterCallback(rueckzug)
        projektion?.stop()
        aufnahmeThread.quitSafely()
        hintergrund.shutdown()
        einstellungen.screenEnabled = false
        super.onDestroy()
    }

    // -- Aufnahme ------------------------------------------------------------

    private fun richteAufnahmeEin() {
        val masse = DisplayMetrics()
        val fenster = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        @Suppress("DEPRECATION")
        fenster.defaultDisplay.getRealMetrics(masse)

        leser = ImageReader.newInstance(
            masse.widthPixels,
            masse.heightPixels,
            PixelFormat.RGBA_8888,
            2,
        )
        anzeige = projektion?.createVirtualDisplay(
            "fokusradar",
            masse.widthPixels,
            masse.heightPixels,
            masse.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            leser?.surface,
            null,
            takt,
        )
    }

    /** Der Takt: aufnehmen, senden, warten. */
    private val schleife = object : Runnable {
        override fun run() {
            val wartezeit = try {
                if (nimmAufUndSende()) einstellungen.screenIntervalMinutes * 60_000L
                else NACHFASSEN
            } catch (fehler: Exception) {
                Log.w(TAG, "Aufnahme fehlgeschlagen", fehler)
                einstellungen.screenIntervalMinutes * 60_000L
            }
            takt.postDelayed(this, wartezeit)
        }
    }

    /**
     * Eine Aufnahme machen und wegschicken.
     *
     * Rückgabe ``false`` heißt nur: es lag noch kein Bild bereit. Das ist gleich
     * nach dem Start der Normalfall — dann wird kurz darauf noch einmal
     * nachgefasst statt bis zum nächsten regulären Takt zu warten, der eine
     * Stunde entfernt sein kann.
     */
    private fun nimmAufUndSende(): Boolean {
        val paket = sammler.currentForegroundPackage()
        if (paket != null && einstellungen.isBlocked(paket)) {
            // Gesperrte App im Vordergrund: gar nicht erst aufnehmen.
            Log.i(TAG, "Aufnahme ausgelassen (gesperrte App)")
            return true
        }

        val bild = leser?.acquireLatestImage() ?: return false
        val png = try {
            alsPng(bild)
        } finally {
            bild.close()
        }
        if (png == null) return false
        if (!einstellungen.ready) return true  // nicht eingerichtet, nichts zu tun

        val name = paket?.let { sammler.beschriftung(it) }
        hintergrund.execute {
            val antwort = SyncClient(einstellungen)
                .sendScreen(png, paket ?: "unbekannt", name)
            einstellungen.lastResult = antwort.meldung()
        }
        return true
    }

    /** Bild aus dem [ImageReader] in ein PNG wandeln, auf Maß gebracht. */
    private fun alsPng(bild: android.media.Image): ByteArray? {
        val ebene = bild.planes.firstOrNull() ?: return null
        // Der Puffer ist zeilenweise aufgefüllt; die Zusatzspalten fallen unten weg.
        val pixelAbstand = ebene.pixelStride
        val zeilenAbstand = ebene.rowStride
        val ueberhang = zeilenAbstand - pixelAbstand * bild.width

        val roh = Bitmap.createBitmap(
            bild.width + ueberhang / pixelAbstand,
            bild.height,
            Bitmap.Config.ARGB_8888,
        )
        roh.copyPixelsFromBuffer(ebene.buffer)
        val beschnitten = Bitmap.createBitmap(roh, 0, 0, bild.width, bild.height)
        if (beschnitten != roh) roh.recycle()

        val verkleinert = verkleinere(beschnitten)
        val strom = ByteArrayOutputStream()
        verkleinert.compress(Bitmap.CompressFormat.PNG, 100, strom)
        if (verkleinert != beschnitten) verkleinert.recycle()
        beschnitten.recycle()
        return strom.toByteArray()
    }

    /** Auf die lange Kante begrenzen — spart Bandbreite, reicht für Texterkennung. */
    private fun verkleinere(bild: Bitmap): Bitmap {
        val laengsteKante = max(bild.width, bild.height)
        if (laengsteKante <= MAX_KANTE) return bild
        val faktor = MAX_KANTE.toFloat() / laengsteKante
        return Bitmap.createScaledBitmap(
            bild,
            (bild.width * faktor).toInt(),
            (bild.height * faktor).toInt(),
            true,
        )
    }

    // -- Benachrichtigung ----------------------------------------------------

    private fun starteImVordergrund() {
        val verwalter = getSystemService(NotificationManager::class.java)
        verwalter.createNotificationChannel(
            NotificationChannel(
                KANAL,
                getString(R.string.kanal_aufnahme),
                NotificationManager.IMPORTANCE_LOW,
            )
        )
        val stopp = PendingIntent.getService(
            this,
            0,
            Intent(this, ScreenCaptureService::class.java).setAction(AKTION_STOPP),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val meldung = Notification.Builder(this, KANAL)
            .setContentTitle(getString(R.string.aufnahme_laeuft))
            .setContentText(getString(R.string.aufnahme_hinweis))
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setOngoing(true)
            .setContentIntent(stopp)
            .addAction(
                Notification.Action.Builder(
                    null, getString(R.string.aufnahme_beenden), stopp
                ).build()
            )
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                MELDUNG_ID,
                meldung,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION,
            )
        } else {
            @Suppress("DEPRECATION")
            startForeground(MELDUNG_ID, meldung)
        }
    }

    companion object {
        private const val TAG = "FokusRadarScreen"
        private const val KANAL = "aufnahme"
        private const val MELDUNG_ID = 4711

        /** Längste Kante der übertragenen Aufnahme in Pixeln. */
        private const val MAX_KANTE = 1280

        /** Abstand, wenn noch kein Bild bereitlag (gleich nach dem Start). */
        private const val NACHFASSEN = 5_000L

        const val AKTION_STOPP = "de.fokusradar.begleiter.STOPP"
        const val EXTRA_CODE = "ergebnis_code"
        const val EXTRA_DATEN = "ergebnis_daten"

        /** Dienst mit der Freigabe des Nutzers starten. */
        fun start(context: Context, ergebnisCode: Int, daten: Intent) {
            val absicht = Intent(context, ScreenCaptureService::class.java)
                .putExtra(EXTRA_CODE, ergebnisCode)
                .putExtra(EXTRA_DATEN, daten)
            context.startForegroundService(absicht)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, ScreenCaptureService::class.java))
        }
    }
}
