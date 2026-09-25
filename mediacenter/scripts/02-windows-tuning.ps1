<#
.SYNOPSIS
    Bereitet Windows 11 fuer den Dauerbetrieb als Headless-Mediencenter vor.

.DESCRIPTION
    Aendert ausschliesslich Einstellungen, die fuer einen stabilen
    Streaming-Dauerbetrieb noetig sind:

      1. Energie      - kein Standby, kein Ruhezustand, kein Fast Startup,
                        keine USB-Selektivsperre, Festplatte bleibt wach
      2. Netzwerk     - Energiesparmodus der Netzwerkadapter aus
                        (haeufigste Ursache fuer WLAN-Abrisse mitten im Set)
      3. Firewall     - Regeln fuer Kodi-Fernsteuerung im lokalen Netz
      4. Autostart    - Kodi startet automatisch mit Windows
      5. Sonstiges    - Benachrichtigungen/Fokus, damit nichts ueber Kodi poppt

    Was dieses Skript bewusst NICHT tut:
      * Keine automatische Anmeldung einrichten (Passwort im Klartext in der
        Registry). Dafuer siehe docs/03-headless-remote.md - dort ist der
        sichere Weg ueber Sysinternals Autologon beschrieben.
      * Keine Windows-Update-Einstellungen veraendern.

.PARAMETER SkipFirewall
    Firewall-Regeln nicht anlegen.

.PARAMETER SkipAutostart
    Keine Kodi-Autostart-Verknuepfung anlegen.

.PARAMETER RemoteSubnet
    Subnetz, aus dem die Fernsteuerung erlaubt wird.
    Standard "LocalSubnet" (nur eigenes Heimnetz - empfohlen).

.PARAMETER WhatIf
    Zeigt nur an, was geaendert wuerde.

.EXAMPLE
    .\02-windows-tuning.ps1

.EXAMPLE
    .\02-windows-tuning.ps1 -SkipAutostart -RemoteSubnet 192.168.1.0/24

.NOTES
    Als Administrator ausfuehren.
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch] $SkipFirewall,
    [switch] $SkipAutostart,
    [string] $RemoteSubnet = 'LocalSubnet'
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

function Invoke-Powercfg {
    param([string[]]$Arguments, [string]$Label)
    try {
        $out = & powercfg.exe @Arguments 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($out -join ' ') }
        Write-Ok $Label
    } catch {
        Write-Warn2 "$Label fehlgeschlagen: $($_.Exception.Message)"
    }
}

Assert-Admin
Write-Host ""
Write-Host "=== Windows-Tuning fuer Kodi-Dauerbetrieb ===" -ForegroundColor White

# ===========================================================================
# 1. ENERGIE
# ===========================================================================
Write-Step 'Energieoptionen'

if ($PSCmdlet.ShouldProcess('Energieplan', 'Hoechstleistung aktivieren')) {
    # GUID des Plans "Hoechstleistung" ist auf allen Windows-Installationen gleich
    $highPerf = '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c'
    $schemes  = (& powercfg.exe /list) -join "`n"
    if ($schemes -notmatch $highPerf) {
        # Plan ist auf manchen Systemen ausgeblendet - aus der Vorlage duplizieren
        & powercfg.exe -duplicatescheme $highPerf | Out-Null
    }
    Invoke-Powercfg -Arguments @('/setactive', $highPerf) -Label 'Energieplan "Hoechstleistung" aktiv'
}

if ($PSCmdlet.ShouldProcess('Standby/Ruhezustand', 'deaktivieren')) {
    Invoke-Powercfg -Arguments @('/change', 'standby-timeout-ac', '0')     -Label 'Energiesparmodus: nie'
    Invoke-Powercfg -Arguments @('/change', 'hibernate-timeout-ac', '0')   -Label 'Ruhezustand: nie'
    Invoke-Powercfg -Arguments @('/change', 'disk-timeout-ac', '0')        -Label 'Festplatte: bleibt wach'
    # Monitor darf ruhig abschalten - das Bild wird im Headless-Betrieb nicht gebraucht
    Invoke-Powercfg -Arguments @('/change', 'monitor-timeout-ac', '15')    -Label 'Bildschirm: nach 15 min aus'
}

if ($PSCmdlet.ShouldProcess('Ruhezustandsdatei', 'deaktivieren (schaltet auch Fast Startup ab)')) {
    Invoke-Powercfg -Arguments @('/hibernate', 'off') -Label 'Ruhezustand + Schnellstart deaktiviert'
}

if ($PSCmdlet.ShouldProcess('USB-Selektivsperre', 'deaktivieren')) {
    # Wichtig fuer den USB-C DAC: sonst schlaeft der DAC ein und klickt beim Aufwachen
    $subUsb  = '2a737441-1930-4402-8d77-b2bebba308a3'
    $setting = '48e6b7a6-50f5-4782-a5d4-53bb8f07e226'
    Invoke-Powercfg -Arguments @('/setacvalueindex', 'SCHEME_CURRENT', $subUsb, $setting, '0') -Label 'USB-Selektivsperre aus'
    Invoke-Powercfg -Arguments @('/setactive', 'SCHEME_CURRENT') -Label 'Energieplan neu angewendet'
}

# ===========================================================================
# 2. NETZWERK
# ===========================================================================
Write-Step 'Netzwerkadapter - Energiesparmodus'

try {
    $adapters = Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' }
    if (-not $adapters) { Write-Warn2 'Kein aktiver Netzwerkadapter gefunden.' }

    foreach ($a in $adapters) {
        if ($PSCmdlet.ShouldProcess($a.Name, 'Energiesparmodus abschalten')) {
            try {
                Disable-NetAdapterPowerManagement -Name $a.Name -ErrorAction Stop -Confirm:$false
                Write-Ok "$($a.Name): Energieverwaltung aus"
            } catch {
                # Manche Treiber (v. a. einfache WLAN-Chips) unterstuetzen das Cmdlet nicht
                Write-Warn2 "$($a.Name): $($_.Exception.Message)"
                Write-Warn2 "  Manuell: Geraete-Manager -> Adapter -> Energieverwaltung -> Haken entfernen"
            }
        }
    }
} catch {
    Write-Warn2 "Netzwerkadapter konnten nicht gelesen werden: $($_.Exception.Message)"
}

# WLAN: Energiesparmodus des Funkmoduls auf Hoechstleistung
if ($PSCmdlet.ShouldProcess('WLAN-Energiesparmodus', 'auf Hoechstleistung')) {
    $subWifi = '19cbb8fa-5279-450e-9fac-8a3d5fedd0c1'
    $setWifi = '12bbebe6-58d6-4636-95bb-3217ef867c1a'
    Invoke-Powercfg -Arguments @('/setacvalueindex', 'SCHEME_CURRENT', $subWifi, $setWifi, '0') -Label 'WLAN: Hoechstleistung'
    Invoke-Powercfg -Arguments @('/setactive', 'SCHEME_CURRENT') -Label 'Energieplan neu angewendet'
}

# ===========================================================================
# 3. FIREWALL
# ===========================================================================
if (-not $SkipFirewall) {
    Write-Step 'Firewall-Regeln fuer die Kodi-Fernsteuerung'

    $rules = @(
        @{ Name = 'Kodi Webserver (HTTP/JSON-RPC)'; Port = 8080; Proto = 'TCP' },
        @{ Name = 'Kodi JSON-RPC (TCP)';            Port = 9090; Proto = 'TCP' },
        @{ Name = 'Kodi EventServer';               Port = 9777; Proto = 'UDP' },
        @{ Name = 'Kodi Zeroconf/mDNS';             Port = 5353; Proto = 'UDP' },
        @{ Name = 'Kodi UPnP';                      Port = 1900; Proto = 'UDP' }
    )

    foreach ($r in $rules) {
        $ruleName = "Kodi Mediacenter - $($r.Name)"
        if ($PSCmdlet.ShouldProcess($ruleName, 'Firewall-Regel anlegen')) {
            try {
                Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue |
                    Remove-NetFirewallRule -ErrorAction SilentlyContinue

                New-NetFirewallRule -DisplayName $ruleName `
                    -Direction Inbound -Action Allow `
                    -Protocol $r.Proto -LocalPort $r.Port `
                    -RemoteAddress $RemoteSubnet `
                    -Profile Private,Domain `
                    -Description 'Angelegt vom Kodi-Mediencenter-Setup' | Out-Null

                Write-Ok "$($r.Proto)/$($r.Port) freigegeben fuer $RemoteSubnet"
            } catch {
                Write-Fail "${ruleName}: $($_.Exception.Message)"
            }
        }
    }
    Write-Warn2 'Regeln gelten nur fuer Profile "Privat" und "Domaene" - das Heimnetz muss in Windows als "Privates Netzwerk" eingestuft sein.'
}

# ===========================================================================
# 4. AUTOSTART
# ===========================================================================
if (-not $SkipAutostart) {
    Write-Step 'Kodi-Autostart'

    $kodiCandidates = @(
        "$env:ProgramFiles\Kodi\kodi.exe",
        "${env:ProgramFiles(x86)}\Kodi\kodi.exe",
        "$env:LOCALAPPDATA\Programs\Kodi\kodi.exe"
    )
    $kodiExe = $kodiCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

    if (-not $kodiExe) {
        Write-Warn2 'kodi.exe nicht gefunden - Autostart uebersprungen.'
        Write-Warn2 'Erst scripts\03-install-kodi.ps1 ausfuehren, danach dieses Skript erneut starten.'
    } else {
        $startupDir = [Environment]::GetFolderPath('Startup')
        $lnkPath    = Join-Path $startupDir 'Kodi.lnk'

        if ($PSCmdlet.ShouldProcess($lnkPath, 'Autostart-Verknuepfung anlegen')) {
            try {
                $shell = New-Object -ComObject WScript.Shell
                $lnk   = $shell.CreateShortcut($lnkPath)
                $lnk.TargetPath       = $kodiExe
                $lnk.WorkingDirectory = Split-Path $kodiExe -Parent
                $lnk.Description      = 'Kodi Mediencenter - Autostart'
                $lnk.Save()
                Write-Ok "Autostart eingerichtet: $lnkPath"
                Write-Ok "Ziel: $kodiExe"
            } catch {
                Write-Fail "Verknuepfung fehlgeschlagen: $($_.Exception.Message)"
            }
        }
    }
}

# ===========================================================================
# 5. STOERQUELLEN
# ===========================================================================
Write-Step 'Stoerende Einblendungen abschalten'

if ($PSCmdlet.ShouldProcess('Benachrichtigungen', 'deaktivieren')) {
    try {
        $key = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\PushNotifications'
        if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }
        New-ItemProperty -Path $key -Name 'ToastEnabled' -PropertyType DWord -Value 0 -Force | Out-Null
        Write-Ok 'Toast-Benachrichtigungen aus (gilt fuer den aktuellen Benutzer)'
    } catch {
        Write-Warn2 "Benachrichtigungen: $($_.Exception.Message)"
    }
}

Write-Host ''
Write-Host 'Fertig. Empfohlene Reihenfolge:' -ForegroundColor White
Write-Host '  1. 01-windows-audio.ps1      (Exklusivmodus)'
Write-Host '  2. 02-windows-tuning.ps1     (dieses Skript)'
Write-Host '  3. 03-install-kodi.ps1       (Kodi installieren)'
Write-Host '  4. 04-deploy-kodi-config.ps1 (advancedsettings + Webserver)'
Write-Host '  5. 05-apply-audio-settings.ps1 (Audio/Passthrough per JSON-RPC)'
Write-Host '  6. 06-install-addons.ps1     (Add-on-Quellen + Favoriten)'
Write-Host ''
