<#
.SYNOPSIS
    Rollt advancedsettings.xml aus und aktiviert den Kodi-Webserver
    (Voraussetzung fuer Yatse/Kore und fuer Skript 05).

.DESCRIPTION
    Kodi schreibt guisettings.xml beim Beenden komplett neu. Deshalb darf
    diese Datei nur bearbeitet werden, waehrend Kodi NICHT laeuft - das
    Skript prueft das und bricht sonst ab.

    Geaendert werden ausschliesslich die services.*-Schluessel:
      services.webserver / -port / -username / -password / -authentication
      services.esenabled / -esallinterfaces / -esport   (Fernsteuerung, Tastatur)
      services.zeroconf                                  (Auto-Erkennung durch Yatse)
      services.upnp / -upnpannounce                      (Netzwerkfreigabe)

    Alle uebrigen Einstellungen bleiben unberuehrt. Vor jeder Aenderung wird
    ein Backup angelegt.

.PARAMETER WebPassword
    Passwort fuer die Kodi-Fernsteuerung. Ohne Angabe wird ein zufaelliges
    erzeugt und angezeigt.

.PARAMETER WebUser
    Benutzername. Standard "kodi".

.PARAMETER WebPort
    Port des Kodi-Webservers. Standard 8080.

.PARAMETER ConfigDir
    Ordner mit advancedsettings.xml. Standard: ..\config relativ zum Skript.

.EXAMPLE
    .\04-deploy-kodi-config.ps1

.EXAMPLE
    .\04-deploy-kodi-config.ps1 -WebPassword 'MeinPasswort' -WebPort 8080

.NOTES
    SICHERHEITSHINWEIS: Kodi speichert dieses Passwort im Klartext in
    guisettings.xml - das ist eine Eigenheit von Kodi und nicht aenderbar.
    Verwende deshalb ein eigenes Passwort, das du nirgends sonst nutzt, und
    gib den Port nur im Heimnetz frei (niemals im Router weiterleiten).
#>

[CmdletBinding()]
param(
    [string] $WebPassword,
    [string] $WebUser = 'kodi',
    [ValidateRange(1024, 65535)]
    [int]    $WebPort = 8080,
    [string] $ConfigDir
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step  { param([string]$m) Write-Host "`n[*] $m" -ForegroundColor Cyan }
function Write-Ok    { param([string]$m) Write-Host "    [ok]   $m" -ForegroundColor Green }
function Write-Warn2 { param([string]$m) Write-Host "    [warn] $m" -ForegroundColor Yellow }
function Write-Fail  { param([string]$m) Write-Host "    [fehl] $m" -ForegroundColor Red }

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ConfigDir) { $ConfigDir = Join-Path (Split-Path $scriptDir -Parent) 'config' }

$userdata  = Join-Path $env:APPDATA 'Kodi\userdata'
$backupDir = Join-Path $env:ProgramData 'KodiMediacenter\backup'

Write-Host ""
Write-Host "=== Kodi-Konfiguration ausrollen ===" -ForegroundColor White

# ---------------------------------------------------------------------------
# Vorbedingungen
# ---------------------------------------------------------------------------
$running = Get-Process -Name 'kodi' -ErrorAction SilentlyContinue
if ($running) {
    Write-Fail 'Kodi laeuft gerade.'
    Write-Warn2 'Kodi beenden (nicht nur minimieren) und dieses Skript erneut starten.'
    Write-Warn2 'Grund: Kodi ueberschreibt guisettings.xml beim Beenden und wuerde die Aenderungen verwerfen.'
    return
}

if (-not (Test-Path $userdata)) {
    Write-Warn2 "Profilordner fehlt: $userdata"
    Write-Warn2 'Lege ihn an. Falls Kodi noch nie gestartet wurde, bitte erst 03-install-kodi.ps1 ausfuehren.'
    New-Item -ItemType Directory -Path $userdata -Force | Out-Null
}

if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir -Force | Out-Null }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

# ---------------------------------------------------------------------------
# 1. advancedsettings.xml
# ---------------------------------------------------------------------------
Write-Step 'advancedsettings.xml'

$srcAdv = Join-Path $ConfigDir 'advancedsettings.xml'
$dstAdv = Join-Path $userdata  'advancedsettings.xml'

if (-not (Test-Path $srcAdv)) {
    Write-Fail "Quelldatei fehlt: $srcAdv"
    return
}

if (Test-Path $dstAdv) {
    $bak = Join-Path $backupDir "advancedsettings-$stamp.xml"
    Copy-Item $dstAdv $bak -Force
    Write-Ok "Vorherige Datei gesichert: $bak"
}

Copy-Item $srcAdv $dstAdv -Force
Write-Ok "Kopiert nach: $dstAdv"

# Syntaxpruefung - eine kaputte advancedsettings.xml wird von Kodi still ignoriert
try {
    [xml]$null = Get-Content $dstAdv -Raw
    Write-Ok 'XML-Syntax in Ordnung'
} catch {
    Write-Fail "advancedsettings.xml ist kein gueltiges XML: $($_.Exception.Message)"
    return
}

# ---------------------------------------------------------------------------
# 2. guisettings.xml - Webserver und Fernsteuerung
# ---------------------------------------------------------------------------
Write-Step 'guisettings.xml - Fernsteuerung aktivieren'

if (-not $WebPassword) {
    # 16 Zeichen aus einem Alphabet ohne leicht verwechselbare Zeichen
    $alphabet = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    $bytes    = New-Object byte[] 16
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $WebPassword = -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
    Write-Warn2 'Kein Passwort uebergeben - es wurde eines erzeugt (siehe Zusammenfassung unten).'
}

$gui = Join-Path $userdata 'guisettings.xml'

if (Test-Path $gui) {
    $bak = Join-Path $backupDir "guisettings-$stamp.xml"
    Copy-Item $gui $bak -Force
    Write-Ok "Vorherige Datei gesichert: $bak"

    try {
        [xml]$doc = Get-Content $gui -Raw
    } catch {
        Write-Fail "guisettings.xml ist beschaedigt: $($_.Exception.Message)"
        Write-Warn2 "Backup liegt unter $bak - im Zweifel Datei loeschen, Kodi starten und erneut versuchen."
        return
    }
} else {
    Write-Warn2 'guisettings.xml existiert noch nicht - lege eine minimale Datei an.'
    [xml]$doc = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><settings version="2" />'
}

if (-not $doc.DocumentElement -or $doc.DocumentElement.Name -ne 'settings') {
    Write-Fail 'Unerwartete Struktur in guisettings.xml (Wurzelelement ist nicht <settings>).'
    return
}

<#
    Setzt ein <setting id="..."> im Dokument. Legt es an, falls es fehlt.
    Das Attribut default="true" wird entfernt - sonst behandelt Kodi den Wert
    weiterhin als Vorgabe und ueberschreibt ihn beim naechsten Start.
#>
function Set-GuiSetting {
    param([xml]$Doc, [string]$Id, [string]$Value)

    $node = $Doc.SelectSingleNode("/settings/setting[@id='$Id']")
    if (-not $node) {
        $node = $Doc.CreateElement('setting')
        $node.SetAttribute('id', $Id)
        [void]$Doc.DocumentElement.AppendChild($node)
    }
    if ($node.HasAttribute('default')) { $node.RemoveAttribute('default') }
    $node.InnerText = $Value
    Write-Ok "$Id = $(if ($Id -like '*password*') { '********' } else { $Value })"
}

$settings = [ordered]@{
    'services.webserver'               = 'true'
    'services.webserverport'           = "$WebPort"
    'services.webserverusername'       = $WebUser
    'services.webserverpassword'       = $WebPassword
    'services.webserverauthentication' = 'true'
    'services.webskin'                 = 'webinterface.default'
    'services.esenabled'               = 'true'
    'services.esallinterfaces'         = 'true'
    'services.esport'                  = '9777'
    'services.zeroconf'                = 'true'
    'services.upnp'                    = 'true'
    'services.upnpannounce'            = 'true'
    'services.devicename'              = 'Mediencenter'
}

foreach ($kv in $settings.GetEnumerator()) {
    Set-GuiSetting -Doc $doc -Id $kv.Key -Value $kv.Value
}

try {
    $doc.Save($gui)
    Write-Ok "Gespeichert: $gui"
} catch {
    Write-Fail "Speichern fehlgeschlagen: $($_.Exception.Message)"
    return
}

# ---------------------------------------------------------------------------
# 3. Zugangsdaten ablegen
# ---------------------------------------------------------------------------
Write-Step 'Zugangsdaten sichern'

$credDir  = Join-Path $env:ProgramData 'KodiMediacenter'
$credFile = Join-Path $credDir 'fernsteuerung.txt'

$ips = @()
try {
    $ips = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' }).IPAddress
} catch { }
$ipText = if ($ips) { $ips -join ', ' } else { '<IP des Mini-PCs>' }

$content = @"
Kodi-Fernsteuerung - Zugangsdaten
Angelegt: $(Get-Date -Format 'yyyy-MM-dd HH:mm')

Host      : $ipText
Port      : $WebPort
Benutzer  : $WebUser
Passwort  : $WebPassword

Weboberflaeche : http://$(($ips | Select-Object -First 1)):$WebPort
JSON-RPC (TCP) : Port 9090
EventServer    : Port 9777 (UDP)

In Yatse / Kore eintragen. Das Passwort steht in Kodi zwangslaeufig im
Klartext in guisettings.xml - diesen Port niemals im Router nach aussen
weiterleiten.
"@

if (-not (Test-Path $credDir)) { New-Item -ItemType Directory -Path $credDir -Force | Out-Null }
Set-Content -Path $credFile -Value $content -Encoding UTF8
Write-Ok "Abgelegt unter: $credFile"

Write-Host ''
Write-Host '--------------------------------------------------' -ForegroundColor White
Write-Host ' Zugangsdaten fuer Yatse / Kore' -ForegroundColor White
Write-Host '--------------------------------------------------' -ForegroundColor White
Write-Host "  Host     : $ipText"
Write-Host "  Port     : $WebPort"
Write-Host "  Benutzer : $WebUser"
Write-Host "  Passwort : $WebPassword" -ForegroundColor Yellow
Write-Host '--------------------------------------------------' -ForegroundColor White
Write-Host ''
Write-Host 'Naechste Schritte:' -ForegroundColor White
Write-Host '  1. Kodi starten (Autostart oder von Hand)'
Write-Host '  2. .\05-apply-audio-settings.ps1  ausfuehren - setzt Audio + Passthrough'
Write-Host ''
