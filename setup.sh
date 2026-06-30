#!/bin/bash
# Setup-Script für Dating App Automation
set -e

echo "=== Dating App Automation Setup ==="

# Python-Version prüfen
if ! python3 --version | grep -qE "3\.(10|11|12)"; then
  echo "FEHLER: Python 3.10+ wird benötigt (gefunden: $(python3 --version))"
  exit 1
fi

# pip installieren falls nicht vorhanden
python3 -m ensurepip --upgrade 2>/dev/null || true

# Dependencies
echo "Installiere Python-Pakete..."
pip install -r requirements.txt -q

# Playwright Browser
echo "Installiere Chromium..."
playwright install chromium

# .env anlegen falls nicht vorhanden
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "WICHTIG: ANTHROPIC_API_KEY in .env eintragen!"
  echo "  Schlüssel holen unter: https://console.anthropic.com"
fi

# Ordner anlegen
mkdir -p photos sessions

echo ""
echo "=== Setup abgeschlossen ==="
echo ""
echo "Nächste Schritte:"
echo "  1. Fotos in den Ordner 'photos/' legen"
echo "  2. config.yaml anpassen (Name, Bio, etc.)"
echo "  3. ANTHROPIC_API_KEY in .env eintragen"
echo "  4. python main.py komplett"
