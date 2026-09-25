@echo off
REM ===========================================================================
REM  START.bat - Doppelklick-Starter fuer das Mediencenter-Setup
REM ===========================================================================
REM  Erledigt die drei Dinge, an denen es sonst haengt:
REM    1. Administratorrechte anfordern (fragt per Windows-Dialog nach)
REM    2. In DIESEN Ordner wechseln - egal von wo aus gestartet wurde
REM    3. PowerShell mit der noetigen Ausfuehrungsrichtlinie starten
REM
REM  Ohne Parameter wird install.ps1 gestartet. Ein Parameter waehlt ein
REM  anderes Skript, zum Beispiel:
REM      START.bat tools\healthcheck.ps1
REM ===========================================================================

setlocal

REM --- Laeuft das hier schon mit Administratorrechten? ----------------------
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  Administratorrechte werden angefordert...
    echo  Bitte die Windows-Rueckfrage mit "Ja" bestaetigen.
    echo.
    REM Sich selbst neu starten, diesmal erhoeht. Der Ordnerpfad wird
    REM mitgegeben, weil das erhoehte Fenster sonst in System32 landet.
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
    exit /b
)

REM --- Ab hier laeuft alles als Administrator --------------------------------
cd /d "%~dp0"

echo ===========================================================================
echo  Hi-Res Mediencenter - Setup
echo ===========================================================================
echo.
echo  Ordner: %CD%
echo.

REM --- Welches Skript? -------------------------------------------------------
set "SKRIPT=%~1"
if "%SKRIPT%"=="" set "SKRIPT=install.ps1"

if not exist "%SKRIPT%" (
    echo  FEHLER: %SKRIPT% liegt nicht in diesem Ordner.
    echo.
    echo  Vermutlich wurde das ZIP nicht vollstaendig entpackt. Der Ordner
    echo  muss install.ps1 sowie die Unterordner scripts, tools und config
    echo  enthalten.
    echo.
    pause
    exit /b 1
)

REM --- PowerShell 7 bevorzugen, sonst Windows PowerShell 5.1 -----------------
where pwsh.exe >nul 2>&1
if %errorlevel% equ 0 (
    set "PS=pwsh.exe"
) else (
    set "PS=powershell.exe"
)

echo  Starte %SKRIPT% mit %PS% ...
echo.

REM -NoExit laesst das Fenster offen, damit Meldungen lesbar bleiben
%PS% -NoProfile -NoExit -ExecutionPolicy Bypass -File "%SKRIPT%" %2 %3 %4 %5 %6 %7 %8 %9

endlocal
