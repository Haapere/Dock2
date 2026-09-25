<#
.SYNOPSIS
    Testsuite fuer das Mediencenter-Setup.

.DESCRIPTION
    Prueft die plattformunabhaengige Logik des Pakets, ohne etwas am System
    zu aendern: Registry wird nicht angefasst, Kodi nicht gestartet, keine
    Datei ausserhalb des Temp-Ordners angelegt.

    Geprueft werden:
      1. Der WAVEFORMATEXTENSIBLE-Binaerblob (Byte fuer Byte gegen die
         Microsoft-Strukturdefinition)
      2. advancedsettings.xml auf Gueltigkeit und plausible Puffergroessen
      3. Die JSON-Konfigurationen
      4. Das JSON-RPC-Modul inklusive Auslesen der Zugangsdatei
      5. Den guisettings.xml-Merge (darf fremde Eintraege nicht verlieren)
      6. Die favourites.xml-Erzeugung inklusive XML-Maskierung
      7. Die Equalizer-APO-Presets auf Syntax

    Laeuft unter Windows PowerShell 5.1 und PowerShell 7+.
    Zusaetzlich sinnvoll: eine reine Syntaxpruefung aller Skripte mit
    tests\test-syntax.ps1

.EXAMPLE
    .\tests\run-tests.ps1

.NOTES
    Exitcode entspricht der Anzahl fehlgeschlagener Tests (0 = alles gut).
#>

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$fails = 0
function T { param($Name,$Cond,$Detail='') 
    if ($Cond) { Write-Host "  ok   $Name" -ForegroundColor Green }
    else { Write-Host "  FEHL $Name  $Detail" -ForegroundColor Red; $script:fails++ }
}

# Hilfsfunktion: benannte Funktion aus einer Skriptdatei extrahieren
function Import-FunctionFromFile {
    param($File, $FunctionName)
    $tokens=$null; $errors=$null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($File, [ref]$tokens, [ref]$errors)
    $fn = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $FunctionName }, $true) | Select-Object -First 1
    if (-not $fn) { throw "Funktion $FunctionName nicht gefunden in $File" }
    return $fn.Extent.Text
}

Write-Host "`n=== 1. WAVEFORMATEXTENSIBLE-Blob ===" -ForegroundColor Cyan
. ([scriptblock]::Create((Import-FunctionFromFile "$root/scripts/01-windows-audio.ps1" 'New-WaveFormatExtensible')))

$blob = New-WaveFormatExtensible -SampleRate 96000 -BitsPerSample 24 -Channels 2
T "Laenge 40 Byte" ($blob.Length -eq 40) "ist $($blob.Length)"
T "wFormatTag = 0xFFFE" ([BitConverter]::ToUInt16($blob,0) -eq 0xFFFE)
T "nChannels = 2"      ([BitConverter]::ToUInt16($blob,2) -eq 2)
T "nSamplesPerSec = 96000" ([BitConverter]::ToUInt32($blob,4) -eq 96000)
T "nAvgBytesPerSec = 576000" ([BitConverter]::ToUInt32($blob,8) -eq 576000) "ist $([BitConverter]::ToUInt32($blob,8))"
T "nBlockAlign = 6"    ([BitConverter]::ToUInt16($blob,12) -eq 6)
T "wBitsPerSample = 24" ([BitConverter]::ToUInt16($blob,14) -eq 24)
T "cbSize = 22"        ([BitConverter]::ToUInt16($blob,16) -eq 22)
T "wValidBits = 24"    ([BitConverter]::ToUInt16($blob,18) -eq 24)
T "dwChannelMask = 3"  ([BitConverter]::ToUInt32($blob,20) -eq 3)
$sub = [guid]::new([byte[]]$blob[24..39])
T "SubFormat = KSDATAFORMAT_SUBTYPE_PCM" ($sub.ToString() -eq '00000001-0000-0010-8000-00aa00389b71') "ist $sub"

$blob16 = New-WaveFormatExtensible -SampleRate 44100 -BitsPerSample 16 -Channels 2
T "16/44,1: BlockAlign 4"   ([BitConverter]::ToUInt16($blob16,12) -eq 4)
T "16/44,1: AvgBytes 176400" ([BitConverter]::ToUInt32($blob16,8) -eq 176400)

Write-Host "`n=== 2. advancedsettings.xml ===" -ForegroundColor Cyan
[xml]$adv = Get-Content "$root/config/advancedsettings.xml" -Raw
T "Wurzelelement advancedsettings" ($adv.DocumentElement.Name -eq 'advancedsettings')
$mem = [int]$adv.SelectSingleNode('/advancedsettings/cache/memorysize').InnerText
T "memorysize = 200 MiB" ($mem -eq 209715200) "ist $mem"
T "buffermode = 1" ($adv.SelectSingleNode('/advancedsettings/cache/buffermode').InnerText -eq '1')
T "readfactor gesetzt" ($null -ne $adv.SelectSingleNode('/advancedsettings/cache/readfactor'))
$ramMb = [math]::Round($mem * 3 / 1MB)
T "RAM-Bedarf unter 1 GB" ($ramMb -lt 1024) "$ramMb MiB"

Write-Host "`n=== 3. JSON-Konfigurationen ===" -ForegroundColor Cyan
$ks = Get-Content "$root/config/kodi-settings.json" -Raw | ConvertFrom-Json
T "kodi-settings.json parsebar" ($null -ne $ks)
T "passthrough = true"  ($ks.boolean.'audiooutput.passthrough' -eq $true)
T "ac3transcode = false" ($ks.boolean.'audiooutput.ac3transcode' -eq $false)
T "usedisplayasclock = false" ($ks.boolean.'videoplayer.usedisplayasclock' -eq $false)
T "webserverport = 8080" ($ks.integer.'services.webserverport' -eq 8080)
T "enumByLabel hat audiooutput.config" ($null -ne $ks.enumByLabel.'audiooutput.config')

$src = Get-Content "$root/addons/sources.json" -Raw | ConvertFrom-Json
T "sources.json parsebar" ($null -ne $src)
T "candidateStreams getrennt von directStreams" ($null -ne $src.candidateStreams)
$unver = @($src.candidateStreams.items | Where-Object { $_.verified -ne $false })
T "alle Kandidaten als ungeprueft markiert" ($unver.Count -eq 0) "nicht markiert: $($unver.name -join ', ')"
T "SomaFM-Generator hinterlegt" ($null -ne $src.generators.somafm)

$dj = Get-Content "$root/config/dj-sources.json" -Raw | ConvertFrom-Json
T "dj-sources.json parsebar" ($null -ne $dj)
T "mind. 5 DJ-Quellen" (@($dj.sources).Count -ge 5)
$noUrl = @($dj.sources | Where-Object { -not $_.url -or $_.url -notmatch '^https?://' })
T "alle DJ-Quellen haben gueltige URL" ($noUrl.Count -eq 0) "ohne URL: $($noUrl.name -join ', ')"
$noPlat = @($dj.sources | Where-Object { $_.platform -notin @('youtube','soundcloud','mixcloud','hearthis','generic') })
T "alle Plattformen bekannt" ($noPlat.Count -eq 0) "unbekannt: $($noPlat.platform -join ', ')"
T "Standardwerte gesetzt" ($dj.defaults.maxPerSource -gt 0 -and $dj.defaults.minDurationMinutes -gt 0)
T "mind. 4 FLAC-Streams" (@($src.directStreams.items | Where-Object { $_.format -match 'FLAC' }).Count -ge 4)
$allHttps = @($src.directStreams.items | Where-Object { $_.url -notlike 'https://*' })
T "alle Stream-URLs via https" ($allHttps.Count -eq 0) "Ausnahmen: $($allHttps.name -join ', ')"

Write-Host "`n=== 4. KodiRpc-Modul ===" -ForegroundColor Cyan
Import-Module "$root/tools/KodiRpc.psm1" -Force
foreach ($fn in 'Get-KodiConnection','Invoke-KodiRpc','Test-KodiConnection','Get-KodiSettings','Set-KodiSetting') {
    T "$fn exportiert" ($null -ne (Get-Command $fn -ErrorAction SilentlyContinue))
}
$conn = Get-KodiConnection -KodiHost 'testhost' -Port 9999 -User 'u' -Password 'p' -CredentialFile '/nonexistent'
T "Verbindungsobjekt korrekt" ($conn.KodiHost -eq 'testhost' -and $conn.Port -eq 9999)

# Auslesen der Zugangsdatei simulieren
$tmpCred = [System.IO.Path]::GetTempFileName()
@"
Kodi-Fernsteuerung - Zugangsdaten

Host      : 192.168.1.50
Port      : 8081
Benutzer  : kodi
Passwort  : GeheimesPasswort42
"@ | Set-Content $tmpCred
$conn2 = Get-KodiConnection -CredentialFile $tmpCred
T "Port aus Datei gelesen"     ($conn2.Port -eq 8081)     "ist $($conn2.Port)"
T "Benutzer aus Datei gelesen" ($conn2.User -eq 'kodi')   "ist $($conn2.User)"
T "Passwort aus Datei gelesen" ($conn2.Password -eq 'GeheimesPasswort42') "ist $($conn2.Password)"
Remove-Item $tmpCred -Force

Write-Host "`n=== 5. guisettings.xml-Merge ===" -ForegroundColor Cyan
. ([scriptblock]::Create((Import-FunctionFromFile "$root/scripts/04-deploy-kodi-config.ps1" 'Set-GuiSetting')))
function Write-Ok { param($m) }   # Ausgabe im Test unterdruecken

# Fall A: bestehende Datei mit default-Attribut und fremden Eintraegen
[xml]$doc = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<settings version="2">
  <setting id="services.webserver" default="true">false</setting>
  <setting id="lookandfeel.skin">skin.estuary</setting>
</settings>
'@
Set-GuiSetting -Doc $doc -Id 'services.webserver' -Value 'true'
Set-GuiSetting -Doc $doc -Id 'services.webserverport' -Value '8080'

$ws = $doc.SelectSingleNode("/settings/setting[@id='services.webserver']")
T "Wert ueberschrieben" ($ws.InnerText -eq 'true')
T "default-Attribut entfernt" (-not $ws.HasAttribute('default'))
T "neues Setting angelegt" ($null -ne $doc.SelectSingleNode("/settings/setting[@id='services.webserverport']"))
T "fremdes Setting erhalten" ($doc.SelectSingleNode("/settings/setting[@id='lookandfeel.skin']").InnerText -eq 'skin.estuary')

Write-Host "`n=== 6. favourites.xml-Erzeugung ===" -ForegroundColor Cyan
# Logik aus 06-install-addons.ps1 nachbilden
$items = @(
  [pscustomobject]@{ name='Radio Paradise - Main Mix (FLAC)'; url='https://stream.radioparadise.com/flac' },
  [pscustomobject]@{ name='Test & Sonderzeichen <">';         url='https://example.com/s?a=1&b=2' }
)
$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
[void]$sb.AppendLine('<favourites>')
foreach ($s in $items) {
    $name = [System.Security.SecurityElement]::Escape($s.name)
    $url  = [System.Security.SecurityElement]::Escape($s.url)
    $cmd  = "PlayMedia(&quot;$url&quot;)"
    [void]$sb.AppendLine("    <favourite name=""$name"">$cmd</favourite>")
}
[void]$sb.AppendLine('</favourites>')
$xmlText = $sb.ToString()

try { [xml]$fav = $xmlText; T "erzeugtes XML ist gueltig" $true }
catch { T "erzeugtes XML ist gueltig" $false $_.Exception.Message }

$first = $fav.favourites.favourite[0]
T "Favoritenname korrekt" ($first.name -eq 'Radio Paradise - Main Mix (FLAC)')
T "PlayMedia-Befehl korrekt" ($first.InnerText -eq 'PlayMedia("https://stream.radioparadise.com/flac")') "ist '$($first.InnerText)'"
T "Sonderzeichen im Namen maskiert" ($fav.favourites.favourite[1].name -eq 'Test & Sonderzeichen <">')
T "Kaufmanns-Und in URL maskiert" ($fav.favourites.favourite[1].InnerText -eq 'PlayMedia("https://example.com/s?a=1&b=2")') "ist '$($fav.favourites.favourite[1].InnerText)'"

Write-Host "`n=== 7. Zuweisungen an Automatikvariablen ===" -ForegroundColor Cyan
<#
    PowerShell schuetzt einige Automatikvariablen. Eine Zuweisung an $HOME
    oder $Host bricht das Skript zur Laufzeit ab - die Syntaxpruefung sieht
    das nicht. Deshalb hier per AST pruefen.
#>
$protectedVars = @('HOME','PID','PSHOME','true','false','Host','Error','ExecutionContext','ShellId','PSCulture','PSUICulture','PSVersionTable')
$violations = @()

foreach ($f in (Get-ChildItem -Path $root -Recurse -Include *.ps1, *.psm1)) {
    $tokens = $null; $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$tokens, [ref]$errors)

    $assignments = $ast.FindAll({
        param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst]
    }, $true)

    foreach ($a in $assignments) {
        $left = $a.Left
        # Auch $x = ... innerhalb von [type]$x = ... erfassen
        if ($left -is [System.Management.Automation.Language.ConvertExpressionAst]) { $left = $left.Child }
        if ($left -isnot [System.Management.Automation.Language.VariableExpressionAst]) { continue }

        $name = $left.VariablePath.UserPath
        if ($protectedVars -contains $name) {
            $violations += "$($f.Name):$($a.Extent.StartLineNumber) -> `$$name"
        }
    }
}

T "keine Zuweisung an geschuetzte Variablen" ($violations.Count -eq 0) ($violations -join ' | ')

Write-Host "`n=== 8. Equalizer-APO-Syntax ===" -ForegroundColor Cyan
$filterRe = '^(Filter\s*\d*\s*:\s*(ON|OFF)\s+(PK|LP|HP|LPQ|HPQ|BP|LS|HS|LSC|HSC|NO|AP)\b.*|Preamp:\s*-?\d+(\.\d+)?\s*dB|Device:.*|Include:.*|Channel:.*|#.*|\s*)$'
foreach ($f in Get-ChildItem "$root/dsp" -Filter '*.txt') {
    $lineNo = 0; $bad = @()
    foreach ($line in Get-Content $f.FullName) {
        $lineNo++
        if ($line -notmatch $filterRe) { $bad += "Z$lineNo`: $line" }
    }
    T "$($f.Name) syntaktisch plausibel" ($bad.Count -eq 0) ($bad -join ' | ')
}

Write-Host ""
if ($fails -eq 0) { Write-Host "ALLE TESTS BESTANDEN" -ForegroundColor Green }
else { Write-Host "$fails Test(s) fehlgeschlagen" -ForegroundColor Red }
exit $fails
