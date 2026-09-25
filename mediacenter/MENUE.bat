@echo off
REM ===========================================================================
REM  MENUE.bat - Auswahl der haeufigsten Aufgaben, ohne Befehle tippen
REM ===========================================================================

setlocal enabledelayedexpansion

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

where pwsh.exe >nul 2>&1
if %errorlevel% equ 0 ( set "PS=pwsh.exe" ) else ( set "PS=powershell.exe" )

:menue
cls
echo ===========================================================================
echo   Hi-Res Mediencenter
echo ===========================================================================
echo.
echo   EINRICHTUNG
echo     1  Komplettes Setup starten          (install.ps1)
echo     2  Systempruefung                    (healthcheck.ps1)
echo.
echo   AUDIO
echo     3  Audiogeraete anzeigen             (Windows-Sicht)
echo     4  Auf Kopfhoerer / USB-DAC umschalten
echo     5  Auf AV-Receiver / HDMI umschalten
echo.
echo   MUSIK
echo     6  DJ-Sets holen                     (alle Quellen)
echo     7  Quellenliste anzeigen
echo     8  SoundCloud-Profil einlesen
echo     9  Vorschlaege anzeigen
echo.
echo   PRUEFEN
echo    10  Streams testen
echo    11  Testsuite
echo.
echo     0  Beenden
echo.
set /p wahl="  Auswahl: "

if "%wahl%"=="1"  ( %PS% -NoProfile -ExecutionPolicy Bypass -File "install.ps1" & pause & goto menue )
if "%wahl%"=="2"  ( %PS% -NoProfile -ExecutionPolicy Bypass -File "tools\healthcheck.ps1" & pause & goto menue )
if "%wahl%"=="3"  ( %PS% -NoProfile -ExecutionPolicy Bypass -File "scripts\01-windows-audio.ps1" -List & pause & goto menue )
if "%wahl%"=="4"  ( %PS% -NoProfile -ExecutionPolicy Bypass -File "tools\switch-audio.ps1" -Target dac & pause & goto menue )
if "%wahl%"=="5"  ( %PS% -NoProfile -ExecutionPolicy Bypass -File "tools\switch-audio.ps1" -Target hdmi & pause & goto menue )
if "%wahl%"=="6"  ( %PS% -NoProfile -ExecutionPolicy Bypass -File "tools\dj-fetch.ps1" -All & pause & goto menue )
if "%wahl%"=="7"  ( %PS% -NoProfile -ExecutionPolicy Bypass -File "tools\dj-fetch.ps1" -List & pause & goto menue )
if "%wahl%"=="8"  ( %PS% -NoProfile -ExecutionPolicy Bypass -File "tools\sc-library.ps1" -Deep & pause & goto menue )
if "%wahl%"=="9"  ( %PS% -NoProfile -ExecutionPolicy Bypass -File "tools\dj-suggest.ps1" -Interactive & pause & goto menue )
if "%wahl%"=="10" ( %PS% -NoProfile -ExecutionPolicy Bypass -File "tools\test-streams.ps1" -IncludeCandidates & pause & goto menue )
if "%wahl%"=="11" ( %PS% -NoProfile -ExecutionPolicy Bypass -File "tests\run-tests.ps1" & pause & goto menue )
if "%wahl%"=="0"  ( exit /b )

goto menue
