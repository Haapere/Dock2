<#
.SYNOPSIS
    Macht aus deinem Geschmacksprofil konkrete Vorschlaege: neue Quellen fuer
    die Set-Liste und legale Downloads in moeglichst hoher Qualitaet.

.DESCRIPTION
    Grundlage ist das Profil, das tools\sc-library.ps1 aus deinen Likes,
    Reposts und Gefolgten gebaut hat. Daraus entstehen drei Arten von
    Vorschlaegen:

    1. NEUE QUELLEN
       Kuenstlerinnen und Labels, die in deiner Bibliothek oft vorkommen,
       aber noch nicht in config\dj-sources.json stehen. Mit -Apply werden
       sie dort eingetragen und ab dann von dj-fetch.ps1 mitgeholt.

    2. LEGALE DOWNLOADS AUF SOUNDCLOUD
       Zwei Faelle, beide ausdruecklich vom Rechteinhaber freigegeben:
         * Titel, bei denen ein Original-Download bereitsteht. Das ist die
           Datei, die hochgeladen wurde - haeufig WAV oder AIFF, also
           unkomprimiert und damit besser als jeder Stream.
         * Titel unter einer Creative-Commons-Lizenz.
       Beides erkennt sc-library.ps1; hier werden sie nur aufbereitet.

    3. BANDCAMP
       Fuer deine haeufigsten Kuenstler wird geprueft, ob es sie auf
       Bandcamp gibt. Das ist fuer Techno die beste legale Quelle
       ueberhaupt: Kaufdateien gibt es dort als FLAC, WAV oder AIFF -
       verlustfrei, in deutlich hoeherer Qualitaet als alles Gestreamte,
       und der groesste Teil des Geldes geht direkt an die Kuenstler.

    Das Skript merkt sich, was es schon vorgeschlagen hat. Ein zweiter Lauf
    zeigt also nur Neues, und abgelehnte Vorschlaege kommen nicht wieder.

.PARAMETER Top
    Wie viele der haeufigsten Kuenstler betrachtet werden. Standard 25.

.PARAMETER MinCount
    Wie oft eine Kuenstlerin mindestens vorkommen muss, um vorgeschlagen zu
    werden. Standard 2 - verhindert Vorschlaege aus einzelnen Zufallslikes.

.PARAMETER Apply
    Neue Quellen ohne Rueckfrage in config\dj-sources.json eintragen.

.PARAMETER Interactive
    Jeden Quellen-Vorschlag einzeln bestaetigen oder ablehnen.

.PARAMETER SkipBandcamp
    Bandcamp-Abgleich auslassen (spart Zeit und Anfragen).

.PARAMETER Reset
    Merkliste der bisherigen Vorschlaege leeren.

.EXAMPLE
    .\dj-suggest.ps1

.EXAMPLE
    .\dj-suggest.ps1 -Interactive

.EXAMPLE
    .\dj-suggest.ps1 -Apply -SkipBandcamp

.NOTES
    Der Bandcamp-Abgleich nutzt die Schnittstelle hinter dem Suchfeld von
    bandcamp.com. Die ist nicht offiziell dokumentiert und kann sich
    jederzeit aendern; faellt sie aus, laeuft der Rest weiter.
#>

[CmdletBinding()]
param(
    [int]    $Top = 25,
    [int]    $MinCount = 2,
    [switch] $Apply,
    [switch] $Interactive,
    [switch] $SkipBandcamp,
    [switch] $Reset
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step  { param([string]$m) Write-Host "`n[*] $m" -ForegroundColor Cyan }
function Write-Ok    { param([string]$m) Write-Host "    [ok]   $m" -ForegroundColor Green }
function Write-Warn2 { param([string]$m) Write-Host "    [warn] $m" -ForegroundColor Yellow }
function Write-Fail  { param([string]$m) Write-Host "    [fehl] $m" -ForegroundColor Red }

$toolsDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir     = Split-Path $toolsDir -Parent
$djFile      = Join-Path $rootDir 'config\dj-sources.json'
$stateDir    = Join-Path $env:LOCALAPPDATA 'KodiMediacenter'
$profileFile = Join-Path $stateDir 'taste-profile.json'
$deepCache   = Join-Path $stateDir 'sc-deep-cache.json'
$seenFile    = Join-Path $stateDir 'suggestions-seen.json'
$reportFile  = Join-Path $stateDir 'vorschlaege.md'

Write-Host ""
Write-Host "=== Vorschlaege ===" -ForegroundColor White

# ---------------------------------------------------------------------------
# Profil laden
# ---------------------------------------------------------------------------
if (-not (Test-Path $profileFile)) {
    Write-Fail 'Kein Geschmacksprofil vorhanden.'
    Write-Warn2 'Bitte zuerst:  .\tools\sc-library.ps1 -User "<dein-name>"'
    return
}

$taste = Get-Content $profileFile -Raw | ConvertFrom-Json

function ConvertTo-Hashtable {
    param($Obj)
    $h = @{}
    if ($null -eq $Obj) { return $h }
    foreach ($p in $Obj.PSObject.Properties) { $h[$p.Name] = $p.Value }
    return $h
}

$artists = ConvertTo-Hashtable $taste.artists
$tracks  = ConvertTo-Hashtable $taste.tracks

Write-Ok "Profil: $($tracks.Count) Titel, $($artists.Count) Kuenstler, Stand $($taste.updated)"

if ($artists.Count -eq 0) {
    Write-Warn2 'Profil ist leer - nichts vorzuschlagen.'
    return
}

# ---------------------------------------------------------------------------
# Merkliste
# ---------------------------------------------------------------------------
$seen = @{}
if ((Test-Path $seenFile) -and -not $Reset) {
    try { $seen = ConvertTo-Hashtable (Get-Content $seenFile -Raw | ConvertFrom-Json) } catch { }
}

# ---------------------------------------------------------------------------
# Vorhandene Quellen
# ---------------------------------------------------------------------------
if (-not (Test-Path $djFile)) { Write-Fail "Quellenliste fehlt: $djFile"; return }
$dj = Get-Content $djFile -Raw | ConvertFrom-Json

$knownUrls  = @($dj.sources | ForEach-Object { "$($_.url)".ToLower().TrimEnd('/') })
$knownNames = @($dj.sources | ForEach-Object { "$($_.name)".ToLower() })

function Test-AlreadyKnown {
    param([string]$Name, [string]$Url)
    $n = $Name.ToLower()
    $u = $Url.ToLower().TrimEnd('/')
    if ($knownUrls -contains $u) { return $true }
    foreach ($kn in $knownNames) {
        if ($kn -eq $n) { return $true }
        # Teilstring in beide Richtungen faengt "Drumcode" vs "Drumcode Radio"
        if ($kn.Length -gt 4 -and ($kn.Contains($n) -or $n.Contains($kn))) { return $true }
    }
    return $false
}

# ===========================================================================
# 1. NEUE QUELLEN
# ===========================================================================
Write-Step 'Neue Quellen fuer die Set-Liste'

$candidates = @($artists.GetEnumerator() |
    Where-Object { [int]$_.Value -ge $MinCount } |
    Sort-Object Value -Descending |
    Select-Object -First $Top)

$newSources = @()

foreach ($c in $candidates) {
    $name  = "$($c.Key)"
    $count = [int]$c.Value
    if ([string]::IsNullOrWhiteSpace($name)) { continue }

    # Profil-URL aus einem Titel dieser Kuenstlerin ableiten - zuverlaessiger
    # als den Namen zu einem Profilnamen zu raten
    $sample = $tracks.Values | Where-Object { "$($_.uploader)" -eq $name -and $_.uploaderUrl } | Select-Object -First 1
    if (-not $sample) {
        $sample = $tracks.Values | Where-Object { "$($_.uploader)" -eq $name -and $_.url } | Select-Object -First 1
    }

    $profileUrl = ''
    if ($sample -and $sample.uploaderUrl) {
        $profileUrl = "$($sample.uploaderUrl)".TrimEnd('/') + '/tracks'
    } elseif ($sample -and $sample.url -match '^(https?://soundcloud\.com/[^/]+)') {
        $profileUrl = $Matches[1] + '/tracks'
    } else {
        continue
    }

    $key = "source:$profileUrl"
    if ($seen.ContainsKey($key)) { continue }
    if (Test-AlreadyKnown -Name $name -Url $profileUrl) { continue }

    # Genre aus den Titeln dieser Kuenstlerin ableiten
    $theirTracks = @($tracks.Values | Where-Object { "$($_.uploader)" -eq $name })
    $genre = ''
    $allGenres = @($theirTracks | ForEach-Object { if ($_.genres) { $_.genres } }) | Where-Object { $_ }
    if ($allGenres.Count -gt 0) {
        $genre = ($allGenres | Group-Object | Sort-Object Count -Descending | Select-Object -First 1).Name
    }

    # Wie lang sind ihre Sachen im Schnitt? Kurze Tracks sind keine Sets.
    $avgMin = 0
    $durs = @($theirTracks | Where-Object { $_.duration -gt 0 } | ForEach-Object { [int]$_.duration })
    if ($durs.Count -gt 0) { $avgMin = [math]::Round((($durs | Measure-Object -Average).Average) / 60) }

    $newSources += [pscustomobject]@{
        Name       = $name
        Url        = $profileUrl
        Count      = $count
        Genre      = if ($genre) { $genre } else { 'unbekannt' }
        AvgMinutes = $avgMin
        IsSetLike  = ($avgMin -ge 20)
        Key        = $key
    }
}

if ($newSources.Count -eq 0) {
    Write-Ok 'Keine neuen Quellen - alles Haeufige steht bereits in der Liste.'
} else {
    Write-Ok "$($newSources.Count) Vorschlaege"
    Write-Host ''
    Write-Host ("  {0,-30} {1,5} {2,-20} {3,8}  {4}" -f 'Kuenstler/Label', 'Likes', 'Genre', 'ø Laenge', 'Art') -ForegroundColor White
    Write-Host ("  " + ("-" * 88)) -ForegroundColor DarkGray
    foreach ($s in $newSources) {
        $art = if ($s.IsSetLike) { 'Sets' } else { 'Einzeltracks' }
        $col = if ($s.IsSetLike) { 'Green' } else { 'Gray' }
        Write-Host ("  {0,-30} {1,5} {2,-20} {3,6} min  {4}" -f `
            $s.Name.Substring(0, [Math]::Min(30, $s.Name.Length)), $s.Count, `
            $s.Genre.Substring(0, [Math]::Min(20, $s.Genre.Length)), $s.AvgMinutes, $art) -ForegroundColor $col
    }
    Write-Host ''
    Write-Host '  Gruen = durchschnittlich ueber 20 Minuten, also vermutlich Sets.' -ForegroundColor DarkGray
}

# ===========================================================================
# 2. LEGALE DOWNLOADS AUF SOUNDCLOUD
# ===========================================================================
Write-Step 'Legale Downloads in deiner Bibliothek'

$deep = @{}
if (Test-Path $deepCache) {
    try { $deep = ConvertTo-Hashtable (Get-Content $deepCache -Raw | ConvertFrom-Json) } catch { }
}

# 2a - Original-Downloads
$originals = @()
foreach ($kv in $deep.GetEnumerator()) {
    $entry = $kv.Value
    $hasOrig = $false
    try { $hasOrig = [bool]$entry.original } catch { }
    if (-not $hasOrig) { continue }

    $t = $tracks[$kv.Key]
    if (-not $t) { continue }

    $ext = ''
    try { $ext = "$($entry.ext)" } catch { }
    $size = 0
    try { if ($entry.filesize) { $size = [int64]$entry.filesize } } catch { }

    $originals += [pscustomobject]@{
        Title    = "$($t.uploader) - $($t.title)"
        Url      = $t.url
        Ext      = $ext
        SizeMb   = if ($size -gt 0) { [math]::Round($size / 1MB, 1) } else { 0 }
        Lossless = ($ext -in @('wav', 'flac', 'aiff', 'aif', 'alac'))
    }
}

if ($deep.Count -eq 0) {
    Write-Warn2 'Noch nicht auf Original-Downloads geprueft.'
    Write-Warn2 'Nachholen mit:  .\tools\sc-library.ps1 -Deep'
} elseif ($originals.Count -eq 0) {
    Write-Ok 'Keiner der geprueften Titel bietet einen Original-Download.'
} else {
    $lossless = @($originals | Where-Object { $_.Lossless })
    Write-Ok "$($originals.Count) Titel mit Original-Download, davon $($lossless.Count) verlustfrei"

    Write-Host ''
    foreach ($o in ($originals | Sort-Object -Property @{Expression='Lossless';Descending=$true}, Title | Select-Object -First 20)) {
        $mark = if ($o.Lossless) { '[verlustfrei]' } else { "[$($o.Ext)]" }
        $col  = if ($o.Lossless) { 'Green' } else { 'Gray' }
        $sz   = if ($o.SizeMb -gt 0) { " $($o.SizeMb) MB" } else { '' }
        Write-Host ("  {0,-14} {1}{2}" -f $mark, $o.Title, $sz) -ForegroundColor $col
    }
    if ($originals.Count -gt 20) { Write-Host "  ... und $($originals.Count - 20) weitere" -ForegroundColor DarkGray }

    Write-Host ''
    Write-Host '  Holen mit:  .\tools\dj-fetch.ps1 -Url "<URL>"' -ForegroundColor White
    Write-Host '  yt-dlp nimmt dabei automatisch die Originaldatei.' -ForegroundColor DarkGray
}

# 2b - freie Lizenzen
$ccTracks = @($tracks.Values | Where-Object {
    $_.license -and "$($_.license)" -ne 'all-rights-reserved' -and "$($_.license)" -ne ''
})

if ($ccTracks.Count -gt 0) {
    Write-Host ''
    Write-Ok "$($ccTracks.Count) Titel unter freier Lizenz (Creative Commons)"
    foreach ($t in ($ccTracks | Select-Object -First 10)) {
        Write-Host ("  [{0,-16}] {1} - {2}" -f $t.license, $t.uploader, $t.title) -ForegroundColor Gray
    }
    if ($ccTracks.Count -gt 10) { Write-Host "  ... und $($ccTracks.Count - 10) weitere" -ForegroundColor DarkGray }
}

# ===========================================================================
# 3. BANDCAMP
# ===========================================================================
$bandcampHits = @()

if (-not $SkipBandcamp) {
    Write-Step 'Bandcamp-Abgleich (verlustfreie Kaufdateien)'

    <#
        Schnittstelle hinter dem Suchfeld von bandcamp.com. Nicht offiziell
        dokumentiert - deshalb defensiv behandeln und bei Fehlern einfach
        weitergehen.
    #>
    function Search-Bandcamp {
        param([string]$Query, [string]$Filter = 'b')

        $body = @{
            search_text   = $Query
            search_filter = $Filter
            full_page     = $false
            fan_id        = $null
        } | ConvertTo-Json -Compress

        try {
            $resp = Invoke-RestMethod -Method Post `
                -Uri 'https://bandcamp.com/api/bcsearch_public_api/1/autocomplete_elastic' `
                -ContentType 'application/json' `
                -Headers @{ 'User-Agent' = 'Mozilla/5.0' } `
                -Body $body -TimeoutSec 20

            if ($resp -and $resp.auto -and $resp.auto.results) { return @($resp.auto.results) }
        } catch {
            throw
        }
        return @()
    }

    $checkList = @($candidates | Select-Object -First 15)
    $apiOk = $true
    $checked = 0

    foreach ($c in $checkList) {
        if (-not $apiOk) { break }
        $name = "$($c.Key)"
        if ([string]::IsNullOrWhiteSpace($name)) { continue }

        $key = "bandcamp:$($name.ToLower())"
        if ($seen.ContainsKey($key)) { continue }

        try {
            $results = Search-Bandcamp -Query $name -Filter 'b'
            $checked++

            # Nur Treffer, deren Name wirklich passt - die Suche ist grosszuegig
            $hit = $results | Where-Object {
                $rn = ''
                if ($_.PSObject.Properties.Name -contains 'name') { $rn = "$($_.name)" }
                $rn -and ($rn.ToLower() -eq $name.ToLower() -or
                          $rn.ToLower().Replace(' ', '') -eq $name.ToLower().Replace(' ', ''))
            } | Select-Object -First 1

            if ($hit) {
                $url = ''
                if ($hit.PSObject.Properties.Name -contains 'url') { $url = "$($hit.url)" }
                $bandcampHits += [pscustomobject]@{
                    Name  = $name
                    Url   = $url
                    Count = [int]$c.Value
                    Key   = $key
                }
                Write-Host "  + $name  ->  $url" -ForegroundColor Green
            }
        } catch {
            Write-Warn2 "Bandcamp-Suche nicht verfuegbar: $($_.Exception.Message.Split([char]10)[0])"
            Write-Warn2 'Ueberspringe diesen Teil - die uebrigen Vorschlaege bleiben gueltig.'
            $apiOk = $false
        }

        Start-Sleep -Milliseconds 600
    }

    if ($apiOk) {
        if ($bandcampHits.Count -eq 0) {
            Write-Ok "$checked Kuenstler geprueft, keine neuen Bandcamp-Seiten gefunden."
        } else {
            Write-Host ''
            Write-Ok "$($bandcampHits.Count) deiner Kuenstler sind auf Bandcamp"
            Write-Host '  Dort gibt es die Musik als FLAC, WAV oder AIFF - verlustfrei und' -ForegroundColor DarkGray
            Write-Host '  deutlich besser als jeder Stream. Kaufen, herunterladen, in den' -ForegroundColor DarkGray
            Write-Host '  Musikordner legen, fertig.' -ForegroundColor DarkGray
        }
    }
}

# ===========================================================================
# ÜBERNEHMEN
# ===========================================================================
$applied = 0

if ($newSources.Count -gt 0) {
    Write-Step 'Quellen uebernehmen'

    $toAdd = @()

    if ($Interactive) {
        foreach ($s in $newSources) {
            $art = if ($s.IsSetLike) { "Sets, ø $($s.AvgMinutes) min" } else { "Einzeltracks, ø $($s.AvgMinutes) min" }
            Write-Host ''
            Write-Host "  $($s.Name)  ($($s.Count)x in deiner Bibliothek, $art)" -ForegroundColor White
            Write-Host "  $($s.Url)" -ForegroundColor DarkGray
            $a = Read-Host '  Aufnehmen? (j = ja / n = nein, nicht wieder fragen / Enter = spaeter)'
            if ($a -match '^[jy]') { $toAdd += $s }
            elseif ($a -match '^n') { $seen[$s.Key] = @{ status = 'abgelehnt'; on = (Get-Date -Format 'yyyy-MM-dd') } }
        }
    }
    elseif ($Apply) {
        # Ohne Rueckfrage nur das, was nach Sets aussieht - Einzeltracks
        # wuerden die Liste zumuellen
        $toAdd = @($newSources | Where-Object { $_.IsSetLike })
        Write-Host "    -Apply: uebernehme $($toAdd.Count) set-artige Quellen (Einzeltrack-Kuenstler ausgelassen)" -ForegroundColor DarkGray
    }
    else {
        Write-Host '    Nichts uebernommen. Optionen:' -ForegroundColor DarkGray
        Write-Host '      -Interactive   jeden Vorschlag einzeln entscheiden'
        Write-Host '      -Apply         alle set-artigen Quellen auf einmal aufnehmen'
    }

    if ($toAdd.Count -gt 0) {
        $list = [System.Collections.ArrayList]::new()
        foreach ($existing in $dj.sources) { [void]$list.Add($existing) }

        foreach ($s in $toAdd) {
            [void]$list.Add([pscustomobject]@{
                name         = $s.Name
                platform     = 'soundcloud'
                url          = $s.Url
                genre        = $s.Genre
                note         = "Automatisch vorgeschlagen: $($s.Count)x in deiner SoundCloud-Bibliothek, durchschnittlich $($s.AvgMinutes) Minuten."
                maxPerSource = 2
                addedBy      = 'dj-suggest'
                addedOn      = (Get-Date -Format 'yyyy-MM-dd')
            })
            $seen[$s.Key] = @{ status = 'uebernommen'; on = (Get-Date -Format 'yyyy-MM-dd') }
            $applied++
        }

        $dj.sources = $list.ToArray()

        # Sicherungskopie, bevor die gepflegte Liste angefasst wird
        $bak = Join-Path $stateDir "dj-sources-$(Get-Date -Format 'yyyyMMdd-HHmmss').json"
        Copy-Item $djFile $bak -Force

        $dj | ConvertTo-Json -Depth 10 | Set-Content -Path $djFile -Encoding UTF8
        Write-Ok "$applied Quellen eingetragen in $djFile"
        Write-Host "    Sicherung der vorherigen Fassung: $bak" -ForegroundColor DarkGray
    }
}

# Bandcamp-Treffer merken, damit sie nicht wieder auftauchen
foreach ($b in $bandcampHits) {
    $seen[$b.Key] = @{ status = 'gezeigt'; on = (Get-Date -Format 'yyyy-MM-dd'); url = $b.Url }
}

$seen | ConvertTo-Json -Depth 5 | Set-Content -Path $seenFile -Encoding UTF8

# ===========================================================================
# BERICHT
# ===========================================================================
$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine("# Vorschlaege vom $(Get-Date -Format 'dd.MM.yyyy HH:mm')")
[void]$sb.AppendLine()
[void]$sb.AppendLine("Grundlage: $($tracks.Count) Titel, $($artists.Count) Kuenstler aus deiner SoundCloud-Bibliothek.")
[void]$sb.AppendLine()

if ($bandcampHits.Count -gt 0) {
    [void]$sb.AppendLine('## Auf Bandcamp verfuegbar (verlustfrei kaufbar)')
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('Dort gibt es FLAC, WAV und AIFF - die beste Qualitaet, die legal zu haben ist.')
    [void]$sb.AppendLine()
    foreach ($b in ($bandcampHits | Sort-Object Count -Descending)) {
        [void]$sb.AppendLine("- [$($b.Name)]($($b.Url)) - $($b.Count)x in deiner Bibliothek")
    }
    [void]$sb.AppendLine()
}

if ($originals.Count -gt 0) {
    [void]$sb.AppendLine('## Original-Download auf SoundCloud freigegeben')
    [void]$sb.AppendLine()
    foreach ($o in ($originals | Sort-Object -Property @{Expression='Lossless';Descending=$true}, Title)) {
        $q = if ($o.Lossless) { "**$($o.Ext)**, verlustfrei" } else { $o.Ext }
        [void]$sb.AppendLine("- [$($o.Title)]($($o.Url)) - $q")
    }
    [void]$sb.AppendLine()
}

if ($ccTracks.Count -gt 0) {
    [void]$sb.AppendLine('## Unter freier Lizenz')
    [void]$sb.AppendLine()
    foreach ($t in $ccTracks) {
        [void]$sb.AppendLine("- [$($t.uploader) - $($t.title)]($($t.url)) - ``$($t.license)``")
    }
    [void]$sb.AppendLine()
}

if ($newSources.Count -gt 0) {
    [void]$sb.AppendLine('## Moegliche neue Quellen')
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('| Kuenstler / Label | Likes | Genre | ø Laenge | Art |')
    [void]$sb.AppendLine('|---|---|---|---|---|')
    foreach ($s in $newSources) {
        $art = if ($s.IsSetLike) { 'Sets' } else { 'Einzeltracks' }
        [void]$sb.AppendLine("| [$($s.Name)]($($s.Url)) | $($s.Count) | $($s.Genre) | $($s.AvgMinutes) min | $art |")
    }
    [void]$sb.AppendLine()
}

Set-Content -Path $reportFile -Value $sb.ToString() -Encoding UTF8

Write-Host ''
Write-Host '--------------------------------------------------' -ForegroundColor White
Write-Host " Bericht: $reportFile" -ForegroundColor White
Write-Host '--------------------------------------------------' -ForegroundColor White
Write-Host ''
if ($applied -gt 0) {
    Write-Host " $applied neue Quellen aufgenommen. Holen mit:" -ForegroundColor Green
    Write-Host '   .\tools\dj-fetch.ps1 -All'
    Write-Host ''
}
