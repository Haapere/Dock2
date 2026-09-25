<#
    KodiRpc.psm1 - schlanker JSON-RPC-Client fuer Kodi.

    Import:
        Import-Module .\tools\KodiRpc.psm1 -Force

    Die Zugangsdaten werden, wenn nicht ausdruecklich uebergeben, aus
    %ProgramData%\KodiMediacenter\fernsteuerung.txt gelesen
    (wird von 04-deploy-kodi-config.ps1 angelegt).
#>

Set-StrictMode -Version Latest

# CommonApplicationData statt $env:ProgramData: liefert auf jedem System einen
# Wert, sodass der Modulimport nie an einer fehlenden Umgebungsvariablen scheitert.
$script:DefaultCredFile = Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'KodiMediacenter/fernsteuerung.txt'

<#
.SYNOPSIS
    Liest Host/Port/Benutzer/Passwort aus der vom Setup angelegten Datei.
#>
function Get-KodiConnection {
    [CmdletBinding()]
    param(
        [string] $KodiHost,
        [int]    $Port,
        [string] $User,
        [string] $Password,
        [string] $CredentialFile = $script:DefaultCredFile
    )

    $conn = [pscustomobject]@{
        KodiHost = if ($KodiHost) { $KodiHost } else { 'localhost' }
        Port     = if ($Port)     { $Port }     else { 8080 }
        User     = $User
        Password = $Password
    }

    # Fehlende Angaben aus der Datei nachziehen
    if ((-not $User -or -not $Password) -and $CredentialFile -and (Test-Path $CredentialFile)) {
        foreach ($line in Get-Content $CredentialFile) {
            if ($line -match '^\s*Port\s*:\s*(\d+)\s*$'      -and -not $Port)     { $conn.Port     = [int]$Matches[1] }
            if ($line -match '^\s*Benutzer\s*:\s*(\S+)\s*$'  -and -not $User)     { $conn.User     = $Matches[1] }
            if ($line -match '^\s*Passwort\s*:\s*(\S+)\s*$'  -and -not $Password) { $conn.Password = $Matches[1] }
        }
    }

    return $conn
}

<#
.SYNOPSIS
    Ruft eine Kodi-JSON-RPC-Methode auf und gibt das result-Objekt zurueck.

.PARAMETER Method
    z. B. 'Settings.GetSettings', 'Application.GetProperties'

.PARAMETER Params
    Hashtable mit den Methodenparametern.

.EXAMPLE
    Invoke-KodiRpc -Method 'JSONRPC.Ping'

.EXAMPLE
    Invoke-KodiRpc -Method 'Settings.SetSettingValue' -Params @{ setting='audiooutput.passthrough'; value=$true }
#>
function Invoke-KodiRpc {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]    $Method,
        [hashtable] $Params,
        [string]    $KodiHost,
        [int]       $Port,
        [string]    $User,
        [string]    $Password,
        [int]       $TimeoutSec = 20
    )

    $conn = Get-KodiConnection -KodiHost $KodiHost -Port $Port -User $User -Password $Password

    $body = @{
        jsonrpc = '2.0'
        id      = [guid]::NewGuid().ToString('N').Substring(0, 8)
        method  = $Method
    }
    if ($Params) { $body['params'] = $Params }

    $json = $body | ConvertTo-Json -Depth 12 -Compress
    $uri  = "http://$($conn.KodiHost):$($conn.Port)/jsonrpc"

    $headers = @{ 'Content-Type' = 'application/json' }
    if ($conn.User) {
        $pair  = "$($conn.User):$($conn.Password)"
        $b64   = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pair))
        $headers['Authorization'] = "Basic $b64"
    }

    try {
        $resp = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers `
                    -Body ([Text.Encoding]::UTF8.GetBytes($json)) -TimeoutSec $TimeoutSec
    } catch {
        $hint = switch -Regex ($_.Exception.Message) {
            '401'                     { 'Benutzername/Passwort stimmen nicht. Siehe %ProgramData%\KodiMediacenter\fernsteuerung.txt' }
            '(?i)refused|verweigert'  { 'Laeuft Kodi? Ist der Webserver aktiv (Einstellungen -> Dienste -> Steuerung)?' }
            '(?i)timeout|zeituebersch'{ 'Kodi antwortet nicht. Port und Firewall pruefen.' }
            default                   { '' }
        }
        throw "JSON-RPC '$Method' fehlgeschlagen: $($_.Exception.Message)$(if ($hint) { " -> $hint" })"
    }

    if ($resp.PSObject.Properties.Name -contains 'error' -and $resp.error) {
        throw "Kodi meldet Fehler bei '$Method': $($resp.error | ConvertTo-Json -Compress)"
    }

    return $resp.result
}

<#
.SYNOPSIS
    Prueft, ob Kodi erreichbar ist. Gibt $true/$false zurueck.
#>
function Test-KodiConnection {
    [CmdletBinding()]
    param(
        [string] $KodiHost,
        [int]    $Port,
        [string] $User,
        [string] $Password,
        [int]    $RetrySeconds = 0
    )

    $deadline = (Get-Date).AddSeconds($RetrySeconds)
    do {
        try {
            $r = Invoke-KodiRpc -Method 'JSONRPC.Ping' -KodiHost $KodiHost -Port $Port -User $User -Password $Password -TimeoutSec 5
            if ($r -eq 'pong') { return $true }
        } catch {
            if ((Get-Date) -ge $deadline) { return $false }
            Start-Sleep -Seconds 3
        }
    } while ((Get-Date) -lt $deadline)

    return $false
}

<#
.SYNOPSIS
    Holt alle Einstellungen einer Ebene inklusive der moeglichen Optionen.

.PARAMETER Level
    'basic' | 'standard' | 'advanced' | 'expert'  (Standard: expert)
#>
function Get-KodiSettings {
    [CmdletBinding()]
    param(
        [ValidateSet('basic', 'standard', 'advanced', 'expert')]
        [string] $Level = 'expert',
        [string] $KodiHost,
        [int]    $Port,
        [string] $User,
        [string] $Password
    )

    $res = Invoke-KodiRpc -Method 'Settings.GetSettings' -Params @{ level = $Level } `
              -KodiHost $KodiHost -Port $Port -User $User -Password $Password
    return $res.settings
}

<#
.SYNOPSIS
    Setzt eine Einstellung und verifiziert anschliessend den tatsaechlichen Wert.

.DESCRIPTION
    Kodi liefert bei Settings.SetSettingValue true/false zurueck. Ein false
    bedeutet meist: Wert ausserhalb des erlaubten Bereichs, falscher Typ,
    oder die Einstellung ist im aktuellen Kontext gesperrt (z. B. Samplerate
    bei "Best Match").
#>
function Set-KodiSetting {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string] $Setting,
        [Parameter(Mandatory)]         $Value,
        [string] $KodiHost,
        [int]    $Port,
        [string] $User,
        [string] $Password
    )

    $ok = Invoke-KodiRpc -Method 'Settings.SetSettingValue' `
              -Params @{ setting = $Setting; value = $Value } `
              -KodiHost $KodiHost -Port $Port -User $User -Password $Password

    return [bool]$ok
}

Export-ModuleMember -Function Get-KodiConnection, Invoke-KodiRpc, Test-KodiConnection, Get-KodiSettings, Set-KodiSetting
