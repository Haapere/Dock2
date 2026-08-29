<#
.SYNOPSIS
  Lädt das Ubuntu-ISO auf einem Windows-PC herunter und prüft die Signatur-Prüfsumme.

.DESCRIPTION
  Holt SHA256SUMS von releases.ubuntu.com, sucht darin das aktuellste
  Desktop-Image für amd64, lädt es herunter und vergleicht die Prüfsumme.
  Beschreibt bewusst KEINE Datenträger – das übernimmt Rufus, damit nicht
  versehentlich eine interne Festplatte getroffen wird.

.PARAMETER Release
  Ubuntu-Release-Verzeichnis, Standard: 26.04

.PARAMETER Ziel
  Zielordner, Standard: der Downloads-Ordner

.PARAMETER NurPruefen
  Lädt nichts, prüft nur eine bereits vorhandene ISO-Datei im Zielordner.

.EXAMPLE
  .\Stick-vorbereiten.ps1
  .\Stick-vorbereiten.ps1 -Release 24.04
  .\Stick-vorbereiten.ps1 -NurPruefen
#>
[CmdletBinding()]
param(
  [string]$Release = "26.04",
  [string]$Ziel = (Join-Path $env:USERPROFILE "Downloads"),
  [switch]$NurPruefen
)

$ErrorActionPreference = "Stop"
$Basis = "https://releases.ubuntu.com/$Release"

function Schritt($text) { Write-Host "`n$text" -ForegroundColor Cyan }
function Gut($text)     { Write-Host "  OK  $text" -ForegroundColor Green }
function Hinweis($text) { Write-Host "      $text" -ForegroundColor DarkGray }
function Fehler($text)  { Write-Host "  !!  $text" -ForegroundColor Red }

Schritt "1. Prüfsummen-Liste holen"
try {
  $summen = (Invoke-WebRequest -Uri "$Basis/SHA256SUMS" -UseBasicParsing).Content
} catch {
  Fehler "SHA256SUMS von $Basis nicht erreichbar."
  Hinweis "Gibt es das Release $Release? Verzeichnisliste: https://releases.ubuntu.com/"
  exit 1
}

# Zeilen sehen so aus: <sha256> *ubuntu-26.04.1-desktop-amd64.iso
$treffer = $summen -split "`n" |
  Where-Object { $_ -match 'desktop-amd64\.iso\s*$' } |
  Sort-Object { ($_ -split '\*')[-1] } -Descending

if (-not $treffer) { Fehler "Kein Desktop-Image für amd64 in SHA256SUMS gefunden."; exit 1 }

$zeile   = $treffer[0].Trim()
$sollHash = ($zeile -split '\s+')[0]
$datei    = ($zeile -split '\*')[-1].Trim()
$pfad     = Join-Path $Ziel $datei

Gut "Image: $datei"
Hinweis "Soll-Prüfsumme: $sollHash"

Schritt "2. Herunterladen"
if (Test-Path $pfad) {
  Gut "Datei liegt schon da: $pfad"
} elseif ($NurPruefen) {
  Fehler "Datei fehlt: $pfad"; exit 1
} else {
  if (-not (Test-Path $Ziel)) { New-Item -ItemType Directory -Path $Ziel | Out-Null }
  Hinweis "Rund 6 GB – das dauert. Abbruch mit Strg+C ist gefahrlos."
  try {
    Start-BitsTransfer -Source "$Basis/$datei" -Destination $pfad -Description "Ubuntu $Release"
  } catch {
    Hinweis "BITS nicht verfügbar, nutze Invoke-WebRequest (ohne Fortschrittsanzeige)."
    Invoke-WebRequest -Uri "$Basis/$datei" -OutFile $pfad -UseBasicParsing
  }
  Gut "Heruntergeladen: $pfad"
}

Schritt "3. Prüfsumme vergleichen"
Hinweis "Dauert bei 6 GB etwa eine Minute."
$istHash = (Get-FileHash -Path $pfad -Algorithm SHA256).Hash.ToLower()

if ($istHash -eq $sollHash.ToLower()) {
  Gut "Prüfsumme stimmt – die Datei ist unverfälscht."
} else {
  Fehler "PRÜFSUMME STIMMT NICHT!"
  Hinweis "erwartet: $sollHash"
  Hinweis "erhalten: $istHash"
  Hinweis "Datei löschen und neu laden. Nicht auf den Stick schreiben."
  exit 1
}

Schritt "4. Jetzt mit Rufus auf Stick A schreiben"
Write-Host @"
      Rufus: https://rufus.ie  (portable Version reicht)

      Einstellungen:
        Laufwerk .................. dein USB-Stick A (mind. 8 GB) - PRÜFEN!
        Startart .................. Abbild und dann $datei wählen
        Partitionsschema .......... GPT
        Zielsystem ................ UEFI (ohne CSM)
        Dateisystem ............... FAT32 (Standard lassen)
        Schreibmodus .............. ISO-Abbild-Modus (empfohlen)

      Achtung: Rufus löscht den gewählten Stick vollständig.

      Weiter geht es in docs/02-system-auf-stick-bauen.md
"@ -ForegroundColor Gray
