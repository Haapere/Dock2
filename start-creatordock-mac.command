#!/bin/bash
# ============================================================
#  CreatorDock starten (macOS) - einfach doppelklicken.
#  Beim ersten Start wird alles automatisch eingerichtet.
# ============================================================
cd "$(dirname "$0")" || exit 1

# Python 3 finden
if ! command -v python3 >/dev/null 2>&1; then
  echo
  echo "  Python 3 wurde nicht gefunden."
  echo "  Bitte Python von https://www.python.org/downloads/ installieren"
  echo "  und dieses Programm danach erneut starten."
  echo
  read -r -p "  Zum Schliessen die Eingabetaste druecken..."
  exit 1
fi

# Beim ersten Start: eigene Umgebung anlegen und Programm installieren
if [ ! -x ".venv/bin/python" ]; then
  echo
  echo "  Erste Einrichtung laeuft - das dauert ein bis zwei Minuten..."
  echo
  python3 -m venv .venv || { echo "  Fehler beim Anlegen der Umgebung."; read -r -p "  Eingabetaste..."; exit 1; }
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade pip
  if ! python -m pip install -e .; then
    echo "  Fehler bei der Installation. Bitte die Meldung oben pruefen."
    read -r -p "  Eingabetaste..."
    exit 1
  fi
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo
echo "  CreatorDock startet - der Browser oeffnet sich gleich automatisch."
echo "  Die Daten liegen in ~/CreatorDock-Daten, nicht im Projektordner."
echo "  Dieses Fenster bitte geoeffnet lassen, solange du das Programm nutzt."
echo "  Zum Beenden hier Strg+C druecken oder das Fenster schliessen."
echo
python -m creatordock.cli gui
