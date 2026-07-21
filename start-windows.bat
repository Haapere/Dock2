@echo off
REM ============================================================
REM  StrategyLab starten (Windows) - einfach doppelklicken.
REM  Beim ersten Start wird alles automatisch eingerichtet.
REM ============================================================
setlocal
cd /d "%~dp0"

REM Python finden (zuerst den Launcher 'py', dann 'python')
set "PY="
py --version >nul 2>&1 && set "PY=py"
if not defined PY (
  python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo.
  echo   Python wurde nicht gefunden.
  echo   Bitte Python von https://www.python.org/downloads/ installieren
  echo   und im Installer das Haekchen "Add Python to PATH" setzen.
  echo.
  pause
  exit /b 1
)

REM Beim ersten Start: eigene Umgebung anlegen und Programm installieren
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   Erste Einrichtung laeuft - das dauert ein bis zwei Minuten...
  echo.
  %PY% -m venv .venv
  if errorlevel 1 goto :error
  call ".venv\Scripts\activate.bat"
  python -m pip install --upgrade pip
  python -m pip install -e .
  if errorlevel 1 goto :error
) else (
  call ".venv\Scripts\activate.bat"
)

echo.
echo   StrategyLab startet - der Browser oeffnet sich gleich automatisch.
echo   Dieses Fenster bitte geoeffnet lassen, solange du das Programm nutzt.
echo   Zum Beenden hier Strg+C druecken oder das Fenster schliessen.
echo.
python -m strategylab.cli gui
goto :eof

:error
echo.
echo   Bei der Einrichtung ist etwas schiefgelaufen. Bitte die Meldung oben pruefen.
echo.
pause
exit /b 1
