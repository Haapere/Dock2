<#
.SYNOPSIS
  Wartet auf einen eingesteckten USB-Stick und schreibt das Ubuntu-ISO automatisch darauf.

.DESCRIPTION
  Überwacht die USB-Datenträger des Rechners. Sobald einer dazukommt, wird er
  geprüft (nur USB, plausible Größe, kein System- oder Startdatenträger) und das
  ISO roh auf das Gerät geschrieben — derselbe Vorgang wie Rufus im DD-Modus.
  Das Ergebnis bootet mit eingeschaltetem Secure Boot, weil der signierte
  Ubuntu-Bootloader unverändert übernommen wird.

  Erzeugt Stick A (den Installer-Stick). Stick B — das eigentliche Linux-System —
  kann Windows nicht erzeugen; das übernimmt build-stick.sh in der Live-Sitzung.

  MUSS als Administrator laufen. Der Zieldatenträger wird vollständig gelöscht.

.PARAMETER Iso
  Pfad zum ISO. Ohne Angabe wird die neueste ubuntu-*-desktop-amd64.iso im
  Downloads-Ordner genommen.

.PARAMETER Automatisch
  Schreibt ohne Rückfrage, sobald ein passender Stick erkannt wird.
  Nur benutzen, wenn wirklich nur der Zielstick angesteckt wird.

.PARAMETER MinGB
  Kleinste akzeptierte Größe in GB, Standard 7.

.PARAMETER MaxGB
  Größte akzeptierte Größe in GB, Standard 128. Sicherheitsnetz gegen
  versehentlich angeschlossene externe Festplatten.

.PARAMETER Einmal
  Nach dem ersten geschriebenen Stick beenden.

.EXAMPLE
  .\Watch-Stick.ps1
  .\Watch-Stick.ps1 -Iso D:\ubuntu-26.04.1-desktop-amd64.iso -Einmal
#>
[CmdletBinding()]
param(
  [string]$Iso = "",
  [switch]$Automatisch,
  [int]$MinGB = 7,
  [int]$MaxGB = 128,
  [switch]$Einmal
)

$ErrorActionPreference = "Stop"

function Schritt($t) { Write-Host "`n$t" -ForegroundColor Cyan }
function Gut($t)     { Write-Host "  OK  $t" -ForegroundColor Green }
function Hinweis($t) { Write-Host "      $t" -ForegroundColor DarkGray }
function Achtung($t) { Write-Host "  !   $t" -ForegroundColor Yellow }
function Fehler($t)  { Write-Host "  !!  $t" -ForegroundColor Red }

# ------------------------------------------------------------ Voraussetzungen
$identitaet = [Security.Principal.WindowsIdentity]::GetCurrent()
$rolle = New-Object Security.Principal.WindowsPrincipal($identitaet)
if (-not $rolle.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Fehler "Dieses Skript braucht Administratorrechte."
  Hinweis "PowerShell mit Rechtsklick als Administrator starten und erneut ausführen."
  exit 1
}

if (-not $Iso) {
  $kandidat = Get-ChildItem -Path (Join-Path $env:USERPROFILE "Downloads") `
                            -Filter "ubuntu-*-desktop-amd64.iso" -ErrorAction SilentlyContinue |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $kandidat) {
    Fehler "Kein ISO gefunden."
    Hinweis "Erst .\Stick-vorbereiten.ps1 laufen lassen oder -Iso <Pfad> angeben."
    exit 1
  }
  $Iso = $kandidat.FullName
}

if (-not (Test-Path $Iso)) { Fehler "ISO nicht gefunden: $Iso"; exit 1 }
$isoGroesse = (Get-Item $Iso).Length
Schritt "Abbild"
Gut ("{0}  ({1:N1} GB)" -f (Split-Path $Iso -Leaf), ($isoGroesse / 1GB))

# ------------------------------------------------------------------ Prüfungen
function Get-UsbDatentraeger {
  Get-Disk | Where-Object { $_.BusType -eq 'USB' }
}

function Test-Ziel($disk) {
  if ($disk.IsSystem -or $disk.IsBoot) {
    Fehler "Datenträger $($disk.Number) ist System- oder Startdatenträger. Übersprungen."
    return $false
  }
  if ($disk.BusType -ne 'USB') {
    Fehler "Datenträger $($disk.Number) hängt nicht am USB ($($disk.BusType)). Übersprungen."
    return $false
  }
  $gb = [math]::Round($disk.Size / 1GB, 1)
  if ($gb -lt $MinGB) {
    Achtung "Datenträger $($disk.Number) ist mit $gb GB zu klein (mindestens $MinGB GB). Übersprungen."
    return $false
  }
  if ($gb -gt $MaxGB) {
    Achtung "Datenträger $($disk.Number) ist mit $gb GB größer als $MaxGB GB — sieht nach einer externen Festplatte aus. Übersprungen."
    Hinweis "Wenn das wirklich der Stick ist: -MaxGB $([math]::Ceiling($gb)) angeben."
    return $false
  }
  if ($disk.Size -lt $isoGroesse) {
    Fehler "Datenträger $($disk.Number) ist kleiner als das Abbild. Übersprungen."
    return $false
  }
  return $true
}

# ------------------------------------------------------------------ Schreiben
function Write-Iso($disk) {
  $nr = $disk.Number
  $quelle = $null
  $ziel = $null
  try {
    Schritt "Vorbereiten"
    Clear-Disk -Number $nr -RemoveData -RemoveOEM -Confirm:$false
    Set-Disk -Number $nr -IsReadOnly $false
    Set-Disk -Number $nr -IsOffline $true
    Gut "Datenträger $nr freigeräumt und offline genommen"

    Schritt "Schreiben"
    Hinweis "Nicht abziehen, bis 'fertig' dasteht."
    $quelle = [System.IO.File]::OpenRead($Iso)
    $ziel = New-Object System.IO.FileStream("\\.\PhysicalDrive$nr",
              [System.IO.FileMode]::Open, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)

    $puffer = New-Object byte[] (8MB)
    $geschrieben = 0L
    $start = Get-Date
    while (($gelesen = $quelle.Read($puffer, 0, $puffer.Length)) -gt 0) {
      $ziel.Write($puffer, 0, $gelesen)
      $geschrieben += $gelesen
      $prozent = [int](($geschrieben / $isoGroesse) * 100)
      $sekunden = [math]::Max((Get-Date).Subtract($start).TotalSeconds, 1)
      $tempo = [math]::Round(($geschrieben / 1MB) / $sekunden, 1)
      Write-Progress -Activity "Schreibe auf Datenträger $nr" `
        -Status ("{0:N1} von {1:N1} GB  —  {2} MB/s" -f ($geschrieben/1GB), ($isoGroesse/1GB), $tempo) `
        -PercentComplete $prozent
    }
    $ziel.Flush()
    Write-Progress -Activity "Schreibe" -Completed
    Gut ("{0:N1} GB geschrieben" -f ($geschrieben / 1GB))
  }
  finally {
    if ($ziel)   { $ziel.Dispose() }
    if ($quelle) { $quelle.Dispose() }
    try { Set-Disk -Number $nr -IsOffline $false }
    catch { Achtung "Datenträger blieb offline — in der Datenträgerverwaltung wieder online setzen." }
  }

  Schritt "Fertig"
  Gut "Stick A ist bootfähig."
  Hinweis "Windows fragt gleich vielleicht, ob der Datenträger formatiert werden soll — NICHT formatieren."
  Hinweis "Die Linux-Partitionen kann Windows nicht lesen, das ist normal."
  Hinweis "Weiter mit docs/02-system-auf-stick-bauen.md"
}

# ---------------------------------------------------------------- Überwachung
Schritt "Überwachung läuft"
$bekannt = @(Get-UsbDatentraeger | Select-Object -ExpandProperty Number)
if ($bekannt.Count -gt 0) {
  Hinweis "Bereits angeschlossen und deshalb ignoriert: Datenträger $($bekannt -join ', ')"
}
Hinweis "Jetzt den Stick einstecken. Beenden mit Strg+C."

while ($true) {
  Start-Sleep -Seconds 2
  $jetzt = @(Get-UsbDatentraeger)
  $neue = $jetzt | Where-Object { $bekannt -notcontains $_.Number }

  foreach ($gefunden in $neue) {
    Start-Sleep -Seconds 2   # Windows die Partitionstabelle einlesen lassen
    $disk = Get-Disk -Number $gefunden.Number
    Schritt "Neuer Datenträger erkannt"
    Write-Host ("      Nummer:  {0}" -f $disk.Number)
    Write-Host ("      Modell:  {0}" -f $disk.FriendlyName)
    Write-Host ("      Größe:   {0:N1} GB" -f ($disk.Size / 1GB))
    $partitionen = Get-Partition -DiskNumber $disk.Number -ErrorAction SilentlyContinue |
                   Where-Object DriveLetter | ForEach-Object { "$($_.DriveLetter):" }
    if ($partitionen) { Write-Host ("      Laufwerk: {0}" -f ($partitionen -join ' ')) }

    if (Test-Ziel $disk) {
      $los = [bool]$Automatisch
      if (-not $los) {
        Achtung "ALLE DATEN auf Datenträger $($disk.Number) werden gelöscht."
        $antwort = Read-Host "      Zum Bestätigen JA eingeben"
        $los = ($antwort -eq "JA")
      }
      if ($los) {
        Write-Iso $disk
        if ($Einmal) { exit 0 }
      } else {
        Hinweis "Übersprungen, nichts verändert."
      }
    }
    $bekannt += $disk.Number
  }

  # Abgezogene Sticks vergessen, damit sie beim erneuten Einstecken wieder greifen.
  $aktuell = @($jetzt | Select-Object -ExpandProperty Number)
  $bekannt = @($bekannt | Where-Object { $aktuell -contains $_ })
}
