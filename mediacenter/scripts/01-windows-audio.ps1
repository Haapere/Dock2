<#
.SYNOPSIS
    Konfiguriert Windows-Audio-Endpunkte fuer bit-perfekte Hi-Res-Wiedergabe.

.DESCRIPTION
    Setzt fuer einen Wiedergabe-Endpunkt (typisch: HDMI zum AV-Receiver):
      * "Anwendungen duerfen die exklusive Kontrolle uebernehmen"   = AN
      * "Anwendungen im Exklusivmodus haben Prioritaet"             = AN
      * Alle Signalverbesserungen / System-Effekte                  = AUS
      * optional: Standardformat auf 24 Bit / 96 kHz (Shared Mode)

    WICHTIG ZUM VERSTAENDNIS
    ------------------------
    Kodi spielt ueber WASAPI im EXCLUSIVE MODE. Dabei umgeht Kodi den
    Windows-Mixer vollstaendig und setzt die Samplerate des Quellmaterials
    direkt am Geraet. Das in der Windows-Systemsteuerung eingestellte
    "Standardformat" ist dann IRRELEVANT - es gilt nur fuer den Shared Mode
    (Browser, Systemklaenge, Spotify-Desktop usw.).

    Entscheidend fuer Kodi ist daher NUR das Exclusive-Flag. Ohne dieses Flag
    faellt Kodi still auf Shared Mode zurueck und resampelt auf das
    Windows-Standardformat - genau das, was wir vermeiden wollen.

    Das Setzen des Standardformats (-SetDefaultFormat) ist also Kosmetik fuer
    andere Programme, nicht fuer Kodi. Es ist der riskanteste Teil des Skripts
    (Binaerblob in der Registry) und daher standardmaessig AUS.

.PARAMETER List
    Listet alle Wiedergabegeraete mit Index und Status auf und beendet sich.

.PARAMETER DeviceFilter
    Teilstring des Geraetenamens, z. B. "Denon" oder "HDMI". Gross-/
    Kleinschreibung egal. Ohne Angabe wird das aktuelle Standardgeraet genutzt.

.PARAMETER All
    Wendet die Einstellungen auf ALLE aktiven Wiedergabegeraete an
    (praktisch, wenn HDMI und USB-DAC beide vorbereitet werden sollen).

.PARAMETER SetDefaultFormat
    Setzt zusaetzlich das Shared-Mode-Standardformat. Siehe Warnung oben.

.PARAMETER SampleRate
    Samplerate fuer -SetDefaultFormat. Standard 96000.

.PARAMETER BitDepth
    Bittiefe fuer -SetDefaultFormat. 16 oder 24. Standard 24.

.PARAMETER RestartAudio
    Startet den Windows-Audiodienst neu, damit Aenderungen sofort greifen.
    Unterbricht laufende Wiedergabe. Ohne diesen Schalter: Neustart noetig.

.PARAMETER Restore
    Stellt das zuletzt angelegte Registry-Backup wieder her.

.EXAMPLE
    .\01-windows-audio.ps1 -List

.EXAMPLE
    .\01-windows-audio.ps1 -DeviceFilter "Denon" -RestartAudio

.EXAMPLE
    .\01-windows-audio.ps1 -All -SetDefaultFormat -SampleRate 96000 -BitDepth 24

.NOTES
    Muss als Administrator laufen. Legt vor jeder Aenderung ein
    Registry-Backup unter %ProgramData%\KodiMediacenter\backup ab.
#>

[CmdletBinding(DefaultParameterSetName = 'Apply')]
param(
    [Parameter(ParameterSetName = 'List')]
    [switch] $List,

    [Parameter(ParameterSetName = 'Apply')]
    [string] $DeviceFilter,

    [Parameter(ParameterSetName = 'Apply')]
    [switch] $All,

    [Parameter(ParameterSetName = 'Apply')]
    [switch] $SetDefaultFormat,

    [Parameter(ParameterSetName = 'Apply')]
    [ValidateSet(44100, 48000, 88200, 96000, 176400, 192000)]
    [int] $SampleRate = 96000,

    [Parameter(ParameterSetName = 'Apply')]
    [ValidateSet(16, 24)]
    [int] $BitDepth = 24,

    [Parameter(ParameterSetName = 'Apply')]
    [switch] $RestartAudio,

    [Parameter(ParameterSetName = 'Restore')]
    [switch] $Restore
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------
$RenderRoot  = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render'
$BackupDir   = Join-Path $env:ProgramData 'KodiMediacenter\backup'

# Property-Keys (PKEY) als Registry-Wertnamen
$PKEY_FriendlyName     = '{a45c254e-df1c-4efd-8020-67d146a850e0},14'  # "Lautsprecher (Realtek)"
$PKEY_DeviceDesc       = '{a45c254e-df1c-4efd-8020-67d146a850e0},2'   # "Lautsprecher"
$PKEY_InterfaceName    = '{b3f8fa53-0004-438e-9003-51a46e139bfc},6'   # "Realtek High Definition Audio"
$PKEY_ExclusiveAllow   = '{b3f8fa53-0004-438e-9003-51a46e139bfc},3'   # Exklusivmodus erlauben
$PKEY_ExclusivePrio    = '{b3f8fa53-0004-438e-9003-51a46e139bfc},4'   # Exklusiv hat Prioritaet
$PKEY_DisableSysFx     = '{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5'   # System-Effekte aus
$PKEY_DeviceFormat     = '{f19f064d-082c-4e4f-9c70-7d5a5e1f9cd7},0'   # Shared-Mode Standardformat

# DeviceState-Bitmaske
$DEVICE_STATE_ACTIVE = 1

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

function Assert-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Dieses Skript muss als Administrator ausgefuehrt werden. PowerShell per Rechtsklick -> 'Als Administrator ausfuehren' starten."
    }
}

function Write-Step  { param([string]$m) Write-Host "`n[*] $m" -ForegroundColor Cyan }
function Write-Ok    { param([string]$m) Write-Host "    [ok]   $m" -ForegroundColor Green }
function Write-Warn2 { param([string]$m) Write-Host "    [warn] $m" -ForegroundColor Yellow }
function Write-Fail  { param([string]$m) Write-Host "    [fehl] $m" -ForegroundColor Red }

<#
    Liest einen Property-Wert eines Endpunkts, ohne bei fehlendem Wert zu werfen.
#>
function Get-EndpointProperty {
    param([string]$EndpointKey, [string]$PropertyName)
    $propsKey = Join-Path $EndpointKey 'Properties'
    if (-not (Test-Path $propsKey)) { return $null }
    try {
        $item = Get-ItemProperty -Path $propsKey -Name $PropertyName -ErrorAction Stop
        return $item.$PropertyName
    } catch {
        return $null
    }
}

<#
    Sammelt alle Wiedergabe-Endpunkte mit lesbarem Namen und Status.
#>
function Get-AudioEndpoints {
    if (-not (Test-Path $RenderRoot)) {
        throw "Registry-Pfad nicht gefunden: $RenderRoot"
    }

    $result = @()
    $i = 0
    foreach ($sub in Get-ChildItem -Path $RenderRoot) {
        $i++
        $state = 0
        try { $state = (Get-ItemProperty -Path $sub.PSPath -Name 'DeviceState' -ErrorAction Stop).DeviceState } catch { }

        $name = Get-EndpointProperty -EndpointKey $sub.PSPath -PropertyName $PKEY_FriendlyName
        if ([string]::IsNullOrWhiteSpace($name)) {
            $desc  = Get-EndpointProperty -EndpointKey $sub.PSPath -PropertyName $PKEY_DeviceDesc
            $iface = Get-EndpointProperty -EndpointKey $sub.PSPath -PropertyName $PKEY_InterfaceName
            $name  = (@($desc, $iface) | Where-Object { $_ } ) -join ' / '
        }
        if ([string]::IsNullOrWhiteSpace($name)) { $name = '(unbenannt)' }

        $stateText = switch ($state) {
            1 { 'aktiv' }
            2 { 'deaktiviert' }
            4 { 'nicht vorhanden' }
            8 { 'nicht angeschlossen' }
            default { "unbekannt($state)" }
        }

        $result += [pscustomobject]@{
            Index     = $i
            Name      = $name
            State     = $state
            StateText = $stateText
            KeyPath   = $sub.PSPath
            Guid      = $sub.PSChildName
        }
    }
    return $result
}

<#
    Erzeugt eine WAVEFORMATEXTENSIBLE-Struktur (40 Byte) als Byte-Array.
    Aufbau laut Microsoft:
      wFormatTag(2) nChannels(2) nSamplesPerSec(4) nAvgBytesPerSec(4)
      nBlockAlign(2) wBitsPerSample(2) cbSize(2)
      wValidBitsPerSample(2) dwChannelMask(4) SubFormat(16)
#>
function New-WaveFormatExtensible {
    param(
        [int]$SampleRate,
        [int]$BitsPerSample,
        [int]$Channels = 2
    )

    $bytesPerSample = [int]($BitsPerSample / 8)
    $blockAlign     = $Channels * $bytesPerSample
    $avgBytesPerSec = $SampleRate * $blockAlign
    $channelMask    = 0x3          # SPEAKER_FRONT_LEFT | SPEAKER_FRONT_RIGHT

    $ms = New-Object System.IO.MemoryStream
    $bw = New-Object System.IO.BinaryWriter($ms)
    try {
        $bw.Write([uint16]0xFFFE)            # WAVE_FORMAT_EXTENSIBLE
        $bw.Write([uint16]$Channels)
        $bw.Write([uint32]$SampleRate)
        $bw.Write([uint32]$avgBytesPerSec)
        $bw.Write([uint16]$blockAlign)
        $bw.Write([uint16]$BitsPerSample)
        $bw.Write([uint16]22)                # cbSize
        $bw.Write([uint16]$BitsPerSample)    # wValidBitsPerSample
        $bw.Write([uint32]$channelMask)
        # KSDATAFORMAT_SUBTYPE_PCM {00000001-0000-0010-8000-00aa00389b71}
        $bw.Write([byte[]]@(
            0x01,0x00,0x00,0x00,
            0x00,0x00,
            0x10,0x00,
            0x80,0x00,0x00,0xAA,0x00,0x38,0x9B,0x71
        ))
        $bw.Flush()
        return $ms.ToArray()
    } finally {
        $bw.Dispose(); $ms.Dispose()
    }
}

function Backup-Registry {
    if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $file  = Join-Path $BackupDir "MMDevices-Render-$stamp.reg"
    $regPath = 'HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render'
    & reg.exe export $regPath $file /y | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Registry-Backup fehlgeschlagen (reg.exe Exitcode $LASTEXITCODE)." }

    # Zeiger auf das juengste Backup
    Set-Content -Path (Join-Path $BackupDir 'latest-audio-backup.txt') -Value $file -Encoding UTF8
    return $file
}

function Restore-Registry {
    $pointer = Join-Path $BackupDir 'latest-audio-backup.txt'
    if (-not (Test-Path $pointer)) { throw "Kein Backup gefunden unter $BackupDir" }
    $file = (Get-Content $pointer -Raw).Trim()
    if (-not (Test-Path $file)) { throw "Backup-Datei fehlt: $file" }

    Write-Step "Stelle Registry-Backup wieder her: $file"
    & reg.exe import $file
    if ($LASTEXITCODE -ne 0) { throw "reg.exe import fehlgeschlagen (Exitcode $LASTEXITCODE)." }
    Write-Ok "Wiederhergestellt. Bitte Windows neu starten."
}

<#
    Setzt einen DWORD-Property-Wert an einem Endpunkt, mit sauberer
    Fehlermeldung falls die ACL das Schreiben verbietet.
#>
function Set-EndpointDword {
    param([string]$EndpointKey, [string]$PropertyName, [int]$Value, [string]$Label)

    $propsKey = Join-Path $EndpointKey 'Properties'
    if (-not (Test-Path $propsKey)) {
        New-Item -Path $propsKey -Force | Out-Null
    }
    try {
        New-ItemProperty -Path $propsKey -Name $PropertyName -PropertyType DWord -Value $Value -Force | Out-Null
        Write-Ok "$Label = $Value"
        return $true
    } catch {
        Write-Fail "$Label konnte nicht gesetzt werden: $($_.Exception.Message)"
        Write-Warn2 "Manuell: Systemsteuerung -> Sound -> Geraet -> Eigenschaften -> Erweitert"
        return $false
    }
}

function Set-EndpointBinary {
    param([string]$EndpointKey, [string]$PropertyName, [byte[]]$Value, [string]$Label)

    $propsKey = Join-Path $EndpointKey 'Properties'
    try {
        New-ItemProperty -Path $propsKey -Name $PropertyName -PropertyType Binary -Value $Value -Force | Out-Null
        Write-Ok "$Label"
        return $true
    } catch {
        Write-Fail "$Label konnte nicht gesetzt werden: $($_.Exception.Message)"
        return $false
    }
}

function Set-EndpointOptimised {
    param([pscustomobject]$Endpoint)

    Write-Step "Konfiguriere: $($Endpoint.Name)  [$($Endpoint.StateText)]"

    $okCount = 0
    if (Set-EndpointDword -EndpointKey $Endpoint.KeyPath -PropertyName $PKEY_ExclusiveAllow -Value 1 `
            -Label 'Exklusivmodus erlauben') { $okCount++ }
    if (Set-EndpointDword -EndpointKey $Endpoint.KeyPath -PropertyName $PKEY_ExclusivePrio -Value 1 `
            -Label 'Exklusivmodus hat Prioritaet') { $okCount++ }
    if (Set-EndpointDword -EndpointKey $Endpoint.KeyPath -PropertyName $PKEY_DisableSysFx -Value 1 `
            -Label 'Signalverbesserungen deaktiviert') { $okCount++ }

    if ($SetDefaultFormat) {
        $blob = New-WaveFormatExtensible -SampleRate $SampleRate -BitsPerSample $BitDepth -Channels 2
        $null = Set-EndpointBinary -EndpointKey $Endpoint.KeyPath -PropertyName $PKEY_DeviceFormat `
            -Value $blob -Label "Standardformat = $BitDepth Bit / $SampleRate Hz (nur Shared Mode)"
    }

    return $okCount
}

# ---------------------------------------------------------------------------
# Hauptablauf
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "=== Windows-Audio fuer Hi-Res / WASAPI Exclusive ===" -ForegroundColor White

if ($Restore) {
    Assert-Admin
    Restore-Registry
    return
}

if ($List) {
    $eps = Get-AudioEndpoints
    Write-Host ""
    $eps | Sort-Object Index | Format-Table Index, StateText, Name -AutoSize
    Write-Host "Auswahl per -DeviceFilter '<Teil des Namens>', z. B.  -DeviceFilter 'Denon'"
    Write-Host ""
    return
}

Assert-Admin

Write-Step 'Lege Registry-Backup an'
$backupFile = Backup-Registry
Write-Ok "Backup: $backupFile"
Write-Host "    Wiederherstellen jederzeit mit:  .\01-windows-audio.ps1 -Restore" -ForegroundColor DarkGray

$endpoints = Get-AudioEndpoints
$active    = $endpoints | Where-Object { $_.State -eq $DEVICE_STATE_ACTIVE }

if (-not $active) {
    Write-Fail 'Kein aktives Wiedergabegeraet gefunden.'
    Write-Warn2 'Ist der AV-Receiver eingeschaltet und per HDMI verbunden? Siehe docs/06-troubleshooting.md'
    return
}

$targets = @()
if ($All) {
    $targets = $active
} elseif ($DeviceFilter) {
    $targets = $active | Where-Object { $_.Name -like "*$DeviceFilter*" }
    if (-not $targets) {
        Write-Fail "Kein aktives Geraet passt auf '$DeviceFilter'."
        Write-Host ''
        $active | Format-Table Index, StateText, Name -AutoSize
        return
    }
} else {
    # Ohne Filter: alle aktiven HDMI-Geraete bevorzugen, sonst alle
    $hdmi = $active | Where-Object { $_.Name -match '(?i)hdmi|digital display|receiver|avr' }
    $targets = if ($hdmi) { $hdmi } else { $active }
    Write-Warn2 "Kein -DeviceFilter angegeben - verwende automatische Auswahl ($($targets.Count) Geraet(e))."
}

foreach ($t in $targets) { $null = Set-EndpointOptimised -Endpoint $t }

if ($RestartAudio) {
    Write-Step 'Starte Windows-Audiodienste neu'
    try {
        Restart-Service -Name 'Audiosrv' -Force -ErrorAction Stop
        Write-Ok 'Audiosrv neu gestartet'
    } catch {
        Write-Warn2 "Audiosrv-Neustart fehlgeschlagen: $($_.Exception.Message)"
        Write-Warn2 'Bitte Windows neu starten, damit die Aenderungen greifen.'
    }
} else {
    Write-Host ''
    Write-Warn2 'Ein Neustart von Windows (oder -RestartAudio) ist noetig, damit alles greift.'
}

Write-Host ''
Write-Host 'Kontrolle in der GUI:' -ForegroundColor White
Write-Host '  Win+R  ->  mmsys.cpl  ->  Geraet  ->  Eigenschaften  ->  Erweitert'
Write-Host '  Haken bei "Anwendungen die exklusive Kontrolle ueber das Geraet erlauben" muss gesetzt sein.'
Write-Host ''
