<#
.SYNOPSIS
    Schaltet die Audioausgabe zwischen AV-Receiver (HDMI) und USB-C DAC um -
    in Windows und in Kodi gleichzeitig.

.DESCRIPTION
    Zwei Dinge muessen zusammenpassen, sonst hoert man nichts:
      1. Windows-Standardgeraet  (fuer Browser, Systemklaenge, alles ausser Kodi)
      2. Kodis eigenes Ausgabegeraet (Kodi ignoriert das Windows-Standardgeraet)

    Fuer Punkt 1 wird das Modul AudioDeviceCmdlets verwendet. Ist es nicht
    vorhanden, bietet das Skript die Installation aus der PowerShell Gallery an
    und ueberspringt den Schritt andernfalls - Kodi wird trotzdem umgestellt.

.PARAMETER Target
    hdmi       - AV-Receiver ueber HDMI (Wohnzimmer)
    dac        - USB-C DAC am Schreibtisch (Kopfhoerer)
    status     - nur anzeigen, was aktuell aktiv ist

.PARAMETER HdmiMatch
    Suchbegriff fuer das HDMI-Geraet. Standard sucht nach HDMI/Receiver-Namen.

.PARAMETER DacMatch
    Suchbegriff fuer den USB-DAC. Standard: "USB" oder die bekannten Chipnamen
    des verbauten Adapters (CX31993 / ALC5686).

.PARAMETER InstallModule
    Installiert AudioDeviceCmdlets ohne Rueckfrage.

.EXAMPLE
    .\switch-audio.ps1 -Target status

.EXAMPLE
    .\switch-audio.ps1 -Target dac

.EXAMPLE
    .\switch-audio.ps1 -Target hdmi -HdmiMatch "Denon"

.NOTES
    Praktisch als Desktop-Verknuepfung:
      powershell.exe -ExecutionPolicy Bypass -File "...\switch-audio.ps1" -Target dac
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('hdmi', 'dac', 'status')]
    [string] $Target,

    [string] $HdmiMatch,
    [string] $DacMatch,
    [switch] $InstallModule,

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

$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$modPath  = Join-Path $toolsDir 'KodiRpc.psm1'

# Standard-Suchmuster
if (-not $HdmiMatch) { $HdmiMatch = 'hdmi|receiver|avr|denon|marantz|onkyo|pioneer|yamaha|sony|harman|digital display' }
if (-not $DacMatch)  { $DacMatch  = 'usb|cx31993|alc5686|dac|kopfh|headphone' }

$rpc = @{ KodiHost = $KodiHost }
if ($Port)     { $rpc['Port']     = $Port }
if ($User)     { $rpc['User']     = $User }
if ($Password) { $rpc['Password'] = $Password }

Write-Host ""
Write-Host "=== Audioausgabe umschalten ===" -ForegroundColor White

# ---------------------------------------------------------------------------
# Windows-Teil
# ---------------------------------------------------------------------------
function Ensure-AudioModule {
    if (Get-Module -ListAvailable -Name AudioDeviceCmdlets) {
        Import-Module AudioDeviceCmdlets -ErrorAction Stop
        return $true
    }

    Write-Warn2 'Modul AudioDeviceCmdlets fehlt - ohne das Modul kann das Windows-Standardgeraet nicht gewechselt werden.'

    $doInstall = $InstallModule
    if (-not $doInstall) {
        $answer = Read-Host 'Jetzt aus der PowerShell Gallery installieren? (j/n)'
        $doInstall = $answer -match '^(j|y)'
    }

    if (-not $doInstall) { return $false }

    try {
        Install-Module -Name AudioDeviceCmdlets -Scope CurrentUser -Force -AllowClobber -ErrorAction Stop
        Import-Module AudioDeviceCmdlets -ErrorAction Stop
        Write-Ok 'AudioDeviceCmdlets installiert'
        return $true
    } catch {
        Write-Fail "Installation fehlgeschlagen: $($_.Exception.Message)"
        Write-Warn2 'Alternative: Windows-Geraet von Hand umstellen (Win+Strg+V oder Lautstaerkesymbol).'
        return $false
    }
}

function Show-WindowsDevices {
    param($Devices)
    foreach ($d in $Devices) {
        $mark = if ($d.Default) { ' <- Standard' } else { '' }
        Write-Host ("      [{0}] {1}{2}" -f $d.Index, $d.Name, $mark) -ForegroundColor DarkGray
    }
}

$windowsOk = Ensure-AudioModule

if ($windowsOk) {
    Write-Step 'Windows-Wiedergabegeraete'
    try {
        $devices = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Playback' }
    } catch {
        Write-Fail "Geraeteliste nicht lesbar: $($_.Exception.Message)"
        $devices = @()
    }

    if ($Target -eq 'status') {
        Show-WindowsDevices $devices
    } elseif ($devices) {
        $pattern = if ($Target -eq 'hdmi') { $HdmiMatch } else { $DacMatch }
        $hit = $devices | Where-Object { $_.Name -match "(?i)$pattern" } | Select-Object -First 1

        if (-not $hit) {
            Write-Fail "Kein Windows-Geraet passt auf '$pattern'."
            Show-WindowsDevices $devices
        } else {
            try {
                Set-AudioDevice -Index $hit.Index | Out-Null
                Write-Ok "Windows-Standardgeraet: $($hit.Name)"
            } catch {
                Write-Fail "Umschalten fehlgeschlagen: $($_.Exception.Message)"
            }
        }
    }
}

# ---------------------------------------------------------------------------
# Kodi-Teil
# ---------------------------------------------------------------------------
Write-Step 'Kodi-Ausgabegeraet'

if (-not (Test-Path $modPath)) {
    Write-Warn2 "KodiRpc.psm1 nicht gefunden ($modPath) - Kodi wird nicht umgestellt."
    return
}

Import-Module $modPath -Force

if (-not (Test-KodiConnection @rpc)) {
    Write-Warn2 'Kodi ist nicht erreichbar - nur Windows wurde umgestellt.'
    Write-Warn2 'Das ist in Ordnung, wenn Kodi gerade nicht laeuft.'
    return
}

$settings = Get-KodiSettings -Level expert @rpc
$devSet   = $settings | Where-Object { $_.id -eq 'audiooutput.audiodevice' } | Select-Object -First 1

if (-not $devSet -or -not $devSet.options) {
    Write-Warn2 'Kodi meldet keine Geraeteliste.'
    return
}

$kodiDevices = @($devSet.options)

if ($Target -eq 'status') {
    Write-Host '    Kodi-Geraete:' -ForegroundColor DarkGray
    foreach ($d in $kodiDevices) {
        $mark = if ($devSet.value -eq $d.value) { ' <- aktiv' } else { '' }
        Write-Host ("      {0}{1}" -f $d.label, $mark) -ForegroundColor DarkGray
    }
    Write-Host ''
    return
}

$pattern = if ($Target -eq 'hdmi') { $HdmiMatch } else { $DacMatch }

# WASAPI bevorzugen - nur damit sind Exclusive Mode und Passthrough moeglich
$candidates = $kodiDevices | Where-Object { $_.label -match "(?i)$pattern" }
$wasapi     = $candidates  | Where-Object { $_.label -match '(?i)wasapi' }
$chosen     = if ($wasapi) { $wasapi | Select-Object -First 1 } else { $candidates | Select-Object -First 1 }

if (-not $chosen) {
    Write-Fail "Kein Kodi-Geraet passt auf '$pattern'. Verfuegbar:"
    foreach ($d in $kodiDevices) { Write-Host "      - $($d.label)" -ForegroundColor DarkGray }
    return
}

try {
    if (Set-KodiSetting -Setting 'audiooutput.audiodevice' -Value $chosen.value @rpc) {
        Write-Ok "Kodi spielt jetzt ueber: $($chosen.label)"
    } else {
        Write-Fail "Kodi hat das Geraet abgelehnt: $($chosen.label)"
    }
} catch {
    Write-Fail $_.Exception.Message
}

# Beim Wechsel auf Kopfhoerer ist Passthrough sinnlos und stumm - der DAC
# kann kein Dolby/DTS dekodieren.
if ($Target -eq 'dac') {
    try {
        $null = Set-KodiSetting -Setting 'audiooutput.passthrough' -Value $false @rpc
        Write-Ok 'Passthrough aus (Kopfhoerer-DAC kann Dolby/DTS nicht dekodieren)'
    } catch {
        Write-Warn2 "Passthrough konnte nicht abgeschaltet werden: $($_.Exception.Message)"
    }
} else {
    try {
        $null = Set-KodiSetting -Setting 'audiooutput.passthrough' -Value $true @rpc
        Write-Ok 'Passthrough wieder an'
    } catch {
        Write-Warn2 "Passthrough konnte nicht eingeschaltet werden: $($_.Exception.Message)"
    }
}

Write-Host ''
