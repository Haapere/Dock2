<#
.SYNOPSIS
    Bereitet die Add-on-Landschaft vor und legt die Direkt-Streams an.

.DESCRIPTION
    Was dieses Skript VOLLSTAENDIG automatisch erledigt:
      * favourites.xml mit allen FLAC-/Radio-Streams (Zugriff per Yatse)
      * einen Ordner mit STRM-Dateien, den Kodi als Musikquelle einbinden kann
      * die Musikquelle in sources.xml eintragen
      * Erreichbarkeitspruefung aller Stream-URLs

    Was NICHT automatisch geht - und warum:
      Kodi bietet keine Schnittstelle, um ein Add-on aus einem Repository zu
      installieren. Ein Add-on einfach nach %APPDATA%\Kodi\addons\ zu entpacken
      funktioniert bei Plugins nur unzuverlaessig, weil Abhaengigkeiten
      (script.module.*) fehlen und Kodi sie dann deaktiviert.
      Der ehrliche Weg sind rund fuenf Minuten Klickarbeit in der Kodi-GUI.
      Dieses Skript bereitet alles dafuer vor: es laedt die noetigen ZIPs
      herunter, legt sie an einem Ort ab und druckt die exakte Klickfolge.

.PARAMETER SkipDownload
    Keine ZIPs herunterladen, nur Favoriten und STRM-Dateien anlegen.

.PARAMETER DownloadDir
    Ablage fuer die ZIPs. Standard: %USERPROFILE%\Downloads\kodi-addons

.PARAMETER StrmDir
    Ablage fuer die STRM-Dateien. Standard: %USERPROFILE%\Music\Radio-Streams

.EXAMPLE
    .\06-install-addons.ps1

.NOTES
    Kodi sollte fuer favourites.xml und sources.xml beendet sein.
#>

[CmdletBinding()]
param(
    [switch] $SkipDownload,
    [string] $DownloadDir,
    [string] $StrmDir
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step  { param([string]$m) Write-Host "`n[*] $m" -ForegroundColor Cyan }
function Write-Ok    { param([string]$m) Write-Host "    [ok]   $m" -ForegroundColor Green }
function Write-Warn2 { param([string]$m) Write-Host "    [warn] $m" -ForegroundColor Yellow }
function Write-Fail  { param([string]$m) Write-Host "    [fehl] $m" -ForegroundColor Red }

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir   = Split-Path $scriptDir -Parent
$srcFile   = Join-Path $rootDir 'addons\sources.json'

$homeDir = if ($env:USERPROFILE) { $env:USERPROFILE } else { [Environment]::GetFolderPath('UserProfile') }
if (-not $DownloadDir) { $DownloadDir = Join-Path $homeDir 'Downloads\kodi-addons' }
if (-not $StrmDir)     { $StrmDir     = Join-Path $homeDir 'Music\Radio-Streams' }
$userdata  = Join-Path $env:APPDATA 'Kodi\userdata'
$backupDir = Join-Path $env:ProgramData 'KodiMediacenter\backup'

if (-not (Test-Path $srcFile)) { throw "Quellenliste fehlt: $srcFile" }
$cfg = Get-Content $srcFile -Raw | ConvertFrom-Json

Write-Host ""
Write-Host "=== Add-ons und Direkt-Streams ===" -ForegroundColor White

if (Get-Process -Name 'kodi' -ErrorAction SilentlyContinue) {
    Write-Warn2 'Kodi laeuft. favourites.xml und sources.xml werden beim Beenden von Kodi ueberschrieben.'
    Write-Warn2 'Empfehlung: Kodi beenden und dieses Skript erneut starten.'
}

foreach ($d in @($userdata, $backupDir, $StrmDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

# ===========================================================================
# 1. STREAMS PRUEFEN
# ===========================================================================
Write-Step 'Pruefe Erreichbarkeit der Direkt-Streams'

$streams  = @($cfg.directStreams.items)
$reachable = @()

foreach ($s in $streams) {
    try {
        # Streams liefern kein Content-Length und enden nie - daher nur den
        # Anfang lesen und die Verbindung sofort wieder schliessen.
        $req = [System.Net.HttpWebRequest]::Create($s.url)
        $req.Method            = 'GET'
        $req.Timeout           = 8000
        $req.ReadWriteTimeout  = 8000
        $req.UserAgent         = 'Kodi/21.0'
        $req.AllowAutoRedirect = $true

        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $type = $resp.ContentType
        $resp.Close()

        if ($code -ge 200 -and $code -lt 400) {
            Write-Ok "$($s.name)  [$type]"
            $reachable += $s
        } else {
            Write-Warn2 "$($s.name) - HTTP $code"
        }
    } catch {
        Write-Warn2 "$($s.name) - nicht erreichbar: $($_.Exception.Message.Split([char]10)[0])"
        # Trotzdem anlegen: der Ausfall kann voruebergehend oder regional sein
        $reachable += $s
    }
}

# ===========================================================================
# 2. FAVORITEN
# ===========================================================================
Write-Step 'Lege favourites.xml an'

$favFile = Join-Path $userdata 'favourites.xml'

# Bestehende Favoriten einlesen und zusammenfuehren, nichts wegwerfen
$existing = @()
if (Test-Path $favFile) {
    Copy-Item $favFile (Join-Path $backupDir "favourites-$stamp.xml") -Force
    Write-Ok 'Vorhandene Favoriten gesichert'
    try {
        [xml]$oldDoc = Get-Content $favFile -Raw
        if ($oldDoc.favourites -and $oldDoc.favourites.favourite) {
            $existing = @($oldDoc.favourites.favourite)
        }
    } catch {
        Write-Warn2 "Bestehende favourites.xml nicht lesbar, wird ersetzt: $($_.Exception.Message)"
    }
}

$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
[void]$sb.AppendLine('<favourites>')

# Alte Eintraege uebernehmen, ausser sie stammen aus einem frueheren Lauf
$ourNames = $reachable | ForEach-Object { $_.name }
foreach ($e in $existing) {
    $n = $e.name
    if ($ourNames -contains $n) { continue }
    $inner = $e.InnerText
    [void]$sb.AppendLine("    <favourite name=""$([System.Security.SecurityElement]::Escape($n))"">$([System.Security.SecurityElement]::Escape($inner))</favourite>")
}

foreach ($s in $reachable) {
    $name = [System.Security.SecurityElement]::Escape($s.name)
    # Auch die URL maskieren: ein "&" in einem Query-String (?a=1&b=2) macht die
    # Datei sonst zu ungueltigem XML und Kodi verwirft dann ALLE Favoriten.
    $url  = [System.Security.SecurityElement]::Escape($s.url)
    # PlayMedia erwartet die URL in Anfuehrungszeichen; diese werden als Entity geschrieben
    $cmd  = "PlayMedia(&quot;$url&quot;)"
    [void]$sb.AppendLine("    <favourite name=""$name"">$cmd</favourite>")
}

[void]$sb.AppendLine('</favourites>')

Set-Content -Path $favFile -Value $sb.ToString() -Encoding UTF8
Write-Ok "$($reachable.Count) Favoriten geschrieben: $favFile"

try {
    [xml]$null = Get-Content $favFile -Raw
    Write-Ok 'XML-Syntax in Ordnung'
} catch {
    Write-Fail "favourites.xml ist ungueltig: $($_.Exception.Message)"
}

# ===========================================================================
# 3. STRM-DATEIEN
# ===========================================================================
Write-Step "Lege STRM-Dateien an: $StrmDir"

foreach ($s in $reachable) {
    # Dateinamen von Zeichen befreien, die Windows nicht erlaubt
    $safe = $s.name -replace '[\\/:*?"<>|]', '-'
    $file = Join-Path $StrmDir "$safe.strm"
    Set-Content -Path $file -Value $s.url -Encoding UTF8 -NoNewline
}
Write-Ok "$($reachable.Count) STRM-Dateien geschrieben"

# Kurze Erklaerung im Ordner hinterlassen
$readme = @"
Radio-Streams als STRM-Dateien
==============================

Jede .strm-Datei enthaelt nur eine Stream-URL. Kodi spielt sie wie eine
normale Musikdatei ab. Vorteil gegenueber Add-ons: funktioniert auch nach
Kodi-Updates weiter und ist in Yatse/Kore ganz normal durchsuchbar.

Einbinden in Kodi (falls nicht automatisch geschehen):
  Musik -> Dateien -> Videos/Musik hinzufuegen -> Durchsuchen
  -> $StrmDir  -> Name: "Radio-Streams" -> OK

Neuen Stream hinzufuegen:
  Textdatei mit der URL als einzigem Inhalt anlegen, Endung .strm.

Angelegt am $(Get-Date -Format 'yyyy-MM-dd HH:mm') vom Kodi-Mediencenter-Setup.
"@
Set-Content -Path (Join-Path $StrmDir '_LIESMICH.txt') -Value $readme -Encoding UTF8

# ===========================================================================
# 4. MUSIKQUELLE EINTRAGEN
# ===========================================================================
Write-Step 'Trage die Musikquelle in sources.xml ein'

$srcXml = Join-Path $userdata 'sources.xml'

if (Test-Path $srcXml) {
    Copy-Item $srcXml (Join-Path $backupDir "sources-$stamp.xml") -Force
    try {
        [xml]$doc = Get-Content $srcXml -Raw
    } catch {
        Write-Warn2 'sources.xml nicht lesbar, wird neu angelegt.'
        [xml]$doc = '<sources />'
    }
} else {
    [xml]$doc = '<sources />'
}

if (-not $doc.DocumentElement) {
    [xml]$doc = '<sources />'
}

$musicNode = $doc.SelectSingleNode('/sources/music')
if (-not $musicNode) {
    $musicNode = $doc.CreateElement('music')
    [void]$doc.DocumentElement.AppendChild($musicNode)
}

$already = $doc.SelectSingleNode("/sources/music/source[name='Radio-Streams']")
if ($already) {
    Write-Ok 'Quelle "Radio-Streams" ist bereits eingetragen'
} else {
    $source = $doc.CreateElement('source')

    $n = $doc.CreateElement('name');  $n.InnerText = 'Radio-Streams'
    $p = $doc.CreateElement('path');  $p.SetAttribute('pathversion', '1'); $p.InnerText = "$StrmDir\"
    $a = $doc.CreateElement('allowsharing'); $a.InnerText = 'true'

    [void]$source.AppendChild($n)
    [void]$source.AppendChild($p)
    [void]$source.AppendChild($a)
    [void]$musicNode.AppendChild($source)

    $doc.Save($srcXml)
    Write-Ok "Quelle angelegt: $srcXml"
}

# ===========================================================================
# 5. ADD-ON-ZIPS HERUNTERLADEN
# ===========================================================================
if (-not $SkipDownload) {
    Write-Step "Lade verfuegbare Add-on-Pakete nach $DownloadDir"

    if (-not (Test-Path $DownloadDir)) { New-Item -ItemType Directory -Path $DownloadDir -Force | Out-Null }

    $progressBackup   = $ProgressPreference
    $ProgressPreference = 'SilentlyContinue'

    try {
        foreach ($repo in $cfg.repositories) {
            $repoHome = $repo.homepage

            # Nur GitHub-Releases lassen sich zuverlaessig automatisch aufloesen
            if ($repoHome -notmatch 'github\.com/([^/]+)/([^/]+)') {
                Write-Warn2 "$($repo.name): automatischer Download nicht moeglich -> $repoHome"
                continue
            }

            $owner = $Matches[1]
            $name  = $Matches[2].TrimEnd('/')
            $api   = "https://api.github.com/repos/$owner/$name/releases/latest"

            try {
                $rel = Invoke-RestMethod -Uri $api -Headers @{ 'User-Agent' = 'kodi-setup' } -TimeoutSec 30

                $asset = $null
                if ($rel.PSObject.Properties.Name -contains 'assets' -and $rel.assets) {
                    $asset = $rel.assets | Where-Object { $_.name -like '*.zip' } | Select-Object -First 1
                }

                if ($asset) {
                    $target = Join-Path $DownloadDir $asset.name
                    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $target -UseBasicParsing -TimeoutSec 300
                    Write-Ok "$($repo.name): $($asset.name)"
                } elseif ($rel.PSObject.Properties.Name -contains 'zipball_url') {
                    Write-Warn2 "$($repo.name): kein fertiges ZIP im Release. Bitte von Hand holen: $repoHome/releases"
                } else {
                    Write-Warn2 "$($repo.name): keine Release-Dateien gefunden. $repoHome"
                }
            } catch {
                Write-Warn2 "$($repo.name): Download fehlgeschlagen ($($_.Exception.Message.Split([char]10)[0])). Manuell: $repoHome"
            }
        }
    } finally {
        $ProgressPreference = $progressBackup
    }
}

# ===========================================================================
# 6. ANLEITUNG
# ===========================================================================
Write-Host ''
Write-Host '===========================================================' -ForegroundColor White
Write-Host ' Restliche Schritte in der Kodi-Oberflaeche (ca. 5 Minuten)' -ForegroundColor White
Write-Host '===========================================================' -ForegroundColor White
Write-Host ''
Write-Host 'A) Unbekannte Quellen freischalten (nur einmal noetig)' -ForegroundColor White
Write-Host '   Einstellungen -> System -> Add-ons -> "Unbekannte Quellen" einschalten'
Write-Host ''
Write-Host 'B) Add-ons aus dem offiziellen Kodi-Repository:' -ForegroundColor White
foreach ($o in $cfg.official) {
    $flag = if ($o.required) { 'Pflicht ' } else { 'optional' }
    Write-Host ("   [{0}] {1}" -f $flag, $o.name)
    Write-Host ("              {0}" -f $o.install) -ForegroundColor DarkGray
}
Write-Host ''
Write-Host 'C) Add-ons aus ZIP-Dateien:' -ForegroundColor White
Write-Host "   Einstellungen -> Add-ons -> Aus ZIP-Datei installieren -> $DownloadDir"
foreach ($r in $cfg.repositories) {
    $risk = if ($r.PSObject.Properties.Name -contains 'risk') { " (Risiko: $($r.risk))" } else { '' }
    Write-Host ("   - {0}{1}" -f $r.name, $risk)
}
Write-Host ''
Write-Host 'D) YouTube auf hochwertiges Audio stellen:' -ForegroundColor White
Write-Host '   siehe addons\youtube-audio-hq.md'
Write-Host ''
Write-Host 'Die Radio-Streams laufen bereits jetzt - ohne jedes Add-on:' -ForegroundColor Green
Write-Host '   Kodi -> Favoriten, oder Yatse -> Favoriten'
Write-Host ''
