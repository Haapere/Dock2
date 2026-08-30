<#
.SYNOPSIS
  Einstiegspunkt fuer den Windows-Teil: holt die Skripte und startet sie.

.DESCRIPTION
  Gedacht fuer den Aufruf als Einzeiler, damit nichts mehrzeilig kopiert
  werden muss:

    irm https://raw.githubusercontent.com/Haapere/Dock2/refs/heads/claude/linux-live-surface-7ugch0/surface-live/windows/Start.ps1 | iex

  Legt %USERPROFILE%\surface-live an, laedt Stick-vorbereiten.ps1 und
  Watch-Stick.ps1 hinein, gibt sie frei und fragt, was laufen soll.

  Bewusst ohne Umlaute in den Ausgaben: beim Ausfuehren ueber "irm | iex"
  haengt die Zeichenkodierung von der PowerShell-Version ab.
#>

function Start-SurfaceLive {
  $ErrorActionPreference = 'Stop'

  $branch = 'claude/linux-live-surface-7ugch0'
  $basis  = "https://raw.githubusercontent.com/Haapere/Dock2/refs/heads/$branch/surface-live/windows/"
  $ordner = Join-Path $env:USERPROFILE 'surface-live'
  $dateien = @('Stick-vorbereiten.ps1', 'Watch-Stick.ps1')

  Write-Host ""
  Write-Host "Surface Linux-Stick - Windows-Teil" -ForegroundColor Cyan
  Write-Host ""

  # Administratorrechte pruefen
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $rolle = New-Object Security.Principal.WindowsPrincipal($id)
  if (-not $rolle.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "  !!  Bitte PowerShell als Administrator starten." -ForegroundColor Red
    Write-Host "      Startmenue -> PowerShell -> Rechtsklick -> Als Administrator starten"
    Write-Host "      Danach diesen Einzeiler erneut einfuegen."
    return
  }

  # Ordner anlegen und hineinwechseln
  New-Item -ItemType Directory -Force -Path $ordner | Out-Null
  Set-Location -Path $ordner

  # Skripte laden und die Windows-Sperre fuer Downloads entfernen
  foreach ($datei in $dateien) {
    $ziel = Join-Path $ordner $datei
    Write-Host "  ... lade $datei"
    Invoke-WebRequest -Uri ($basis + $datei) -OutFile $ziel -UseBasicParsing
    Unblock-File -Path $ziel
  }
  Write-Host "  OK  Skripte liegen in $ordner" -ForegroundColor Green

  # Auswahl
  Write-Host ""
  Write-Host "Was soll passieren?"
  Write-Host "  1  ISO herunterladen und Checksumme vergleichen"
  Write-Host "  2  Stick schreiben (wartet, bis du ihn einsteckst)"
  Write-Host "  3  beides nacheinander"
  Write-Host "  4  nichts - ich mache von Hand weiter"
  Write-Host ""
  $wahl = Read-Host "Zahl eingeben"

  $vorbereiten = Join-Path $ordner 'Stick-vorbereiten.ps1'
  $schreiben   = Join-Path $ordner 'Watch-Stick.ps1'

  switch ($wahl) {
    '1' { & $vorbereiten }
    '2' { & $schreiben }
    '3' { & $vorbereiten; & $schreiben }
    default {
      Write-Host ""
      Write-Host "Alles klar. Du stehst jetzt in $ordner"
      Write-Host "Weiter geht es mit einer dieser beiden Zeilen:"
      Write-Host "  .\Stick-vorbereiten.ps1"
      Write-Host "  .\Watch-Stick.ps1"
    }
  }
}

Start-SurfaceLive
