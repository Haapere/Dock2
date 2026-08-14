package de.fokusradar.begleiter

import android.content.Intent
import android.os.Bundle
import android.provider.Settings as SystemSettings
import androidx.appcompat.app.AppCompatActivity
import de.fokusradar.begleiter.databinding.ActivityMainBinding
import java.util.concurrent.Executors

/**
 * Die einzige Ansicht der App: Zugangsdaten eintragen, Berechtigung erteilen,
 * senden — und sehen, was heute zusammengekommen ist.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var oberflaeche: ActivityMainBinding
    private lateinit var einstellungen: Settings
    private lateinit var sammler: UsageCollector

    // Netzwerk und das Auslesen der Statistik gehören nicht in den Hauptthread.
    private val hintergrund = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        oberflaeche = ActivityMainBinding.inflate(layoutInflater)
        setContentView(oberflaeche.root)

        einstellungen = Settings(this)
        sammler = UsageCollector(this)

        oberflaeche.feldAdresse.setText(einstellungen.serverUrl)
        oberflaeche.feldToken.setText(einstellungen.token)
        oberflaeche.feldGeraet.setText(einstellungen.deviceName)
        oberflaeche.schalterAutomatisch.isChecked = einstellungen.autoSync

        oberflaeche.knopfSpeichern.setOnClickListener { speichern() }
        oberflaeche.knopfBerechtigung.setOnClickListener {
            startActivity(Intent(SystemSettings.ACTION_USAGE_ACCESS_SETTINGS))
        }
        oberflaeche.knopfPruefen.setOnClickListener { pruefen() }
        oberflaeche.knopfSenden.setOnClickListener { senden() }
    }

    override fun onResume() {
        super.onResume()
        // Nach dem Ausflug in die Systemeinstellungen kann die Berechtigung
        // plötzlich da sein — also jedes Mal frisch nachsehen.
        zeigeZustand()
        vorschauLaden()
    }

    override fun onDestroy() {
        hintergrund.shutdown()
        super.onDestroy()
    }

    // -- Aktionen ------------------------------------------------------------

    private fun speichern() {
        einstellungen.serverUrl = oberflaeche.feldAdresse.text.toString()
        einstellungen.token = oberflaeche.feldToken.text.toString()
        einstellungen.deviceName = oberflaeche.feldGeraet.text.toString()
        einstellungen.autoSync = oberflaeche.schalterAutomatisch.isChecked
        SyncWorker.schedule(this, einstellungen.autoSync)
        melde(getString(R.string.gespeichert))
    }

    private fun pruefen() {
        if (!bereit()) return
        speichern()
        melde(getString(R.string.laeuft))
        imHintergrund { SyncClient(einstellungen).status().meldung() }
    }

    private fun senden() {
        if (!bereit()) return
        if (!sammler.hasPermission()) {
            melde(getString(R.string.berechtigung_fehlt))
            return
        }
        speichern()
        melde(getString(R.string.laeuft))
        imHintergrund {
            val tage = sammler.collect()
            val meldung = SyncClient(einstellungen).send(tage).meldung()
            einstellungen.lastResult = meldung
            meldung
        }
    }

    private fun bereit(): Boolean {
        val vollstaendig = oberflaeche.feldAdresse.text.isNotBlank() &&
            oberflaeche.feldToken.text.isNotBlank()
        if (!vollstaendig) {
            melde(getString(R.string.unvollstaendig))
        }
        return vollstaendig
    }

    // -- Anzeige -------------------------------------------------------------

    private fun zeigeZustand() {
        val zustand = if (sammler.hasPermission()) {
            getString(R.string.berechtigung_da)
        } else {
            getString(R.string.berechtigung_fehlt)
        }
        val letztes = einstellungen.lastResult
        melde(if (letztes.isBlank()) zustand else "$zustand\n$letztes")
    }

    /** Die heutigen Zahlen anzeigen — dieselben, die auch gesendet würden. */
    private fun vorschauLaden() {
        if (!sammler.hasPermission()) {
            oberflaeche.feldVorschau.text = ""
            return
        }
        hintergrund.execute {
            val heute = sammler.collect(days = 1).firstOrNull()
            val text = if (heute == null || heute.apps.isEmpty()) {
                "Noch keine Nutzung erfasst."
            } else {
                buildString {
                    append("Gesamt: ${dauer(heute.seconds)}\n\n")
                    for (app in heute.apps.take(10)) {
                        val name = (app.label ?: app.packageName).take(22)
                        append(name.padEnd(24))
                        append(dauer(app.seconds).padStart(9))
                        append("  ${app.opens}×\n")
                    }
                }
            }
            runOnUiThread { oberflaeche.feldVorschau.text = text }
        }
    }

    private fun imHintergrund(arbeit: () -> String) {
        hintergrund.execute {
            val meldung = try {
                arbeit()
            } catch (fehler: Exception) {
                fehler.message ?: "Unbekannter Fehler"
            }
            runOnUiThread {
                melde(meldung)
                vorschauLaden()
            }
        }
    }

    private fun melde(text: String) {
        oberflaeche.feldMeldung.text = text
    }

    private fun dauer(sekunden: Long): String {
        val stunden = sekunden / 3600
        val minuten = (sekunden % 3600) / 60
        return if (stunden > 0) "${stunden}h ${minuten}min" else "${minuten}min"
    }
}
