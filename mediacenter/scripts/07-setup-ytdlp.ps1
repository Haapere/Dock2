<#
.SYNOPSIS
    Installiert yt-dlp und ffmpeg - die Grundlage fuer das Herunterladen
    von DJ-Sets.

.DESCRIPTION
    yt-dlp ersetzt die fragilen Kodi-Add-ons fuer Mixcloud und SoundCloud
    durch ein einziges Werkzeug, das ueber tausend Plattformen abdeckt und
    woechentlich aktualisiert wird. Faellt eine Plattform aus, ist der Fix
    meist schon in der naechsten Version.

    ffmpeg wird von yt-dlp fuer das Zusammenfuehren getrennter Audiospuren
    und fuer Metadaten gebraucht.

    Installiert wird bevorzugt per winget. Fehlt winget, landen beide
    Programme als Einzeldateien in %LOCALAPPDATA%\KodiMediacenter\bin.

.PARAMETER Update
    Vorhandene Installation aktualisieren statt neu zu installieren.

.PARAMETER SetupSoundCloud
    Fuehrt durch das Hinterlegen der SoundCloud-Zugangsdaten, damit die
    256-kbit/s-Streams eines Go+-Abos genutzt werden koennen.

.EXAMPLE
    .\07-setup-ytdlp.ps1

.EXAMPLE
    .\07-setup-ytdlp.ps1 -SetupSoundCloud

.NOTES
    Als Administrator ausfuehren, wenn winget genutzt werden soll.
#>

[CmdletBinding()]
param(
    [switch] $Update,
    [switch] $SetupSoundCloud
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step  { param([string]$m) Write-Host "`n[*] $m" -ForegroundColor Cyan }
function Write-Ok    { param([string]$m) Write-Host "    [ok]   $m" -ForegroundColor Green }
function Write-Warn2 { param([string]$m) Write-Host "    [warn] $m" -ForegroundColor Yellow }
function Write-Fail  { param([string]$m) Write-Host "    [fehl] $m" -ForegroundColor Red }

$binDir = Join-Path $env:LOCALAPPDATA 'KodiMediacenter\bin'
$cfgDir = Join-Path $env:LOCALAPPDATA 'KodiMediacenter'

Write-Host ""
Write-Host "=== yt-dlp und ffmpeg einrichten ===" -ForegroundColor White

function Find-Tool {
    param([string]$Name)
    $cmd = Get-Command "$Name.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $local = Join-Path $binDir "$Name.exe"
    if (Test-Path $local) { return $local }
    return $null
}

# ===========================================================================
# yt-dlp
# ===========================================================================
Write-Step 'yt-dlp'

$ytdlp = Find-Tool 'yt-dlp'

if ($ytdlp -and -not $Update) {
    $v = & $ytdlp --version 2>$null
    Write-Ok "bereits vorhanden: $ytdlp (Version $v)"
} else {
    $installed = $false

    if (Get-Command winget.exe -ErrorAction SilentlyContinue) {
        try {
            $action = if ($Update) { 'upgrade' } else { 'install' }
            & winget.exe $action --id 'yt-dlp.yt-dlp' --exact --silent `
                --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189 -or $LASTEXITCODE -eq -1978335212) {
                Write-Ok 'ueber winget eingerichtet'
                $installed = $true
            } else {
                Write-Warn2 "winget Exitcode $LASTEXITCODE - weiche auf Direktdownload aus"
            }
        } catch {
            Write-Warn2 "winget: $($_.Exception.Message)"
        }
    }

    if (-not $installed) {
        if (-not (Test-Path $binDir)) { New-Item -ItemType Directory -Path $binDir -Force | Out-Null }
        $target = Join-Path $binDir 'yt-dlp.exe'
        $url    = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe'

        try {
            $pb = $ProgressPreference; $ProgressPreference = 'SilentlyContinue'
            try { Invoke-WebRequest -Uri $url -OutFile $target -UseBasicParsing -TimeoutSec 300 }
            finally { $ProgressPreference = $pb }
            Write-Ok "heruntergeladen: $target"
            $installed = $true
        } catch {
            Write-Fail "Download fehlgeschlagen: $($_.Exception.Message)"
        }
    }

    $ytdlp = Find-Tool 'yt-dlp'
}

if ($ytdlp) {
    # yt-dlp aktualisiert sich selbst - das ist der Hauptgrund fuer seine Robustheit
    if ($Update) {
        Write-Host '    Selbstaktualisierung ...' -ForegroundColor DarkGray
        try { & $ytdlp -U 2>&1 | ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray } } catch { }
    }
    $v = & $ytdlp --version 2>$null
    Write-Ok "yt-dlp einsatzbereit (Version $v)"
} else {
    Write-Fail 'yt-dlp konnte nicht eingerichtet werden.'
    return
}

# ===========================================================================
# ffmpeg
# ===========================================================================
Write-Step 'ffmpeg'

$ffmpeg = Find-Tool 'ffmpeg'

if ($ffmpeg -and -not $Update) {
    Write-Ok "bereits vorhanden: $ffmpeg"
} else {
    $done = $false

    if (Get-Command winget.exe -ErrorAction SilentlyContinue) {
        try {
            $action = if ($Update) { 'upgrade' } else { 'install' }
            & winget.exe $action --id 'Gyan.FFmpeg' --exact --silent `
                --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189 -or $LASTEXITCODE -eq -1978335212) {
                Write-Ok 'ueber winget eingerichtet'
                $done = $true
            }
        } catch {
            Write-Warn2 "winget: $($_.Exception.Message)"
        }
    }

    if (-not $done) {
        Write-Warn2 'ffmpeg nicht automatisch installiert.'
        Write-Warn2 'Ohne ffmpeg funktioniert yt-dlp eingeschraenkt: getrennte Audiospuren'
        Write-Warn2 'lassen sich nicht zusammenfuehren und Metadaten nicht einbetten.'
        Write-Warn2 'Manuell: https://www.gyan.dev/ffmpeg/builds/  (Release essentials)'
        Write-Warn2 "Die ffmpeg.exe daraus nach $binDir kopieren."
    }
}

# PATH ergaenzen, damit yt-dlp das lokale ffmpeg findet
if (Test-Path $binDir) {
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($userPath -notlike "*$binDir*") {
        [Environment]::SetEnvironmentVariable('Path', "$userPath;$binDir", 'User')
        Write-Ok "$binDir zum Benutzer-PATH hinzugefuegt (wirkt in neuen Fenstern)"
    }
}

# ===========================================================================
# SoundCloud-Zugang
# ===========================================================================
if ($SetupSoundCloud) {
    Write-Step 'SoundCloud Go+ einrichten'

    Write-Host @"

    Mit einem Go+-Abo liefert SoundCloud 256 kbit/s AAC statt der sonst
    ueblichen 128 kbit/s MP3. yt-dlp kann diese Streams nutzen, braucht dafuer
    aber deine Anmeldung. Es gibt zwei Wege:

    Weg A - Browser-Cookies (einfach, haelt aber nur solange die Sitzung lebt)
      Du bleibst in Chrome/Edge/Firefox bei SoundCloud angemeldet, yt-dlp liest
      die Cookies direkt aus dem Browser. Nichts zu hinterlegen.

    Weg B - OAuth-Token (stabiler, haelt Monate)
      1. soundcloud.com im Browser oeffnen und anmelden
      2. F12 druecken -> Reiter "Netzwerkanalyse" / "Network"
      3. Seite neu laden, im Filter "api-v2" eintippen
      4. Eine beliebige Anfrage anklicken -> Abschnitt "Anfrageheader"
      5. Die Zeile "Authorization: OAuth 2-xxxxx-..." suchen
      6. Nur den Teil NACH "OAuth " kopieren

"@ -ForegroundColor Gray

    $choice = Read-Host '    Welchen Weg? (A/B/ueberspringen mit Enter)'

    if (-not (Test-Path $cfgDir)) { New-Item -ItemType Directory -Path $cfgDir -Force | Out-Null }
    $scFile = Join-Path $cfgDir 'soundcloud.json'

    if ($choice -match '^[Aa]') {
        $browser = Read-Host '    Welcher Browser? (chrome/edge/firefox)'
        if ($browser -notmatch '^(chrome|edge|firefox|brave|vivaldi|opera)$') {
            Write-Warn2 "Unbekannter Browser '$browser' - bitte einen der genannten Namen verwenden."
        } else {
            @{ method = 'cookies'; browser = $browser.ToLower() } |
                ConvertTo-Json | Set-Content -Path $scFile -Encoding UTF8
            Write-Ok "Hinterlegt: Cookies aus $browser"
        }
    }
    elseif ($choice -match '^[Bb]') {
        $token = Read-Host '    OAuth-Token einfuegen'
        $token = $token.Trim()
        if ($token -match '^OAuth\s+') { $token = $token -replace '^OAuth\s+', '' }

        if ([string]::IsNullOrWhiteSpace($token)) {
            Write-Warn2 'Kein Token eingegeben - uebersprungen.'
        } else {
            @{ method = 'oauth'; token = $token } |
                ConvertTo-Json | Set-Content -Path $scFile -Encoding UTF8

            # Datei auf den aktuellen Benutzer beschraenken - das Token ist ein
            # vollwertiger Kontozugang
            try {
                $acl = Get-Acl $scFile
                $acl.SetAccessRuleProtection($true, $false)
                $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
                    "$env:USERDOMAIN\$env:USERNAME", 'FullControl', 'Allow')
                $acl.SetAccessRule($rule)
                Set-Acl -Path $scFile -AclObject $acl
                Write-Ok 'Token hinterlegt, Datei auf dein Benutzerkonto beschraenkt'
            } catch {
                Write-Ok 'Token hinterlegt'
                Write-Warn2 "Dateirechte nicht eingeschraenkt: $($_.Exception.Message)"
            }

            Write-Warn2 'Das Token ist ein vollwertiger Kontozugang - nicht weitergeben.'
            Write-Warn2 'Bei Passwortwechsel oder Abmeldung wird es ungueltig; dann erneut hinterlegen.'
        }
    }
    else {
        Write-Warn2 'Uebersprungen. SoundCloud laeuft dann mit 128 kbit/s.'
    }
}

Write-Host ''
Write-Host 'Naechster Schritt:' -ForegroundColor White
Write-Host '  .\tools\dj-fetch.ps1 -List           Quellen anzeigen'
Write-Host '  .\tools\dj-fetch.ps1 -Source "HOER"  ein Set holen'
Write-Host '  .\tools\dj-fetch.ps1 -All            alle Quellen durchgehen'
Write-Host ''
Write-Host 'Hintergrund: docs\07-dj-sets.md' -ForegroundColor White
Write-Host ''
