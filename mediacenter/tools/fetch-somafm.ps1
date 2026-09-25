<#
.SYNOPSIS
    Holt SomaFMs aktuelle Kanalliste und legt die elektronischen Kanäle als
    STRM-Dateien und Kodi-Favoriten an.

.DESCRIPTION
    SomaFM veroeffentlicht seine Kanaele unter https://somafm.com/channels.json.
    Das Skript liest diese Liste zur Laufzeit aus, statt URLs fest zu
    verdrahten - damit bleibt die Sammlung auch dann gueltig, wenn SomaFM
    Server umzieht oder Kanaele umbenennt.

    SomaFM ist fuer elektronische Musik eine der besten freien Quellen
    ueberhaupt: werbefrei, hoerergestuetzt, sorgfaeltig kuratiert. Relevant
    hier sind vor allem:

      Beat Blender       Downtempo House und Deep House
      Groove Salad       Chillout und Downtempo Electronica
      The Trip           Progressive House und Psytrance
      Dub Step Beyond    Dubstep und Bass
      Cliqhop idm        IDM und Glitch
      Space Station Soma Ambient Electronica
      DEF CON Radio      Musik der Hackerkonferenz, viel Elektronik

    Zur Qualitaet: Die regulaeren Streams liefern bis 256 kbit/s MP3 bzw.
    128 kbit/s AAC. Zusaetzlich betreibt SomaFM einen experimentellen
    verlustfreien FLAC-Stream ueber HLS. Ob Kodi den abspielt, haengt an der
    ffmpeg-Version - mit -IncludeFlac wird er angelegt und laesst sich
    einfach ausprobieren.

.PARAMETER Genre
    Nur Kanaele, deren Genre-Feld diesen Text enthaelt.
    Standard: elektronische Genres.

.PARAMETER All
    Alle Kanaele uebernehmen, nicht nur die elektronischen.

.PARAMETER IncludeFlac
    Zusaetzlich die experimentellen FLAC-HLS-Streams anlegen.

.PARAMETER StrmDir
    Zielordner. Standard: %USERPROFILE%\Music\Radio-Streams\SomaFM

.PARAMETER ListOnly
    Kanaele nur anzeigen, nichts anlegen.

.EXAMPLE
    .\fetch-somafm.ps1 -ListOnly

.EXAMPLE
    .\fetch-somafm.ps1 -IncludeFlac

.NOTES
    Kodi sollte beendet sein, wenn Favoriten geschrieben werden.
#>

[CmdletBinding()]
param(
    [string[]] $Genre = @('electronic', 'techno', 'house', 'downtempo', 'ambient', 'idm', 'dub', 'breaks', 'trance'),
    [switch]   $All,
    [switch]   $IncludeFlac,
    [string]   $StrmDir,
    [switch]   $ListOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step  { param([string]$m) Write-Host "`n[*] $m" -ForegroundColor Cyan }
function Write-Ok    { param([string]$m) Write-Host "    [ok]   $m" -ForegroundColor Green }
function Write-Warn2 { param([string]$m) Write-Host "    [warn] $m" -ForegroundColor Yellow }
function Write-Fail  { param([string]$m) Write-Host "    [fehl] $m" -ForegroundColor Red }

if (-not $StrmDir) {
    $homeDir = if ($env:USERPROFILE) { $env:USERPROFILE } else { [Environment]::GetFolderPath('UserProfile') }
    $StrmDir = Join-Path $homeDir 'Music\Radio-Streams\SomaFM'
}

Write-Host ""
Write-Host "=== SomaFM-Kanaele ===" -ForegroundColor White

# ---------------------------------------------------------------------------
# Kanalliste holen
# ---------------------------------------------------------------------------
Write-Step 'Lade Kanalliste von somafm.com'

try {
    $data = Invoke-RestMethod -Uri 'https://somafm.com/channels.json' -TimeoutSec 30 `
                -Headers @{ 'User-Agent' = 'Kodi-Mediacenter-Setup' }
} catch {
    Write-Fail "Kanalliste nicht abrufbar: $($_.Exception.Message)"
    Write-Warn2 'Ohne Internetzugang oder bei gesperrtem Zugriff kann die Liste nicht geholt werden.'
    return
}

if (-not $data -or -not $data.channels) {
    Write-Fail 'Unerwartetes Antwortformat.'
    return
}

$channels = @($data.channels)
Write-Ok "$($channels.Count) Kanaele gemeldet"

# ---------------------------------------------------------------------------
# Filtern
# ---------------------------------------------------------------------------
if ($All) {
    $selected = $channels
} else {
    $pattern  = ($Genre | ForEach-Object { [regex]::Escape($_) }) -join '|'
    $selected = @($channels | Where-Object {
        $g = if ($_.PSObject.Properties.Name -contains 'genre') { "$($_.genre)" } else { '' }
        $d = if ($_.PSObject.Properties.Name -contains 'description') { "$($_.description)" } else { '' }
        ($g -match "(?i)$pattern") -or ($d -match "(?i)$pattern")
    })
}

Write-Ok "$($selected.Count) davon passen zum Filter"

if ($selected.Count -eq 0) {
    Write-Warn2 'Kein Kanal passt. Mit -All alle uebernehmen, oder -Genre anpassen.'
    return
}

# ---------------------------------------------------------------------------
# Beste Playlist je Kanal bestimmen
# ---------------------------------------------------------------------------
<#
    SomaFM liefert je Kanal mehrere Playlists mit unterschiedlicher Qualitaet
    und Codec. Wir bevorzugen die hoechste Qualitaet; bei gleicher Qualitaet
    MP3 vor AAC, weil Kodi MP3-Streams am zuverlaessigsten verarbeitet.
#>
function Get-BestPlaylist {
    param($Channel)

    if ($Channel.PSObject.Properties.Name -notcontains 'playlists') { return $null }
    $pls = @($Channel.playlists)
    if ($pls.Count -eq 0) { return $null }

    $rank = @{ 'highest' = 3; 'high' = 2; 'low' = 1 }

    return $pls | Sort-Object `
        @{ Expression = { if ($_.quality -and $rank.ContainsKey($_.quality)) { $rank[$_.quality] } else { 0 } }; Descending = $true },
        @{ Expression = { if ($_.format -eq 'mp3') { 1 } else { 0 } }; Descending = $true } |
        Select-Object -First 1
}

<#
    Die playlists-Eintraege zeigen auf .pls-Dateien. Kodi spielt zwar auch
    .pls, aber eine direkte Stream-URL ist robuster - deshalb aufloesen.
#>
function Resolve-PlsUrl {
    param([string]$PlsUrl)

    try {
        $content = Invoke-WebRequest -Uri $PlsUrl -UseBasicParsing -TimeoutSec 20
        $text    = $content.Content

        $m = [regex]::Match($text, '(?im)^\s*File\d+\s*=\s*(\S+)\s*$')
        if ($m.Success) { return $m.Groups[1].Value }
    } catch {
        Write-Warn2 "  .pls nicht aufloesbar ($PlsUrl): $($_.Exception.Message.Split([char]10)[0])"
    }
    return $null
}

Write-Step 'Loese Stream-Adressen auf'

$results = @()

foreach ($ch in $selected) {
    $best = Get-BestPlaylist -Channel $ch
    if (-not $best) {
        Write-Warn2 "$($ch.title): keine Playlist gemeldet"
        continue
    }

    $direct = Resolve-PlsUrl -PlsUrl $best.url
    if (-not $direct) {
        # Rueckfallebene: die .pls-URL selbst eintragen, Kodi kommt meist damit klar
        $direct = $best.url
    }

    $quality = if ($best.PSObject.Properties.Name -contains 'quality') { $best.quality } else { '?' }
    $format  = if ($best.PSObject.Properties.Name -contains 'format')  { $best.format }  else { '?' }

    $results += [pscustomobject]@{
        Name    = "SomaFM - $($ch.title)"
        Url     = $direct
        Genre   = if ($ch.PSObject.Properties.Name -contains 'genre') { $ch.genre } else { '' }
        Format  = "$format / $quality"
        Lossless = $false
    }

    Write-Ok "$($ch.title)  [$format $quality]"

    if ($IncludeFlac) {
        $flacUrl = "https://hls.somafm.com/hls/$($ch.id)/FLAC/program.m3u8"
        $results += [pscustomobject]@{
            Name     = "SomaFM - $($ch.title) (FLAC, experimentell)"
            Url      = $flacUrl
            Genre    = if ($ch.PSObject.Properties.Name -contains 'genre') { $ch.genre } else { '' }
            Format   = 'FLAC / HLS'
            Lossless = $true
        }
    }
}

if ($ListOnly) {
    Write-Host ''
    Write-Host ("  {0,-46} {1,-16} {2}" -f 'Kanal', 'Format', 'Genre') -ForegroundColor White
    Write-Host ("  " + ("-" * 90)) -ForegroundColor DarkGray
    foreach ($r in $results) {
        Write-Host ("  {0,-46} {1,-16} {2}" -f $r.Name, $r.Format, $r.Genre)
    }
    Write-Host ''
    Write-Host "  Anlegen mit demselben Aufruf ohne -ListOnly"
    Write-Host ''
    return
}

# ---------------------------------------------------------------------------
# STRM-Dateien schreiben
# ---------------------------------------------------------------------------
Write-Step "Lege STRM-Dateien an: $StrmDir"

if (-not (Test-Path $StrmDir)) { New-Item -ItemType Directory -Path $StrmDir -Force | Out-Null }

foreach ($r in $results) {
    $safe = $r.Name -replace '[\\/:*?"<>|]', '-'
    Set-Content -Path (Join-Path $StrmDir "$safe.strm") -Value $r.Url -Encoding UTF8 -NoNewline
}
Write-Ok "$($results.Count) Dateien geschrieben"

$flacCount = @($results | Where-Object { $_.Lossless }).Count
if ($flacCount -gt 0) {
    Write-Warn2 "$flacCount davon sind experimentelle FLAC-Streams ueber HLS."
    Write-Warn2 'Ob Kodi sie abspielt, haengt an der ffmpeg-Version - einfach ausprobieren.'
    Write-Warn2 'Falls sie stumm bleiben: die Dateien mit "(FLAC" im Namen loeschen.'
}

Write-Host ''
Write-Host 'In Kodi einbinden (falls noch nicht geschehen):' -ForegroundColor White
Write-Host "  Musik -> Dateien -> Musik hinzufuegen -> $((Split-Path $StrmDir -Parent))"
Write-Host ''
Write-Host 'Bibliothek aktualisieren:' -ForegroundColor White
Write-Host '  Import-Module .\tools\KodiRpc.psm1 -Force'
Write-Host '  Invoke-KodiRpc -Method "AudioLibrary.Scan"'
Write-Host ''
