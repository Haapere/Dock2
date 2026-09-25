<#
.SYNOPSIS
    Holt DJ-Sets von YouTube, SoundCloud, Mixcloud und hearthis.at in die
    lokale Kodi-Musikbibliothek.

.DESCRIPTION
    Warum herunterladen statt streamen?

    Bei einem dreistuendigen Set ist Streaming der schlechtere Weg:
      * Jede Netzdelle riskiert einen Aussetzer mitten im Mix.
      * Springen an eine Stelle nach zwei Stunden bedeutet Nachpuffern.
      * Die Qualitaet haengt am Tagesform des Anbieters.
      * Faellt ein Add-on nach einem API-Wechsel aus, ist das Set weg.

    Eine lokale Datei loest alles davon auf einmal - und Kodi spielt lokale
    Dateien mit dem besten Codepfad, den es hat.

    yt-dlp holt dabei automatisch die beste verfuegbare Tonspur:
      YouTube     -> Opus, meist 160 kbit/s
      SoundCloud  -> mit Go+-Zugang 256 kbit/s AAC, sonst 128 kbit/s MP3
      Mixcloud    -> was der Anbieter hergibt
      hearthis.at -> haeufig der Original-Download der Kuenstlerin/des Kuenstlers

.PARAMETER Source
    Nur diese Quelle abrufen (Teilstring des Namens aus dj-sources.json).

.PARAMETER Url
    Einzelne URL herunterladen, ohne Quellenliste.

.PARAMETER All
    Alle Quellen aus config/dj-sources.json durchgehen.

.PARAMETER List
    Nur die konfigurierten Quellen anzeigen.

.PARAMETER Max
    Wie viele Sets je Quelle maximal geholt werden. Ueberschreibt die Vorgabe.

.PARAMETER MusicDir
    Zielordner. Standard: %USERPROFILE%\Music\DJ-Sets

.PARAMETER DryRun
    Nur anzeigen, was geholt wuerde.

.EXAMPLE
    .\dj-fetch.ps1 -List

.EXAMPLE
    .\dj-fetch.ps1 -Source "HOER" -Max 2

.EXAMPLE
    .\dj-fetch.ps1 -Url "https://soundcloud.com/drumcode/drumcode-radio-700"

.EXAMPLE
    .\dj-fetch.ps1 -All

.NOTES
    Voraussetzung: scripts\07-setup-ytdlp.ps1 wurde ausgefuehrt.

    Bereits geholte Sets werden uebersprungen (yt-dlp fuehrt ein Archiv),
    ein wiederholter Lauf holt also nur Neues. Damit eignet sich das Skript
    fuer die Aufgabenplanung, z. B. taeglich nachts.
#>

[CmdletBinding()]
param(
    [string] $Source,
    [string] $Url,
    [switch] $All,
    [switch] $List,
    [int]    $Max = 0,
    [string] $MusicDir = (Join-Path $env:USERPROFILE 'Music\DJ-Sets'),
    [switch] $DryRun
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step  { param([string]$m) Write-Host "`n[*] $m" -ForegroundColor Cyan }
function Write-Ok    { param([string]$m) Write-Host "    [ok]   $m" -ForegroundColor Green }
function Write-Warn2 { param([string]$m) Write-Host "    [warn] $m" -ForegroundColor Yellow }
function Write-Fail  { param([string]$m) Write-Host "    [fehl] $m" -ForegroundColor Red }

$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir  = Split-Path $toolsDir -Parent
$cfgFile  = Join-Path $rootDir 'config\dj-sources.json'
$binDir   = Join-Path $env:LOCALAPPDATA 'KodiMediacenter\bin'
$stateDir = Join-Path $env:LOCALAPPDATA 'KodiMediacenter'
$archive  = Join-Path $stateDir 'dj-fetch-archive.txt'
$scFile   = Join-Path $stateDir 'soundcloud.json'

Write-Host ""
Write-Host "=== DJ-Sets abrufen ===" -ForegroundColor White

# ---------------------------------------------------------------------------
# Werkzeuge finden
# ---------------------------------------------------------------------------
function Find-Tool {
    param([string]$Name)
    $cmd = Get-Command "$Name.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $local = Join-Path $binDir "$Name.exe"
    if (Test-Path $local) { return $local }
    return $null
}

$ytdlp = Find-Tool 'yt-dlp'
if (-not $ytdlp) {
    Write-Fail 'yt-dlp nicht gefunden.'
    Write-Warn2 'Bitte zuerst ausfuehren:  .\scripts\07-setup-ytdlp.ps1'
    return
}

$ffmpeg = Find-Tool 'ffmpeg'
if (-not $ffmpeg) {
    Write-Warn2 'ffmpeg nicht gefunden - Metadaten und Coverbilder werden nicht eingebettet.'
}

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
if (-not (Test-Path $cfgFile)) { throw "Quellenliste fehlt: $cfgFile" }
$cfg = Get-Content $cfgFile -Raw | ConvertFrom-Json

if ($List) {
    Write-Host ''
    Write-Host ("  {0,-28} {1,-12} {2}" -f 'Name', 'Plattform', 'Genre') -ForegroundColor White
    Write-Host ("  " + ("-" * 70)) -ForegroundColor DarkGray
    foreach ($s in $cfg.sources) {
        Write-Host ("  {0,-28} {1,-12} {2}" -f $s.name, $s.platform, $s.genre)
        if ($s.PSObject.Properties.Name -contains 'note') {
            Write-Host ("    {0}" -f $s.note) -ForegroundColor DarkGray
        }
    }
    Write-Host ''
    Write-Host '  Abruf:  .\dj-fetch.ps1 -Source "<Teil des Namens>"   oder   -All'
    Write-Host '  Eigene Quellen in config\dj-sources.json ergaenzen.'
    Write-Host ''
    return
}

if (-not (Test-Path $MusicDir)) { New-Item -ItemType Directory -Path $MusicDir -Force | Out-Null }
if (-not (Test-Path $stateDir)) { New-Item -ItemType Directory -Path $stateDir -Force | Out-Null }

# ---------------------------------------------------------------------------
# SoundCloud-Zugang
# ---------------------------------------------------------------------------
$scArgs = @()
if (Test-Path $scFile) {
    try {
        $sc = Get-Content $scFile -Raw | ConvertFrom-Json
        if ($sc.method -eq 'oauth' -and $sc.token) {
            $scArgs = @('--add-header', "Authorization:OAuth $($sc.token)")
            Write-Ok 'SoundCloud: OAuth-Token hinterlegt (Go+ Qualitaet moeglich)'
        } elseif ($sc.method -eq 'cookies' -and $sc.browser) {
            $scArgs = @('--cookies-from-browser', $sc.browser)
            Write-Ok "SoundCloud: Cookies aus $($sc.browser)"
        }
    } catch {
        Write-Warn2 "soundcloud.json nicht lesbar: $($_.Exception.Message)"
    }
} else {
    Write-Warn2 'Kein SoundCloud-Zugang hinterlegt - dort nur 128 kbit/s.'
    Write-Warn2 'Einrichten mit:  .\scripts\07-setup-ytdlp.ps1 -SetupSoundCloud'
}

# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
function Invoke-Fetch {
    param(
        [string] $TargetUrl,
        [string] $Label,
        [string] $Platform = 'generic',
        [int]    $MaxItems = 3,
        [int]    $MinMinutes = 20
    )

    Write-Step "$Label"
    Write-Host "    $TargetUrl" -ForegroundColor DarkGray

    # Jede Quelle bekommt einen eigenen Unterordner - Kodi zeigt ihn als Album/Ordner
    $safeLabel = $Label -replace '[\\/:*?"<>|]', '-'
    $outDir    = Join-Path $MusicDir $safeLabel

    $args = @(
        '--extract-audio'
        '--audio-quality', '0'          # 0 = beste verfuegbare Qualitaet
        '--format', 'bestaudio/best'
        '--no-playlist-reverse'
        '--download-archive', $archive  # bereits Geholtes ueberspringen
        '--no-overwrites'
        '--ignore-errors'               # ein gesperrtes Video stoppt nicht den Rest
        '--no-warnings'
        '--retries', '5'
        '--fragment-retries', '10'
        '--concurrent-fragments', '4'
        '--output', (Join-Path $outDir '%(upload_date>%Y-%m-%d)s - %(title).120s.%(ext)s')
    )

    # Nur echte Sets, keine Trailer und Ankuendigungen
    if ($MinMinutes -gt 0) {
        $args += @('--match-filter', "duration > $($MinMinutes * 60)")
    }

    if ($MaxItems -gt 0) {
        $args += @('--playlist-items', "1:$MaxItems")
    }

    if ($ffmpeg) {
        $args += @('--embed-metadata', '--embed-thumbnail', '--add-metadata')
        # Genre setzen, damit Kodis Musikbibliothek sinnvoll sortiert
        $args += @('--parse-metadata', 'playlist_title:%(genre)s')
    }

    if ($Platform -eq 'soundcloud' -and $scArgs.Count -gt 0) {
        $args += $scArgs
    }

    $args += $TargetUrl

    if ($DryRun) {
        Write-Host "    wuerde ausfuehren:" -ForegroundColor DarkGray
        Write-Host "    yt-dlp $($args -join ' ')" -ForegroundColor DarkGray
        return $true
    }

    try {
        & $ytdlp @args 2>&1 | ForEach-Object {
            $line = "$_"
            if ($line -match '\[download\]\s+Destination:\s*(.+)') {
                Write-Host "    hole: $(Split-Path $Matches[1] -Leaf)" -ForegroundColor Green
            }
            elseif ($line -match 'has already been recorded in the archive') {
                # erwartet bei wiederholtem Lauf - nicht melden
            }
            elseif ($line -match 'does not pass filter') {
                # zu kurz - gewollt uebersprungen
            }
            elseif ($line -match '^ERROR:') {
                Write-Warn2 ($line -replace '^ERROR:\s*', '')
            }
            elseif ($line -match '\[download\]\s+100%') {
                Write-Host "    fertig" -ForegroundColor DarkGray
            }
        }
        return $true
    } catch {
        Write-Fail "$Label : $($_.Exception.Message)"
        return $false
    }
}

$before = @(Get-ChildItem $MusicDir -Recurse -File -ErrorAction SilentlyContinue).Count

if ($Url) {
    $null = Invoke-Fetch -TargetUrl $Url -Label 'Einzelabruf' -MaxItems 0 -MinMinutes 0
}
elseif ($Source -or $All) {
    $targets = if ($All) { @($cfg.sources) }
               else      { @($cfg.sources | Where-Object { $_.name -like "*$Source*" }) }

    if (-not $targets) {
        Write-Fail "Keine Quelle passt auf '$Source'."
        Write-Host '    Verfuegbar:' -ForegroundColor DarkGray
        foreach ($s in $cfg.sources) { Write-Host "      - $($s.name)" -ForegroundColor DarkGray }
        return
    }

    foreach ($s in $targets) {
        $perSource = if ($Max -gt 0) { $Max }
                     elseif ($s.PSObject.Properties.Name -contains 'maxPerSource') { $s.maxPerSource }
                     else { $cfg.defaults.maxPerSource }

        $minMin = $cfg.defaults.minDurationMinutes

        # hearthis.at kennt yt-dlp nicht als eigene Plattform - dort steuert der
        # generische Extraktor, der auf Kategorieseiten nichts findet.
        if ($s.platform -eq 'hearthis' -and $s.url -match '/categories/') {
            Write-Step $s.name
            Write-Warn2 'Kategorieseiten von hearthis.at lassen sich nicht automatisch abrufen.'
            Write-Warn2 "Seite oeffnen, Set aussuchen, dann:  .\dj-fetch.ps1 -Url `"<Set-URL>`""
            Write-Host "    $($s.url)" -ForegroundColor DarkGray
            continue
        }

        $null = Invoke-Fetch -TargetUrl $s.url -Label $s.name -Platform $s.platform `
                    -MaxItems $perSource -MinMinutes $minMin
    }
}
else {
    Write-Warn2 'Nichts angegeben. Eine der Optionen waehlen:'
    Write-Host '    -List              Quellen anzeigen'
    Write-Host '    -Source "<Name>"   eine Quelle abrufen'
    Write-Host '    -All               alle Quellen abrufen'
    Write-Host '    -Url "<URL>"       einzelnes Set holen'
    return
}

# ---------------------------------------------------------------------------
# Ergebnis
# ---------------------------------------------------------------------------
if (-not $DryRun) {
    $after = @(Get-ChildItem $MusicDir -Recurse -File -ErrorAction SilentlyContinue).Count
    $neu   = $after - $before

    Write-Host ''
    if ($neu -gt 0) {
        Write-Ok "$neu neue Datei(en) in $MusicDir"

        $size = (Get-ChildItem $MusicDir -Recurse -File -ErrorAction SilentlyContinue |
                 Measure-Object -Property Length -Sum).Sum
        Write-Host ("    Ordner belegt jetzt {0:N1} GB" -f ($size / 1GB)) -ForegroundColor DarkGray

        Write-Host ''
        Write-Host '    Kodi-Bibliothek aktualisieren:' -ForegroundColor White
        Write-Host '      Import-Module .\tools\KodiRpc.psm1 -Force'
        Write-Host '      Invoke-KodiRpc -Method "AudioLibrary.Scan"'
    } else {
        Write-Ok 'Nichts Neues - alles bereits vorhanden.'
    }
}

Write-Host ''
Write-Host 'Tipp: Als naechtliche Aufgabe einrichten, dann sind morgens die' -ForegroundColor DarkGray
Write-Host '      neuen Sets da. Anleitung in docs\07-dj-sets.md' -ForegroundColor DarkGray
Write-Host ''
