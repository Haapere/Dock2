<#
.SYNOPSIS
    Prueft alle in addons/sources.json hinterlegten Stream-URLs.

.DESCRIPTION
    Streams enden nie von selbst - ein normaler Invoke-WebRequest wuerde
    haengen bleiben. Dieses Skript oeffnet die Verbindung, liest nur den
    Antwort-Header und ein paar Bytes, und schliesst wieder.

    Ausgegeben werden Statuscode, Content-Type und, sofern der Server sie
    meldet, die Icecast-Metadaten (Sendername, Bitrate).

.PARAMETER Url
    Einzelne URL statt der Liste pruefen.

.PARAMETER TimeoutSec
    Zeitlimit pro Stream. Standard 10.

.EXAMPLE
    .\test-streams.ps1

.EXAMPLE
    .\test-streams.ps1 -Url "https://stream.radioparadise.com/flac"
#>

[CmdletBinding()]
param(
    [string] $Url,
    [int]    $TimeoutSec = 10
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir  = Split-Path $toolsDir -Parent
$srcFile  = Join-Path $rootDir 'addons\sources.json'

function Test-OneStream {
    param([string]$StreamUrl, [string]$Label)

    $result = [pscustomobject]@{
        Name        = $Label
        Url         = $StreamUrl
        Status      = 'unbekannt'
        ContentType = ''
        Server      = ''
        Bitrate     = ''
        Ok          = $false
    }

    try {
        $req = [System.Net.HttpWebRequest]::Create($StreamUrl)
        $req.Method            = 'GET'
        $req.Timeout           = $TimeoutSec * 1000
        $req.ReadWriteTimeout  = $TimeoutSec * 1000
        $req.UserAgent         = 'Kodi/21.0'
        $req.AllowAutoRedirect = $true
        # Icecast-Metadaten anfordern - liefert Name und Bitrate im Header
        $req.Headers.Add('Icy-MetaData', '1')

        $resp = $req.GetResponse()
        try {
            $result.Status      = "HTTP $([int]$resp.StatusCode)"
            $result.ContentType = $resp.ContentType
            $result.Ok          = ([int]$resp.StatusCode -ge 200 -and [int]$resp.StatusCode -lt 400)

            foreach ($h in @('icy-name', 'icy-description')) {
                $v = $resp.Headers[$h]
                if ($v) { $result.Server = $v; break }
            }
            $br = $resp.Headers['icy-br']
            if ($br) { $result.Bitrate = "$br kbit/s" }

            # ein paar Bytes lesen, um zu bestaetigen, dass wirklich Daten fliessen
            $stream = $resp.GetResponseStream()
            $buffer = New-Object byte[] 4096
            $read   = $stream.Read($buffer, 0, $buffer.Length)
            if ($read -le 0) {
                $result.Ok     = $false
                $result.Status += ' (keine Daten)'
            }
            $stream.Close()
        } finally {
            $resp.Close()
        }
    } catch [System.Net.WebException] {
        $we = $_.Exception
        if ($we.Response) {
            $result.Status = "HTTP $([int]$we.Response.StatusCode)"
        } else {
            $result.Status = $we.Status.ToString()
        }
    } catch {
        $result.Status = $_.Exception.Message.Split([char]10)[0]
    }

    return $result
}

Write-Host ""
Write-Host "=== Stream-Pruefung ===" -ForegroundColor White
Write-Host ""

$results = @()

if ($Url) {
    $results += Test-OneStream -StreamUrl $Url -Label $Url
} else {
    if (-not (Test-Path $srcFile)) { throw "Quellenliste fehlt: $srcFile" }
    $cfg = Get-Content $srcFile -Raw | ConvertFrom-Json

    foreach ($s in $cfg.directStreams.items) {
        Write-Host "  pruefe: $($s.name) ..." -ForegroundColor DarkGray
        $results += Test-OneStream -StreamUrl $s.url -Label $s.name
    }
}

Write-Host ""
foreach ($r in $results) {
    $colour = if ($r.Ok) { 'Green' } else { 'Red' }
    $symbol = if ($r.Ok) { 'ok  ' } else { 'FEHL' }
    Write-Host ("  [{0}] {1}" -f $symbol, $r.Name) -ForegroundColor $colour
    Write-Host ("         {0}  {1}  {2} {3}" -f $r.Status, $r.ContentType, $r.Server, $r.Bitrate) -ForegroundColor DarkGray
}

$bad = @($results | Where-Object { -not $_.Ok })
Write-Host ""
if ($bad.Count -eq 0) {
    Write-Host "Alle $($results.Count) Streams erreichbar." -ForegroundColor Green
} else {
    Write-Host "$($bad.Count) von $($results.Count) Streams nicht erreichbar." -ForegroundColor Yellow
    Write-Host "Aktuelle Radio-Paradise-URLs stehen auf https://radioparadise.com/listen/stream-links"
    Write-Host "Danach addons/sources.json anpassen und scripts/06-install-addons.ps1 erneut ausfuehren."
}
Write-Host ""
