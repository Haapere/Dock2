<#
.SYNOPSIS
    Master-Installer: richtet den Mini-PC in einem Durchlauf als
    Hi-Res-Mediencenter ein.

.DESCRIPTION
    Fuehrt die Teilskripte in der richtigen Reihenfolge aus und haelt an den
    Stellen an, an denen Kodi beendet bzw. gestartet sein muss.

    Ablauf:
      1. 01-windows-audio.ps1        Exklusivmodus, Klangeffekte aus
      2. 02-windows-tuning.ps1       Energie, Netzwerk, Firewall, Autostart
      3. 03-install-kodi.ps1         Kodi installieren, Profil anlegen
      4. 04-deploy-kodi-config.ps1   advancedsettings.xml, Webserver
         -> Kodi wird gestartet
      5. 05-apply-audio-settings.ps1 Audio und Passthrough per JSON-RPC
      6. 06-install-addons.ps1       Favoriten, Streams, Add-on-Pakete
      7. healthcheck.ps1             Abschlusspruefung

.PARAMETER ReceiverName
    Teilstring des AV-Receivers, z. B. "Denon". Wird an die Audio-Skripte
    durchgereicht. Ohne Angabe wird automatisch gesucht.

.PARAMETER WebPassword
    Passwort fuer die Fernsteuerung. Ohne Angabe wird eines erzeugt.

.PARAMETER SkipSteps
    Schrittnummern, die uebersprungen werden sollen, z. B. -SkipSteps 3,6

.EXAMPLE
    .\install.ps1

.EXAMPLE
    .\install.ps1 -ReceiverName "Denon" -WebPassword "GutesPasswort123"

.NOTES
    PowerShell als Administrator starten. Vorher einmal:
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#>

[CmdletBinding()]
param(
    [string] $ReceiverName,
    [string] $WebPassword,
    [int[]]  $SkipSteps = @()
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$rootDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Join-Path $rootDir 'scripts'
$toolsDir   = Join-Path $rootDir 'tools'

function Write-Banner {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 64) -ForegroundColor White
    Write-Host " $Text" -ForegroundColor White
    Write-Host ("=" * 64) -ForegroundColor White
}

function Assert-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Bitte PowerShell als Administrator starten (Rechtsklick -> Als Administrator ausfuehren)."
    }
}

function Invoke-Step {
    param(
        [int]       $Number,
        [string]    $Title,
        [string]    $Script,
        [hashtable] $Arguments = @{}
    )

    if ($SkipSteps -contains $Number) {
        Write-Host "`n[$Number] $Title - uebersprungen (-SkipSteps)" -ForegroundColor DarkGray
        return $true
    }

    Write-Banner "Schritt $Number von 7: $Title"

    if (-not (Test-Path $Script)) {
        Write-Host "  Skript fehlt: $Script" -ForegroundColor Red
        return $false
    }

    try {
        & $Script @Arguments
        return $true
    } catch {
        Write-Host ""
        Write-Host "  Schritt $Number ist fehlgeschlagen:" -ForegroundColor Red
        Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
        Write-Host ""

        $answer = Read-Host '  Trotzdem weitermachen? (j/n)'
        return ($answer -match '^(j|y)')
    }
}

function Stop-KodiIfRunning {
    $p = Get-Process -Name kodi -ErrorAction SilentlyContinue
    if (-not $p) { return }

    Write-Host "`n  Kodi laeuft und muss fuer den naechsten Schritt beendet werden." -ForegroundColor Yellow
    Read-Host '  Kodi bitte beenden, dann Enter druecken' | Out-Null

    $p = Get-Process -Name kodi -ErrorAction SilentlyContinue
    if ($p) {
        Write-Host '  Kodi laeuft noch - beende es jetzt.' -ForegroundColor Yellow
        try {
            $null = $p.CloseMainWindow()
            if (-not $p.WaitForExit(20000)) { Stop-Process -Id $p.Id -Force }
        } catch {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 3
    }
}

function Start-Kodi {
    $candidates = @(
        "$env:ProgramFiles\Kodi\kodi.exe",
        "${env:ProgramFiles(x86)}\Kodi\kodi.exe",
        "$env:LOCALAPPDATA\Programs\Kodi\kodi.exe"
    )
    $exe = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $exe) {
        Write-Host '  kodi.exe nicht gefunden - bitte Kodi von Hand starten.' -ForegroundColor Yellow
        Read-Host '  Enter, wenn Kodi laeuft' | Out-Null
        return
    }

    if (Get-Process -Name kodi -ErrorAction SilentlyContinue) { return }

    Write-Host "  Starte Kodi ..." -ForegroundColor DarkGray
    Start-Process -FilePath $exe | Out-Null
    Start-Sleep -Seconds 12
}

# ===========================================================================
Assert-Admin

Write-Banner 'Hi-Res-Mediencenter - Einrichtung'
Write-Host @"
  Zielsystem : Windows 11 Mini-PC am AV-Receiver (HDMI)
  Ergebnis   : Kodi mit WASAPI-Exklusivmodus, Passthrough fuer Film-Tonformate,
               Fernsteuerung per Yatse/Kore, FLAC-Radio ohne Add-on-Abhaengigkeit

  Der Ablauf dauert je nach Internetverbindung 10 bis 25 Minuten.
  An zwei Stellen wird eine Eingabe gebraucht (Kodi beenden / starten).
"@

$go = Read-Host "`n  Jetzt starten? (j/n)"
if ($go -notmatch '^(j|y)') { Write-Host '  Abgebrochen.'; return }

$results = [ordered]@{}

# --- 1 ---------------------------------------------------------------------
$args1 = @{}
if ($ReceiverName) { $args1['DeviceFilter'] = $ReceiverName } else { $args1['All'] = $true }
$results['1 Windows-Audio'] = Invoke-Step -Number 1 -Title 'Windows-Audio (Exklusivmodus)' `
    -Script (Join-Path $scriptsDir '01-windows-audio.ps1') -Arguments $args1

# --- 2 ---------------------------------------------------------------------
# Autostart erst nach der Kodi-Installation sinnvoll, daher hier ueberspringen
$results['2 Windows-Tuning'] = Invoke-Step -Number 2 -Title 'Windows-Tuning (Energie, Netz, Firewall)' `
    -Script (Join-Path $scriptsDir '02-windows-tuning.ps1') -Arguments @{ SkipAutostart = $true }

# --- 3 ---------------------------------------------------------------------
$results['3 Kodi-Installation'] = Invoke-Step -Number 3 -Title 'Kodi installieren' `
    -Script (Join-Path $scriptsDir '03-install-kodi.ps1')

# Autostart jetzt nachholen, da kodi.exe nun existiert
if ($SkipSteps -notcontains 2 -and $SkipSteps -notcontains 3) {
    Write-Host "`n  Richte Kodi-Autostart ein ..." -ForegroundColor DarkGray
    try {
        & (Join-Path $scriptsDir '02-windows-tuning.ps1') -SkipFirewall
    } catch {
        Write-Host "  Autostart konnte nicht eingerichtet werden: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# --- 4 ---------------------------------------------------------------------
Stop-KodiIfRunning
$args4 = @{}
if ($WebPassword) { $args4['WebPassword'] = $WebPassword }
$results['4 Kodi-Konfiguration'] = Invoke-Step -Number 4 -Title 'Kodi-Konfiguration ausrollen' `
    -Script (Join-Path $scriptsDir '04-deploy-kodi-config.ps1') -Arguments $args4

# --- 5 ---------------------------------------------------------------------
Write-Banner 'Kodi wird jetzt gestartet'
Write-Host '  Die naechsten Schritte sprechen mit dem laufenden Kodi.'
Start-Kodi

$args5 = @{}
if ($ReceiverName) { $args5['ReceiverName'] = $ReceiverName }
$results['5 Audio-Einstellungen'] = Invoke-Step -Number 5 -Title 'Audio und Passthrough setzen' `
    -Script (Join-Path $scriptsDir '05-apply-audio-settings.ps1') -Arguments $args5

# --- 6 ---------------------------------------------------------------------
Stop-KodiIfRunning
$results['6 Add-ons und Streams'] = Invoke-Step -Number 6 -Title 'Favoriten, Streams, Add-on-Pakete' `
    -Script (Join-Path $scriptsDir '06-install-addons.ps1')

# --- 7 ---------------------------------------------------------------------
Write-Banner 'Schritt 7 von 7: Abschlusspruefung'
Start-Kodi
Start-Sleep -Seconds 5
try {
    & (Join-Path $toolsDir 'healthcheck.ps1')
    $results['7 Pruefung'] = $true
} catch {
    Write-Host "  Pruefung fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Red
    $results['7 Pruefung'] = $false
}

# ===========================================================================
Write-Banner 'Zusammenfassung'
foreach ($kv in $results.GetEnumerator()) {
    $sym = if ($kv.Value) { 'ok  ' } else { 'FEHL' }
    $col = if ($kv.Value) { 'Green' } else { 'Red' }
    Write-Host ("  [{0}] {1}" -f $sym, $kv.Key) -ForegroundColor $col
}

Write-Host ""
Write-Host "  Zugangsdaten fuer Yatse/Kore: %ProgramData%\KodiMediacenter\fernsteuerung.txt" -ForegroundColor White
Write-Host ""
Write-Host "  Weiter geht es hier:" -ForegroundColor White
Write-Host "    docs\02-passthrough-matrix.md   Einstellungen pruefen und abnehmen"
Write-Host "    docs\03-headless-remote.md      Betrieb ohne Fernseher einrichten"
Write-Host "    docs\04-addons.md               DJ-Sets und Mediatheken"
Write-Host "    docs\05-equalizer-apo.md        Raummoden baendigen (optional)"
Write-Host "    docs\06-troubleshooting.md      wenn etwas klemmt"
Write-Host ""
