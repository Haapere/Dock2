<#
.SYNOPSIS
    Prueft alle PowerShell-Dateien des Pakets auf Syntaxfehler.

.DESCRIPTION
    Nutzt den PowerShell-Parser, ohne die Skripte auszufuehren. Damit laesst
    sich nach jeder Aenderung in Sekunden pruefen, ob alles noch parst -
    deutlich schneller und ungefaehrlicher, als die Skripte testweise
    laufen zu lassen.

.EXAMPLE
    .\tests\test-syntax.ps1

.NOTES
    Exitcode entspricht der Anzahl fehlerhafter Dateien.
#>

[CmdletBinding()]
param()

$root  = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$files = Get-ChildItem -Path $root -Recurse -Include *.ps1, *.psm1
$bad   = 0

Write-Host ""
Write-Host "=== Syntaxpruefung ===" -ForegroundColor White
Write-Host ""

foreach ($f in $files) {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$tokens, [ref]$errors) | Out-Null

    $rel = $f.FullName.Substring($root.Length).TrimStart('\', '/')

    if ($errors -and $errors.Count -gt 0) {
        $bad++
        Write-Host "  FEHL $rel" -ForegroundColor Red
        foreach ($e in $errors) {
            Write-Host ("         Zeile {0}, Spalte {1}: {2}" -f `
                $e.Extent.StartLineNumber, $e.Extent.StartColumnNumber, $e.Message) -ForegroundColor DarkGray
        }
    } else {
        Write-Host ("  ok   {0,-44} {1,4} Zeilen" -f $rel, (Get-Content $f.FullName).Count) -ForegroundColor Green
    }
}

Write-Host ""
if ($bad -eq 0) {
    Write-Host "$($files.Count) Dateien geprueft, keine Syntaxfehler." -ForegroundColor Green
} else {
    Write-Host "$($files.Count) Dateien geprueft, $bad mit Fehlern." -ForegroundColor Red
}
Write-Host ""

exit $bad
