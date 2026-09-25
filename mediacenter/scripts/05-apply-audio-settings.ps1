<#
.SYNOPSIS
    Setzt Kodis Audio- und Passthrough-Einstellungen ueber JSON-RPC.

.DESCRIPTION
    Kodi muss dafuer LAUFEN und der Webserver aktiv sein (Skript 04).
    Der Umweg ueber JSON-RPC statt direktem Schreiben in guisettings.xml ist
    Absicht: Kodi uebernimmt die Werte sofort, validiert sie und schreibt sie
    beim naechsten Beenden selbst korrekt weg.

    Enum-Werte (z. B. "Best Match", "Immer") sind zwischen Kodi-Versionen und
    Sprachen nicht stabil. Das Skript liest deshalb die von Kodi gemeldeten
    Options-Labels aus und sucht den passenden Wert zur Laufzeit.

    Gesetzt wird das Profil "Musik als PCM + Film mit Passthrough":
      * Ausgabegeraet : WASAPI (Pflicht - DirectSound kann kein Exclusive)
      * Konfiguration : Best Match  -> Samplerate folgt dem Quellmaterial,
                        also kein Resampling von 44,1 kHz auf 48 kHz
      * Passthrough   : an, inklusive Dolby Digital/Plus, DTS, TrueHD, DTS-HD
      * Transcoding   : aus (nur fuer optisch/SPDIF sinnvoll, ueber HDMI schaedlich)
      * Geraet wachhalten: immer  -> keine abgeschnittenen Titelanfaenge
      * GUI-Klaenge   : nie       -> stoert sonst den Passthrough-Kanal
      * "An Anzeige angleichen": aus -> resampelt sonst und zerstoert Bit-Perfect

.PARAMETER ReceiverName
    Teilstring des AV-Receivers, wie Windows ihn meldet, z. B. "Denon".
    Ohne Angabe waehlt das Skript das erste WASAPI-Geraet, das nach HDMI
    oder Receiver aussieht, und zeigt alle Alternativen an.

.PARAMETER DryRun
    Nichts aendern, nur anzeigen, was gesetzt wuerde.

.PARAMETER ShowDevices
    Nur die verfuegbaren Audiogeraete auflisten und beenden.

.EXAMPLE
    .\05-apply-audio-settings.ps1 -ShowDevices

.EXAMPLE
    .\05-apply-audio-settings.ps1 -ReceiverName "Denon"

.NOTES
    Nach dem Lauf einmal Kodi beenden und neu starten, damit die
    Audio-Engine sauber mit den neuen Werten initialisiert.
#>

[CmdletBinding()]
param(
    [string] $ReceiverName,
    [switch] $DryRun,
    [switch] $ShowDevices,
    [string] $KodiHost = 'localhost',
    [int]    $Port,
    [string] $User,
    [string] $Password
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step  { param([string]$m) Write-Host "`n[*] $m" -ForegroundColor Cyan }
function Write-Ok    { param([string]$m) Write-Host "    [ok]   $m" -ForegroundColor Green }
function Write-Warn2 { param([string]$m) Write-Host "    [warn] $m" -ForegroundColor Yellow }
function Write-Fail  { param([string]$m) Write-Host "    [fehl] $m" -ForegroundColor Red }
function Write-Skip  { param([string]$m) Write-Host "    [--]   $m" -ForegroundColor DarkGray }

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir   = Split-Path $scriptDir -Parent
$modPath   = Join-Path $rootDir 'tools\KodiRpc.psm1'
$cfgPath   = Join-Path $rootDir 'config\kodi-settings.json'

if (-not (Test-Path $modPath)) { throw "Modul fehlt: $modPath" }
if (-not (Test-Path $cfgPath)) { throw "Konfiguration fehlt: $cfgPath" }

Import-Module $modPath -Force

$rpc = @{ KodiHost = $KodiHost }
if ($Port)     { $rpc['Port']     = $Port }
if ($User)     { $rpc['User']     = $User }
if ($Password) { $rpc['Password'] = $Password }

Write-Host ""
Write-Host "=== Kodi Audio & Passthrough ===" -ForegroundColor White

# ---------------------------------------------------------------------------
# Verbindung
# ---------------------------------------------------------------------------
Write-Step 'Verbinde mit Kodi'
if (-not (Test-KodiConnection @rpc -RetrySeconds 30)) {
    Write-Fail 'Keine Verbindung zu Kodi.'
    Write-Warn2 'Pruefen: Laeuft Kodi? Wurde 04-deploy-kodi-config.ps1 ausgefuehrt und Kodi danach neu gestartet?'
    Write-Warn2 'Zugangsdaten stehen in %ProgramData%\KodiMediacenter\fernsteuerung.txt'
    return
}
Write-Ok 'Verbindung steht'

$ver = Invoke-KodiRpc -Method 'Application.GetProperties' -Params @{ properties = @('version') } @rpc
Write-Ok "Kodi $($ver.version.major).$($ver.version.minor) ($($ver.version.tag))"

# ---------------------------------------------------------------------------
# Einstellungen einlesen
# ---------------------------------------------------------------------------
Write-Step 'Lese verfuegbare Einstellungen (Ebene: Experte)'
$all = Get-KodiSettings -Level expert @rpc
Write-Ok "$($all.Count) Einstellungen gelesen"

function Find-Setting {
    param([string]$Id)
    return $all | Where-Object { $_.id -eq $Id } | Select-Object -First 1
}

function Get-OptionList {
    param($Setting)
    if (-not $Setting) { return @() }
    if ($Setting.PSObject.Properties.Name -notcontains 'options') { return @() }
    if (-not $Setting.options) { return @() }
    return @($Setting.options)
}

# ---------------------------------------------------------------------------
# Audiogeraet
# ---------------------------------------------------------------------------
$devSetting = Find-Setting 'audiooutput.audiodevice'
$devices    = Get-OptionList $devSetting

if ($ShowDevices) {
    Write-Host ''
    Write-Host 'Von Kodi gemeldete Audiogeraete:' -ForegroundColor White
    if (-not $devices) {
        Write-Warn2 'Kodi meldet keine Geraeteliste. Ist der AV-Receiver eingeschaltet und per HDMI verbunden?'
    }
    $i = 0
    foreach ($d in $devices) {
        $i++
        $mark = if ($devSetting.value -eq $d.value) { '  <- aktuell' } else { '' }
        Write-Host ("  {0,2}. {1}{2}" -f $i, $d.label, $mark)
    }
    Write-Host ''
    Write-Host 'Aufruf mit passendem Teilstring, z. B.:  .\05-apply-audio-settings.ps1 -ReceiverName "Denon"'
    Write-Host ''
    return
}

Write-Step 'Audioausgabegeraet'

if (-not $devices) {
    Write-Warn2 'Kodi meldet keine Geraeteliste - Geraetewahl wird uebersprungen.'
    Write-Warn2 'Haeufigste Ursache: AV-Receiver aus oder HDMI nicht verbunden. Siehe docs/06-troubleshooting.md'
} else {
    # WASAPI ist Pflicht: nur darueber sind Exclusive Mode und Passthrough moeglich
    $wasapi = @($devices | Where-Object { $_.label -match '(?i)wasapi' })

    if (-not $wasapi) {
        Write-Warn2 'Kein WASAPI-Geraet gefunden - Kodi bietet nur DirectSound an.'
        Write-Warn2 'Damit sind weder Exclusive Mode noch Passthrough moeglich.'
        Write-Warn2 'Pruefen: Ist der Receiver eingeschaltet? Wurde Kodi nach dem Anschliessen neu gestartet?'
    } else {
        $chosen = $null

        if ($ReceiverName) {
            $chosen = $wasapi | Where-Object { $_.label -like "*$ReceiverName*" } | Select-Object -First 1
            if (-not $chosen) {
                Write-Warn2 "Kein WASAPI-Geraet passt auf '$ReceiverName'. Verfuegbar:"
                foreach ($d in $wasapi) { Write-Host "      - $($d.label)" -ForegroundColor DarkGray }
            }
        }

        if (-not $chosen) {
            # Automatik: HDMI/Receiver-typische Namen bevorzugen
            $chosen = $wasapi | Where-Object {
                $_.label -match '(?i)hdmi|receiver|avr|denon|marantz|onkyo|pioneer|yamaha|sony|harman'
            } | Select-Object -First 1
        }
        if (-not $chosen) { $chosen = $wasapi | Select-Object -First 1 }

        if ($DryRun) {
            Write-Skip "wuerde setzen: audiooutput.audiodevice = $($chosen.label)"
        } else {
            if (Set-KodiSetting -Setting 'audiooutput.audiodevice' -Value $chosen.value @rpc) {
                Write-Ok "Geraet: $($chosen.label)"
            } else {
                Write-Fail "Geraet konnte nicht gesetzt werden: $($chosen.label)"
            }
        }

        if ($wasapi.Count -gt 1) {
            Write-Host '      Weitere WASAPI-Geraete:' -ForegroundColor DarkGray
            foreach ($d in $wasapi) {
                if ($d.value -ne $chosen.value) { Write-Host "        - $($d.label)" -ForegroundColor DarkGray }
            }
        }
    }
}

# ---------------------------------------------------------------------------
# Enum-Einstellungen ueber Labels aufloesen
# ---------------------------------------------------------------------------
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json

Write-Step 'Auswahl-Einstellungen (Label-basiert aufgeloest)'

foreach ($prop in $cfg.enumByLabel.PSObject.Properties) {
    if ($prop.Name -eq '_comment') { continue }

    $id         = $prop.Name
    $candidates = @($prop.Value)
    $setting    = Find-Setting $id

    if (-not $setting) {
        Write-Skip "$id - in dieser Kodi-Version nicht vorhanden"
        continue
    }

    $options = Get-OptionList $setting
    if (-not $options) {
        Write-Skip "$id - keine Optionsliste verfuegbar"
        continue
    }

    $match = $null
    foreach ($cand in $candidates) {
        $match = $options | Where-Object { $_.label -and ($_.label.Trim() -eq $cand) } | Select-Object -First 1
        if ($match) { break }
        # zweiter Versuch: Teilstring, falls Kodi das Label anders formatiert
        $match = $options | Where-Object { $_.label -and ($_.label -like "*$cand*") } | Select-Object -First 1
        if ($match) { break }
    }

    if (-not $match) {
        Write-Warn2 "$id - keines der erwarteten Labels gefunden. Verfuegbar:"
        foreach ($o in $options) { Write-Host "        - $($o.label)" -ForegroundColor DarkGray }
        continue
    }

    if ($DryRun) {
        Write-Skip "wuerde setzen: $id = $($match.label)"
    } else {
        try {
            if (Set-KodiSetting -Setting $id -Value $match.value @rpc) {
                Write-Ok "$id = $($match.label)"
            } else {
                Write-Warn2 "$id = $($match.label) wurde von Kodi abgelehnt (evtl. durch eine andere Einstellung gesperrt)"
            }
        } catch {
            Write-Fail "$id : $($_.Exception.Message)"
        }
    }
}

# ---------------------------------------------------------------------------
# Boolesche und numerische Einstellungen
# ---------------------------------------------------------------------------
Write-Step 'Schalter und Zahlenwerte'

$applyGroups = @(
    @{ Name = 'boolean'; Convert = { param($v) [bool]$v } },
    @{ Name = 'integer'; Convert = { param($v) [int]$v } },
    @{ Name = 'string';  Convert = { param($v) [string]$v } }
)

foreach ($group in $applyGroups) {
    $section = $cfg.($group.Name)
    if (-not $section) { continue }

    foreach ($prop in $section.PSObject.Properties) {
        if ($prop.Name -eq '_comment') { continue }

        $id = $prop.Name

        # Wurde oben bereits label-basiert gesetzt? Dann nicht ueberschreiben.
        if ($cfg.enumByLabel.PSObject.Properties.Name -contains $id) { continue }

        $setting = Find-Setting $id
        if (-not $setting) {
            Write-Skip "$id - in dieser Kodi-Version nicht vorhanden"
            continue
        }

        $value = & $group.Convert $prop.Value

        if ($DryRun) {
            Write-Skip "wuerde setzen: $id = $value"
            continue
        }

        try {
            if (Set-KodiSetting -Setting $id -Value $value @rpc) {
                Write-Ok "$id = $value"
            } else {
                Write-Warn2 "$id = $value abgelehnt (Wert ausserhalb des Bereichs oder Einstellung gesperrt)"
            }
        } catch {
            Write-Fail "$id : $($_.Exception.Message)"
        }
    }
}

# ---------------------------------------------------------------------------
# Kontrolle
# ---------------------------------------------------------------------------
Write-Step 'Kontrolle der wichtigsten Werte'

$check = @(
    'audiooutput.audiodevice',
    'audiooutput.config',
    'audiooutput.channels',
    'audiooutput.passthrough',
    'audiooutput.ac3passthrough',
    'audiooutput.dtspassthrough',
    'audiooutput.truehdpassthrough',
    'audiooutput.dtshdpassthrough',
    'audiooutput.streamsilence',
    'audiooutput.guisoundmode',
    'videoplayer.usedisplayasclock'
)

foreach ($id in $check) {
    try {
        $v = Invoke-KodiRpc -Method 'Settings.GetSettingValue' -Params @{ setting = $id } @rpc
        Write-Host ("    {0,-32} = {1}" -f $id, $v.value)
    } catch {
        Write-Skip "$id - nicht lesbar"
    }
}

Write-Host ''
if ($DryRun) {
    Write-Warn2 'DryRun - es wurde nichts geaendert.'
} else {
    Write-Host 'Fertig. Bitte Kodi einmal beenden und neu starten,' -ForegroundColor White
    Write-Host 'damit die Audio-Engine mit den neuen Werten initialisiert.' -ForegroundColor White
    Write-Host ''
    Write-Host 'Danach pruefen: docs/02-passthrough-matrix.md, Abschnitt "Abnahme".' -ForegroundColor White
}
Write-Host ''
