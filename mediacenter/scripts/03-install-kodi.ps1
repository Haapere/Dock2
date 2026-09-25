<#
.SYNOPSIS
    Installiert Kodi (x86_64) auf Windows 11 und legt die Benutzerordner an.

.DESCRIPTION
    Versucht die Installation in dieser Reihenfolge:
      1. winget (XBMCFoundation.Kodi)  - bevorzugt, weil updatefaehig
      2. Direkter Download vom offiziellen Kodi-Spiegel als Fallback

    Danach wird Kodi einmal kurz gestartet und wieder beendet, damit die
    Ordnerstruktur unter %APPDATA%\Kodi\userdata\ tatsaechlich existiert -
    ohne diesen Erststart gibt es kein guisettings.xml zum Ergaenzen.

.PARAMETER Version
    Zu installierende Version fuer den Fallback-Download, z. B. "21.2".
    Ohne Angabe wird die auf dem Spiegel als aktuell markierte Version geholt.

.PARAMETER SkipFirstRun
    Kodi nach der Installation nicht automatisch starten.

.PARAMETER Force
    Neu installieren, auch wenn Kodi bereits vorhanden ist.

.EXAMPLE
    .\03-install-kodi.ps1

.NOTES
    Als Administrator ausfuehren. Benoetigt Internetzugang.
#>

[CmdletBinding()]
param(
    [string] $Version,
    [switch] $SkipFirstRun,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step  { param([string]$m) Write-Host "`n[*] $m" -ForegroundColor Cyan }
function Write-Ok    { param([string]$m) Write-Host "    [ok]   $m" -ForegroundColor Green }
function Write-Warn2 { param([string]$m) Write-Host "    [warn] $m" -ForegroundColor Yellow }
function Write-Fail  { param([string]$m) Write-Host "    [fehl] $m" -ForegroundColor Red }

function Assert-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Bitte PowerShell als Administrator starten."
    }
}

function Find-KodiExe {
    $candidates = @(
        "$env:ProgramFiles\Kodi\kodi.exe",
        "${env:ProgramFiles(x86)}\Kodi\kodi.exe",
        "$env:LOCALAPPDATA\Programs\Kodi\kodi.exe"
    )
    return $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

Assert-Admin
Write-Host ""
Write-Host "=== Kodi-Installation ===" -ForegroundColor White

# ---------------------------------------------------------------------------
# Bereits installiert?
# ---------------------------------------------------------------------------
$existing = Find-KodiExe
if ($existing -and -not $Force) {
    $fv = (Get-Item $existing).VersionInfo.ProductVersion
    Write-Ok "Kodi ist bereits installiert: $existing (Version $fv)"
    Write-Warn2 'Neuinstallation erzwingen mit -Force'
} else {

    $installed = $false

    # -----------------------------------------------------------------------
    # Weg 1: winget
    # -----------------------------------------------------------------------
    Write-Step 'Versuche Installation ueber winget'
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue

    if ($winget) {
        try {
            $args = @(
                'install', '--id', 'XBMCFoundation.Kodi',
                '--exact', '--silent',
                '--accept-package-agreements', '--accept-source-agreements'
            )
            if ($Force) { $args += '--force' }

            & winget.exe @args
            # winget liefert 0 bei Erfolg, -1978335189 bei "bereits installiert"
            if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189) {
                Write-Ok 'winget-Installation abgeschlossen'
                $installed = $true
            } else {
                Write-Warn2 "winget Exitcode $LASTEXITCODE - weiche auf Direktdownload aus"
            }
        } catch {
            Write-Warn2 "winget fehlgeschlagen: $($_.Exception.Message)"
        }
    } else {
        Write-Warn2 'winget nicht verfuegbar (App-Installer fehlt) - weiche auf Direktdownload aus'
    }

    # -----------------------------------------------------------------------
    # Weg 2: Direktdownload vom offiziellen Spiegel
    # -----------------------------------------------------------------------
    if (-not $installed) {
        Write-Step 'Direktdownload von mirrors.kodi.tv'

        $baseUrl = 'https://mirrors.kodi.tv/releases/windows/win64/'
        $dlDir   = Join-Path $env:TEMP 'kodi-setup'
        if (-not (Test-Path $dlDir)) { New-Item -ItemType Directory -Path $dlDir -Force | Out-Null }

        try {
            $fileName = $null

            if ($Version) {
                $fileName = "KodiSetup-$Version-x64.exe"
            } else {
                Write-Host '    Lese Dateiliste vom Spiegel...' -ForegroundColor DarkGray
                $page = Invoke-WebRequest -Uri $baseUrl -UseBasicParsing -TimeoutSec 60

                # Nur finale Releases, keine Alpha/Beta/RC
                $matches = [regex]::Matches($page.Content, 'KodiSetup-(\d+\.\d+(?:\.\d+)?)-x64\.exe')
                $stable  = $matches |
                    Where-Object { $_.Value -notmatch '(?i)alpha|beta|rc' } |
                    ForEach-Object {
                        [pscustomobject]@{
                            File = $_.Value
                            Ver  = [version]($_.Groups[1].Value)
                        }
                    } |
                    Sort-Object Ver -Descending |
                    Select-Object -First 1

                if (-not $stable) { throw "Keine passende KodiSetup-Datei auf dem Spiegel gefunden." }
                $fileName = $stable.File
                Write-Ok "Gefundene Version: $($stable.Ver)"
            }

            $url    = $baseUrl + $fileName
            $target = Join-Path $dlDir $fileName

            Write-Host "    Lade $fileName ..." -ForegroundColor DarkGray
            $progressPreferenceBackup = $ProgressPreference
            $ProgressPreference = 'SilentlyContinue'   # beschleunigt Invoke-WebRequest erheblich
            try {
                Invoke-WebRequest -Uri $url -OutFile $target -UseBasicParsing -TimeoutSec 900
            } finally {
                $ProgressPreference = $progressPreferenceBackup
            }

            $sizeMb = [math]::Round((Get-Item $target).Length / 1MB, 1)
            Write-Ok "Heruntergeladen: $target ($sizeMb MB)"

            Write-Host '    Installiere im Hintergrund (NSIS /S)...' -ForegroundColor DarkGray
            $p = Start-Process -FilePath $target -ArgumentList '/S' -Wait -PassThru
            if ($p.ExitCode -ne 0) { throw "Installer-Exitcode $($p.ExitCode)" }
            Write-Ok 'Installation abgeschlossen'
            $installed = $true

        } catch {
            Write-Fail "Direktdownload fehlgeschlagen: $($_.Exception.Message)"
            Write-Warn2 'Bitte Kodi manuell von https://kodi.tv/download/ (Windows 64-Bit) installieren und dieses Skript erneut ausfuehren.'
            return
        }
    }
}

# ---------------------------------------------------------------------------
# Erststart, damit %APPDATA%\Kodi\userdata entsteht
# ---------------------------------------------------------------------------
$kodiExe = Find-KodiExe
if (-not $kodiExe) {
    Write-Fail 'kodi.exe wurde nach der Installation nicht gefunden.'
    return
}

$userdata = Join-Path $env:APPDATA 'Kodi\userdata'

if ($SkipFirstRun) {
    Write-Warn2 'Erststart uebersprungen (-SkipFirstRun). userdata-Ordner existiert evtl. noch nicht.'
} elseif (Test-Path (Join-Path $userdata 'guisettings.xml')) {
    Write-Ok "Profilordner vorhanden: $userdata"
} else {
    Write-Step 'Starte Kodi einmalig, damit das Benutzerprofil angelegt wird'
    Write-Warn2 'Kodi oeffnet sich kurz und wird automatisch wieder beendet - bitte nicht eingreifen.'

    $proc = Start-Process -FilePath $kodiExe -PassThru
    $deadline = (Get-Date).AddSeconds(120)
    $created  = $false

    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        if (Test-Path (Join-Path $userdata 'guisettings.xml')) { $created = $true; break }
    }

    # Kodi sauber beenden, damit es guisettings.xml vollstaendig schreibt
    try {
        if (-not $proc.HasExited) {
            $null = $proc.CloseMainWindow()
            if (-not $proc.WaitForExit(30000)) {
                Write-Warn2 'Kodi reagiert nicht auf Schliessen-Anforderung, beende hart.'
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
        Write-Warn2 "Beenden von Kodi: $($_.Exception.Message)"
    }

    Start-Sleep -Seconds 3
    if ($created -or (Test-Path (Join-Path $userdata 'guisettings.xml'))) {
        Write-Ok "Profilordner angelegt: $userdata"
    } else {
        Write-Warn2 "guisettings.xml noch nicht vorhanden. Bitte Kodi einmal von Hand starten und wieder beenden."
    }
}

Write-Host ''
Write-Host 'Naechster Schritt:  .\04-deploy-kodi-config.ps1' -ForegroundColor White
Write-Host ''
