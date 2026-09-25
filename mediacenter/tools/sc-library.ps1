<#
.SYNOPSIS
    Liest deine SoundCloud-Bibliothek aus und baut daraus ein Geschmacksprofil.

.DESCRIPTION
    Holt Likes, Reposts, Playlists und Gefolgte ueber yt-dlp - also mit
    derselben Anmeldung, die schon fuer die Downloads hinterlegt ist. Es
    werden keine Dateien geladen, nur Metadaten gelesen.

    Daraus entsteht ein Profil unter
      %LOCALAPPDATA%\KodiMediacenter\taste-profile.json

    das festhaelt, welche Kuenstlerinnen und Labels bei dir oft vorkommen,
    welche Genres und Schlagwoerter dominieren und welche Titel unter einer
    freien Lizenz stehen. tools/dj-suggest.ps1 macht daraus Vorschlaege.

    Das Profil waechst mit jedem Lauf: neue Likes kommen dazu, die Zaehler
    werden fortgeschrieben, Verschwundenes bleibt erhalten. Dadurch wird die
    Grundlage fuer Vorschlaege mit der Zeit besser.

    ZWEI DURCHGAENGE
    ---------------
    Ohne Schalter laeuft nur der schnelle Durchgang: eine Anfrage je Liste,
    liefert Kuenstler, Genres, Schlagwoerter und Lizenz. Dauert Sekunden.

    Mit -Deep wird jeder Titel einzeln abgefragt, um zu sehen, ob die
    Kuenstlerin einen Original-Download freigegeben hat - das ist die
    einzige Moeglichkeit, an die unkomprimierte Datei zu kommen, und
    SoundCloud verraet es nur bei der vollen Abfrage. Das dauert etwa eine
    Sekunde je Titel, laesst sich aber ueber -DeepLimit begrenzen und wird
    zwischengespeichert.

.PARAMETER User
    Dein SoundCloud-Nutzername, wie er in der Adresszeile steht
    (soundcloud.com/DEIN-NAME). Wird beim ersten Lauf gespeichert.

.PARAMETER What
    Welche Listen gelesen werden: likes, reposts, playlists, tracks,
    following oder all. Standard: likes und reposts.

.PARAMETER Limit
    Hoechstzahl der Eintraege je Liste. Standard 200, 0 = alle.

.PARAMETER Deep
    Zweiter Durchgang: prueft, bei welchen Titeln ein Original-Download
    bereitsteht.

.PARAMETER DeepLimit
    Wie viele Titel im zweiten Durchgang geprueft werden. Standard 60.

.PARAMETER Reset
    Vorhandenes Profil verwerfen und neu aufbauen.

.EXAMPLE
    .\sc-library.ps1 -User "meinname"

.EXAMPLE
    .\sc-library.ps1 -Deep -DeepLimit 100

.NOTES
    Voraussetzung: scripts\07-setup-ytdlp.ps1 -SetupSoundCloud wurde
    ausgefuehrt. Ohne Anmeldung sind nur oeffentliche Listen lesbar und
    Original-Downloads gar nicht.
#>

[CmdletBinding()]
param(
    [string]   $User,
    [ValidateSet('likes', 'reposts', 'playlists', 'tracks', 'following', 'all')]
    [string[]] $What = @('likes', 'reposts'),
    [int]      $Limit = 200,
    [switch]   $Deep,
    [int]      $DeepLimit = 60,
    [switch]   $Reset
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step  { param([string]$m) Write-Host "`n[*] $m" -ForegroundColor Cyan }
function Write-Ok    { param([string]$m) Write-Host "    [ok]   $m" -ForegroundColor Green }
function Write-Warn2 { param([string]$m) Write-Host "    [warn] $m" -ForegroundColor Yellow }
function Write-Fail  { param([string]$m) Write-Host "    [fehl] $m" -ForegroundColor Red }

$stateDir    = Join-Path $env:LOCALAPPDATA 'KodiMediacenter'
$binDir      = Join-Path $stateDir 'bin'
$profileFile = Join-Path $stateDir 'taste-profile.json'
$scFile      = Join-Path $stateDir 'soundcloud.json'
$deepCache   = Join-Path $stateDir 'sc-deep-cache.json'

if (-not (Test-Path $stateDir)) { New-Item -ItemType Directory -Path $stateDir -Force | Out-Null }

Write-Host ""
Write-Host "=== SoundCloud-Bibliothek lesen ===" -ForegroundColor White

# ---------------------------------------------------------------------------
# yt-dlp
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
    Write-Warn2 'Bitte zuerst:  .\scripts\07-setup-ytdlp.ps1'
    return
}

# ---------------------------------------------------------------------------
# Anmeldung
# ---------------------------------------------------------------------------
$authArgs = @()
if (Test-Path $scFile) {
    try {
        $sc = Get-Content $scFile -Raw | ConvertFrom-Json
        if ($sc.method -eq 'oauth' -and $sc.token) {
            $authArgs = @('--add-header', "Authorization:OAuth $($sc.token)")
            Write-Ok 'Angemeldet ueber OAuth-Token'
        } elseif ($sc.method -eq 'cookies' -and $sc.browser) {
            $authArgs = @('--cookies-from-browser', $sc.browser)
            Write-Ok "Angemeldet ueber Cookies aus $($sc.browser)"
        }
    } catch {
        Write-Warn2 "soundcloud.json nicht lesbar: $($_.Exception.Message)"
    }
}
if ($authArgs.Count -eq 0) {
    Write-Warn2 'Nicht angemeldet - nur oeffentliche Listen lesbar, keine Original-Downloads.'
    Write-Warn2 'Einrichten:  .\scripts\07-setup-ytdlp.ps1 -SetupSoundCloud'
}

# ---------------------------------------------------------------------------
# Profil laden
# ---------------------------------------------------------------------------
$taste = $null
if ((Test-Path $profileFile) -and -not $Reset) {
    try {
        $taste = Get-Content $profileFile -Raw | ConvertFrom-Json
        Write-Ok "Vorhandenes Profil geladen (Stand $($taste.updated))"
    } catch {
        Write-Warn2 'Profil nicht lesbar, wird neu aufgebaut.'
    }
}

if (-not $taste) {
    $taste = [pscustomobject]@{
        version = 1
        user    = ''
        created = (Get-Date -Format 'o')
        updated = ''
        runs    = 0
        tracks  = @{}
        artists = @{}
        genres  = @{}
        tags    = @{}
    }
}

# Hashtables aus dem JSON zurueckgewinnen (ConvertFrom-Json liefert PSCustomObject)
function ConvertTo-Hashtable {
    param($Obj)
    $h = @{}
    if ($null -eq $Obj) { return $h }
    if ($Obj -is [hashtable]) { return $Obj }
    foreach ($p in $Obj.PSObject.Properties) { $h[$p.Name] = $p.Value }
    return $h
}

$tracks  = ConvertTo-Hashtable $taste.tracks
$artists = ConvertTo-Hashtable $taste.artists
$genres  = ConvertTo-Hashtable $taste.genres
$tags    = ConvertTo-Hashtable $taste.tags

# ---------------------------------------------------------------------------
# Nutzername
# ---------------------------------------------------------------------------
if (-not $User) {
    if ($taste.user) {
        $User = $taste.user
        Write-Ok "Nutzer: $User (gespeichert)"
    } else {
        Write-Host ''
        Write-Host '    Dein SoundCloud-Nutzername steht in der Adresszeile deines Profils:' -ForegroundColor Gray
        Write-Host '    soundcloud.com/DEIN-NAME' -ForegroundColor Gray
        $User = (Read-Host '    Nutzername').Trim()
    }
}
if (-not $User) { Write-Fail 'Ohne Nutzernamen geht es nicht.'; return }
$taste.user = $User

# ---------------------------------------------------------------------------
# Listen abrufen
# ---------------------------------------------------------------------------
$lists = if ($What -contains 'all') {
    @('likes', 'reposts', 'playlists', 'tracks', 'following')
} else { $What }

<#
    Ruft eine SoundCloud-Liste als JSON ab. --flat-playlist haelt die Anfrage
    klein: yt-dlp liefert je Eintrag die Metadaten, aber keine Streamformate.
    Fuer Kuenstler, Genre, Schlagwoerter und Lizenz reicht das.
#>
function Get-ScList {
    param([string]$ListUrl, [int]$MaxItems)

    $args = @(
        '--flat-playlist'
        '--dump-single-json'
        '--ignore-errors'
        '--no-warnings'
        '--retries', '3'
    )
    if ($MaxItems -gt 0) { $args += @('--playlist-items', "1:$MaxItems") }
    $args += $authArgs
    $args += $ListUrl

    $raw = & $ytdlp @args 2>$null
    if (-not $raw) { return $null }

    try { return ($raw -join "`n" | ConvertFrom-Json) }
    catch {
        Write-Warn2 "Antwort nicht lesbar: $($_.Exception.Message)"
        return $null
    }
}

function Add-Count {
    param([hashtable]$Table, [string]$Key, [int]$By = 1)
    if ([string]::IsNullOrWhiteSpace($Key)) { return }
    $k = $Key.Trim()
    if ($Table.ContainsKey($k)) { $Table[$k] = [int]$Table[$k] + $By }
    else { $Table[$k] = $By }
}

$newTracks = 0

foreach ($list in $lists) {
    $url = "https://soundcloud.com/$User/$list"
    Write-Step "Lese $list"
    Write-Host "    $url" -ForegroundColor DarkGray

    $data = Get-ScList -ListUrl $url -MaxItems $Limit
    if (-not $data) {
        Write-Warn2 'Keine Daten - Liste leer, privat, oder Name falsch.'
        continue
    }

    $entries = @()
    if ($data.PSObject.Properties.Name -contains 'entries' -and $data.entries) {
        $entries = @($data.entries)
    }

    if ($entries.Count -eq 0) {
        Write-Warn2 'Liste enthaelt keine Eintraege.'
        continue
    }

    # "following" liefert Nutzerprofile statt Titel
    if ($list -eq 'following') {
        foreach ($e in $entries) {
            $name = if ($e.PSObject.Properties.Name -contains 'title') { "$($e.title)" }
                    elseif ($e.PSObject.Properties.Name -contains 'uploader') { "$($e.uploader)" }
                    else { '' }
            if ($name) {
                # Gefolgte zaehlen staerker: das ist eine bewusste Entscheidung
                Add-Count -Table $artists -Key $name -By 3
            }
        }
        Write-Ok "$($entries.Count) Gefolgte erfasst"
        continue
    }

    foreach ($e in $entries) {
        $id = if ($e.PSObject.Properties.Name -contains 'id') { "$($e.id)" } else { $null }
        if (-not $id) { continue }

        $uploader = if ($e.PSObject.Properties.Name -contains 'uploader') { "$($e.uploader)" } else { '' }
        $title    = if ($e.PSObject.Properties.Name -contains 'title') { "$($e.title)" } else { '' }
        $license  = if ($e.PSObject.Properties.Name -contains 'license') { "$($e.license)" } else { '' }
        $webUrl   = if ($e.PSObject.Properties.Name -contains 'url') { "$($e.url)" }
                    elseif ($e.PSObject.Properties.Name -contains 'webpage_url') { "$($e.webpage_url)" }
                    else { '' }
        $upUrl    = if ($e.PSObject.Properties.Name -contains 'uploader_url') { "$($e.uploader_url)" } else { '' }
        $dur      = if ($e.PSObject.Properties.Name -contains 'duration' -and $e.duration) { [int]$e.duration } else { 0 }

        $gs = @()
        if ($e.PSObject.Properties.Name -contains 'genres' -and $e.genres) { $gs = @($e.genres) }
        $ts = @()
        if ($e.PSObject.Properties.Name -contains 'tags' -and $e.tags) { $ts = @($e.tags) }

        $key = "sc:$id"
        if (-not $tracks.ContainsKey($key)) { $newTracks++ }

        $tracks[$key] = [pscustomobject]@{
            id        = $id
            title     = $title
            uploader  = $uploader
            uploaderUrl = $upUrl
            url       = $webUrl
            license   = $license
            duration  = $dur
            genres    = $gs
            tags      = $ts
            source    = $list
            seen      = (Get-Date -Format 'yyyy-MM-dd')
        }

        Add-Count -Table $artists -Key $uploader
        foreach ($g in $gs) { Add-Count -Table $genres -Key "$g" }
        foreach ($t in $ts) { Add-Count -Table $tags -Key "$t" }
    }

    Write-Ok "$($entries.Count) Eintraege gelesen"
}

# ---------------------------------------------------------------------------
# Zweiter Durchgang: Original-Downloads finden
# ---------------------------------------------------------------------------
if ($Deep) {
    Write-Step 'Pruefe auf freigegebene Original-Downloads'

    if ($authArgs.Count -eq 0) {
        Write-Warn2 'Ohne Anmeldung gibt SoundCloud keine Original-Downloads heraus - uebersprungen.'
    } else {
        $cache = @{}
        if (Test-Path $deepCache) {
            try { $cache = ConvertTo-Hashtable (Get-Content $deepCache -Raw | ConvertFrom-Json) } catch { }
        }

        # Noch nicht geprueft, und die neuesten zuerst
        $todo = @($tracks.Values |
                  Where-Object { $_.url -and -not $cache.ContainsKey("sc:$($_.id)") } |
                  Select-Object -First $DeepLimit)

        if ($todo.Count -eq 0) {
            Write-Ok 'Alles bereits geprueft (Zwischenspeicher).'
        } else {
            Write-Host "    $($todo.Count) Titel zu pruefen, etwa $([math]::Ceiling($todo.Count * 1.2)) Sekunden" -ForegroundColor DarkGray

            $i = 0
            $found = 0
            foreach ($t in $todo) {
                $i++
                if ($i % 10 -eq 0) { Write-Host "    $i / $($todo.Count) ..." -ForegroundColor DarkGray }

                $args = @('--dump-single-json', '--skip-download', '--no-warnings', '--ignore-errors', '--retries', '2')
                $args += $authArgs
                $args += $t.url

                try {
                    $raw = & $ytdlp @args 2>$null
                    if (-not $raw) { $cache["sc:$($t.id)"] = @{ checked = $true; original = $false }; continue }

                    $info = ($raw -join "`n" | ConvertFrom-Json)

                    $orig = $null
                    if ($info.PSObject.Properties.Name -contains 'formats' -and $info.formats) {
                        $orig = @($info.formats) | Where-Object { $_.format_id -eq 'download' } | Select-Object -First 1
                    }

                    if ($orig) {
                        $found++
                        $ext  = if ($orig.PSObject.Properties.Name -contains 'ext') { "$($orig.ext)" } else { '?' }
                        $size = if ($orig.PSObject.Properties.Name -contains 'filesize' -and $orig.filesize) { [int64]$orig.filesize } else { 0 }
                        $cache["sc:$($t.id)"] = @{
                            checked  = $true
                            original = $true
                            ext      = $ext
                            filesize = $size
                        }
                        $lossless = $ext -in @('wav', 'flac', 'aiff', 'aif', 'alac')
                        $mark = if ($lossless) { ' *verlustfrei*' } else { '' }
                        Write-Host "    + $($t.uploader) - $($t.title)  [$ext]$mark" -ForegroundColor Green
                    } else {
                        $cache["sc:$($t.id)"] = @{ checked = $true; original = $false }
                    }
                } catch {
                    $cache["sc:$($t.id)"] = @{ checked = $true; original = $false }
                }

                # SoundCloud mag keine Anfrageflut
                Start-Sleep -Milliseconds 400
            }

            $cache | ConvertTo-Json -Depth 5 | Set-Content -Path $deepCache -Encoding UTF8
            Write-Ok "$found von $($todo.Count) Titeln bieten einen Original-Download"
        }
    }
}

# ---------------------------------------------------------------------------
# Profil speichern
# ---------------------------------------------------------------------------
Write-Step 'Speichere Geschmacksprofil'

$taste.tracks  = $tracks
$taste.artists = $artists
$taste.genres  = $genres
$taste.tags    = $tags
$taste.updated = (Get-Date -Format 'o')
$taste.runs    = [int]$taste.runs + 1

$taste | ConvertTo-Json -Depth 8 | Set-Content -Path $profileFile -Encoding UTF8
Write-Ok "$profileFile"

# ---------------------------------------------------------------------------
# Kurzbericht
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host '--------------------------------------------------' -ForegroundColor White
Write-Host " Profil: $($tracks.Count) Titel, $($artists.Count) Kuenstler, Lauf Nr. $($taste.runs)" -ForegroundColor White
if ($newTracks -gt 0) { Write-Host " Davon neu in diesem Lauf: $newTracks" -ForegroundColor Green }
Write-Host '--------------------------------------------------' -ForegroundColor White

$topArtists = $artists.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 10
if ($topArtists) {
    Write-Host ''
    Write-Host ' Haeufigste Kuenstler / Labels:' -ForegroundColor White
    foreach ($a in $topArtists) { Write-Host ("   {0,3}x  {1}" -f $a.Value, $a.Key) }
}

$topGenres = $genres.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 8
if ($topGenres) {
    Write-Host ''
    Write-Host ' Haeufigste Genres:' -ForegroundColor White
    foreach ($g in $topGenres) { Write-Host ("   {0,3}x  {1}" -f $g.Value, $g.Key) }
}

$free = @($tracks.Values | Where-Object { $_.license -and $_.license -ne 'all-rights-reserved' })
if ($free.Count -gt 0) {
    Write-Host ''
    Write-Host " Titel unter freier Lizenz: $($free.Count)" -ForegroundColor Green
}

Write-Host ''
Write-Host ' Naechster Schritt:  .\tools\dj-suggest.ps1' -ForegroundColor White
Write-Host ''
