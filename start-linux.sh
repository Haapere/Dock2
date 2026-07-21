#!/bin/bash
# ============================================================
#  StrategyLab starten (Linux).
#  Ausfuehrbar machen mit:  chmod +x start-linux.sh
#  Danach doppelklicken oder im Terminal ./start-linux.sh
#  Beim ersten Start wird alles automatisch eingerichtet.
# ============================================================
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo
  echo "  Python 3 wurde nicht gefunden."
  echo "  Bitte ueber die Paketverwaltung installieren, z. B.:"
  echo "    sudo apt install python3 python3-venv python3-pip"
  echo
  read -r -p "  Zum Schliessen die Eingabetaste druecken..."
  exit 1
fi

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
echo "  StrategyLab startet - der Browser oeffnet sich gleich automatisch."
echo "  Dieses Fenster bitte geoeffnet lassen, solange du das Programm nutzt."
echo "  Zum Beenden hier Strg+C druecken."
echo
python -m strategylab.cli gui
