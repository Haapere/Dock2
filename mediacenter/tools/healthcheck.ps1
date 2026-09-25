<#
.SYNOPSIS
    Prueft das komplette Setup und meldet, was noch fehlt.

.DESCRIPTION
    Geht alle Punkte durch, die erfahrungsgemaess Aussetzer oder schlechten
    Klang verursachen, und gibt am Ende eine Liste konkreter Massnahmen aus.
    Aendert nichts.

.EXAMPLE
    .\healthcheck.ps1
#>

[CmdletBinding()]
param(
    [string] $KodiHost = 'localhost',
    [int]    $Port,
    [string] $User,
    [string] $Password
)

$ErrorActionPreference = 'Continue'
Set-StrictMode -Version Latest

$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir  = Split-Path $toolsDir -Parent
$modPath  = Join-Path $toolsDir 'KodiRpc.psm1'
$userdata = Join-Path $env:APPDATA 'Kodi\userdata'

$script:Findings = @()

function Add-Finding {
    param(
        [ValidateSet('ok', 'warn', 'fail')] [string] $Level,
        [string] $Area,
        [string] $Message,
        [string] $Fix = ''
    )
    $script:Findings += [pscustomobject]@{ Level = $Level; Area = $Area; Message = $Message; Fix = $Fix }

    $colour = switch ($Level) { 'ok' { 'Green' } 'warn' { 'Yellow' } 'fail' { 'Red' } }
    $symbol = switch ($Level) { 'ok' { 'ok  ' } 'warn' { 'warn' } 'fail' { 'FEHL' } }
    Write-Host ("  [{0}] {1,-16} {2}" -f $symbol, $Area, $Message) -ForegroundColor $colour
}

Write-Host ""
Write-Host "=== Systempruefung Hi-Res-Mediencenter ===" -ForegroundColor White
Write-Host ""

# ---------------------------------------------------------------------------
# 1. Windows-Audio
# ---------------------------------------------------------------------------
Write-Host "-- Windows-Audio" -ForegroundColor Cyan

$renderRoot = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render'
$pkeyExcl   = '{b3f8fa53-0004-438e-9003-51a46e139bfc},3'
$pkeySysFx  = '{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5'
$pkeyName   = '{a45c254e-df1c-4efd-8020-67d146a850e0},14'

if (Test-Path $renderRoot) {
    $activeCount = 0
    $exclCount   = 0

    foreach ($sub in Get-ChildItem $renderRoot) {
        $state = 0
        try { $state = (Get-ItemProperty $sub.PSPath -Name DeviceState -ErrorAction Stop).DeviceState } catch { }
        if ($state -ne 1) { continue }
        $activeCount++

        $props = Join-Path $sub.PSPath 'Properties'
        $name = '(unbenannt)'
        try { $name = (Get-ItemProperty $props -Name $pkeyName -ErrorAction Stop).$pkeyName } catch { }

        $excl = $null
        try { $excl = (Get-ItemProperty $props -Name $pkeyExcl -ErrorAction Stop).$pkeyExcl } catch { }

        $sysfx = $null
        try { $sysfx = (Get-ItemProperty $props -Name $pkeySysFx -ErrorAction Stop).$pkeySysFx } catch { }

        if ($excl -eq 1) {
            $exclCount++
            Add-Finding -Level ok -Area 'Exklusivmodus' -Message "$name"
        } else {
            Add-Finding -Level fail -Area 'Exklusivmodus' -Message "$name - Exklusivmodus NICHT erlaubt" `
                -Fix "scripts\01-windows-audio.ps1 -DeviceFilter `"$name`" ausfuehren"
        }

        if ($sysfx -ne 1) {
            Add-Finding -Level warn -Area 'Klangeffekte' -Message "$name - Signalverbesserungen evtl. aktiv" `
                -Fix 'mmsys.cpl -> Geraet -> Eigenschaften -> Erweitert/Verbesserungen -> alle deaktivieren'
        }
    }

    if ($activeCount -eq 0) {
        Add-Finding -Level fail -Area 'Audiogeraet' -Message 'Kein aktives Wiedergabegeraet' `
            -Fix 'AV-Receiver einschalten und HDMI pruefen'
    }
} else {
    Add-Finding -Level fail -Area 'Audiogeraet' -Message 'MMDevices-Registry nicht lesbar'
}

# ---------------------------------------------------------------------------
# 2. Energie
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "-- Energie und Netzwerk" -ForegroundColor Cyan

try {
    $standby = (& powercfg.exe /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE) -join "`n"
    if ($standby -match '(?s)Wechselstrom.*?0x00000000' -or $standby -match '(?s)AC Power Setting Index:\s*0x00000000') {
        Add-Finding -Level ok -Area 'Energiesparen' -Message 'Standby im Netzbetrieb deaktiviert'
    } else {
        Add-Finding -Level warn -Area 'Energiesparen' -Message 'Standby moeglicherweise noch aktiv' `
            -Fix 'scripts\02-windows-tuning.ps1 ausfuehren'
    }
} catch {
    Add-Finding -Level warn -Area 'Energiesparen' -Message 'Energieplan nicht lesbar'
}

$hiberfil = Join-Path $env:SystemDrive 'hiberfil.sys'
if (Test-Path $hiberfil) {
    Add-Finding -Level warn -Area 'Schnellstart' -Message 'hiberfil.sys vorhanden - Schnellstart evtl. aktiv' `
        -Fix 'powercfg /hibernate off  (in scripts\02-windows-tuning.ps1 enthalten)'
} else {
    Add-Finding -Level ok -Area 'Schnellstart' -Message 'Ruhezustand/Schnellstart deaktiviert'
}

try {
    $rules = Get-NetFirewallRule -DisplayName 'Kodi Mediacenter*' -ErrorAction SilentlyContinue
    if ($rules) {
        Add-Finding -Level ok -Area 'Firewall' -Message "$(@($rules).Count) Regeln vorhanden"
    } else {
        Add-Finding -Level warn -Area 'Firewall' -Message 'Keine Kodi-Firewallregeln gefunden' `
            -Fix 'scripts\02-windows-tuning.ps1 ausfuehren'
    }
} catch { }

try {
    $profiles = Get-NetConnectionProfile -ErrorAction Stop
    $public   = $profiles | Where-Object { $_.NetworkCategory -eq 'Public' }
    if ($public) {
        Add-Finding -Level warn -Area 'Netzwerkprofil' -Message "Netzwerk '$($public[0].Name)' ist als OEFFENTLICH eingestuft" `
            -Fix 'Einstellungen -> Netzwerk -> Eigenschaften -> auf "Privates Netzwerk" umstellen, sonst blockt die Firewall Yatse'
    } else {
        Add-Finding -Level ok -Area 'Netzwerkprofil' -Message 'Netzwerk ist privat'
    }
} catch { }

# ---------------------------------------------------------------------------
# 3. Kodi-Dateien
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "-- Kodi-Konfiguration" -ForegroundColor Cyan

$adv = Join-Path $userdata 'advancedsettings.xml'
if (Test-Path $adv) {
    try {
        [xml]$advDoc = Get-Content $adv -Raw
        $mem = $advDoc.SelectSingleNode('/advancedsettings/cache/memorysize')
        if ($mem) {
            $mb = [math]::Round([int]$mem.InnerText / 1MB, 0)
            Add-Finding -Level ok -Area 'RAM-Puffer' -Message "$mb MiB (Kodi belegt bis zum Dreifachen)"
        } else {
            Add-Finding -Level warn -Area 'RAM-Puffer' -Message 'cache/memorysize nicht gesetzt' `
                -Fix 'scripts\04-deploy-kodi-config.ps1 ausfuehren'
        }
    } catch {
        Add-Finding -Level fail -Area 'RAM-Puffer' -Message 'advancedsettings.xml ist kein gueltiges XML' `
            -Fix 'Datei loeschen und scripts\04-deploy-kodi-config.ps1 erneut ausfuehren'
    }
} else {
    Add-Finding -Level fail -Area 'RAM-Puffer' -Message 'advancedsettings.xml fehlt' `
        -Fix 'scripts\04-deploy-kodi-config.ps1 ausfuehren'
}

foreach ($f in @('favourites.xml', 'sources.xml')) {
    if (Test-Path (Join-Path $userdata $f)) {
        Add-Finding -Level ok -Area 'Dateien' -Message "$f vorhanden"
    } else {
        Add-Finding -Level warn -Area 'Dateien' -Message "$f fehlt" -Fix 'scripts\06-install-addons.ps1 ausfuehren'
    }
}

# ---------------------------------------------------------------------------
# 4. Kodi zur Laufzeit
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "-- Kodi zur Laufzeit" -ForegroundColor Cyan

if (-not (Get-Process -Name kodi -ErrorAction SilentlyContinue)) {
    Add-Finding -Level warn -Area 'Kodi' -Message 'Kodi laeuft gerade nicht' -Fix 'Kodi starten und Pruefung wiederholen'
} elseif (-not (Test-Path $modPath)) {
    Add-Finding -Level warn -Area 'Kodi' -Message "KodiRpc.psm1 fehlt ($modPath)"
} else {
    Import-Module $modPath -Force
    $rpc = @{ KodiHost = $KodiHost }
    if ($Port)     { $rpc['Port']     = $Port }
    if ($User)     { $rpc['User']     = $User }
    if ($Password) { $rpc['Password'] = $Password }

    if (-not (Test-KodiConnection @rpc)) {
        Add-Finding -Level fail -Area 'Fernsteuerung' -Message 'Kodi-Webserver nicht erreichbar' `
            -Fix 'scripts\04-deploy-kodi-config.ps1 ausfuehren (Kodi vorher beenden)'
    } else {
        Add-Finding -Level ok -Area 'Fernsteuerung' -Message 'JSON-RPC antwortet'

        $expect = @{
            'audiooutput.passthrough'       = $true
            'audiooutput.ac3passthrough'    = $true
            'audiooutput.dtspassthrough'    = $true
            'videoplayer.usedisplayasclock' = $false
            'audiooutput.stereoupmix'       = $false
        }

        foreach ($kv in $expect.GetEnumerator()) {
            try {
                $v = (Invoke-KodiRpc -Method 'Settings.GetSettingValue' -Params @{ setting = $kv.Key } @rpc).value
                if ([bool]$v -eq [bool]$kv.Value) {
                    Add-Finding -Level ok -Area 'Audio' -Message "$($kv.Key) = $v"
                } else {
                    Add-Finding -Level warn -Area 'Audio' -Message "$($kv.Key) = $v (erwartet: $($kv.Value))" `
                        -Fix 'scripts\05-apply-audio-settings.ps1 ausfuehren'
                }
            } catch {
                Add-Finding -Level warn -Area 'Audio' -Message "$($kv.Key) nicht lesbar"
            }
        }

        try {
            $dev = (Invoke-KodiRpc -Method 'Settings.GetSettingValue' -Params @{ setting = 'audiooutput.audiodevice' } @rpc).value
            if ($dev -match '(?i)wasapi') {
                Add-Finding -Level ok -Area 'Ausgabe' -Message "WASAPI aktiv: $dev"
            } else {
                Add-Finding -Level fail -Area 'Ausgabe' -Message "Kein WASAPI-Geraet aktiv: $dev" `
                    -Fix 'scripts\05-apply-audio-settings.ps1 -ShowDevices, dann passendes WASAPI-Geraet waehlen'
            }
        } catch { }
    }
}

# ---------------------------------------------------------------------------
# Zusammenfassung
# ---------------------------------------------------------------------------
$fails = @($script:Findings | Where-Object { $_.Level -eq 'fail' })
$warns = @($script:Findings | Where-Object { $_.Level -eq 'warn' })
$oks   = @($script:Findings | Where-Object { $_.Level -eq 'ok' })

Write-Host ""
Write-Host "===========================================================" -ForegroundColor White
Write-Host (" Ergebnis: {0} in Ordnung, {1} Hinweise, {2} Fehler" -f $oks.Count, $warns.Count, $fails.Count) -ForegroundColor White
Write-Host "===========================================================" -ForegroundColor White

$todo = @($fails + $warns) | Where-Object { $_.Fix }
if ($todo) {
    Write-Host ""
    Write-Host "Zu tun:" -ForegroundColor White
    $i = 0
    foreach ($t in $todo) {
        $i++
        Write-Host ("  {0}. {1}" -f $i, $t.Message)
        Write-Host ("     -> {0}" -f $t.Fix) -ForegroundColor DarkGray
    }
} else {
    Write-Host ""
    Write-Host "Nichts zu tun. Viel Spass beim Hoeren." -ForegroundColor Green
}
Write-Host ""
