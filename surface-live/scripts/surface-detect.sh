#!/usr/bin/env bash
# surface-detect.sh – erkennt das Surface-Modell und sagt, was es unter Linux braucht.
#
#   ./surface-detect.sh            # lesbarer Bericht
#   ./surface-detect.sh --json     # maschinenlesbar
#
# Testbar ohne Surface:
#   SURFACE_DMI_DIR=../tests/fixtures/surface-go-2 ./surface-detect.sh
set -euo pipefail

SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
. "$SKRIPT_DIR/lib/common.sh"
# shellcheck source=lib/surface-model.sh
. "$SKRIPT_DIR/lib/surface-model.sh"

AUSGABE="text"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --json) AUSGABE="json" ;;
    -h|--help)
      sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) die "Unbekannte Option: $1 (--help für Hilfe)" ;;
  esac
  shift
done

surface_identify

if [ "$AUSGABE" = "json" ]; then
  surface_json
  exit 0
fi

step "Geräteerkennung"
surface_report

detect_distro
printf 'Distribution:     %s\n' "$DISTRO_NAME"

step "Empfehlung"
if [ "$SURFACE_IS_SURFACE" -ne 1 ]; then
  info "Kein Surface erkannt. Wenn du gerade den USB-Stick auf einem anderen PC baust, ist das genau richtig so."
  hint "Die Surface-Schritte laufen später auf dem Surface selbst."
elif [ "$SURFACE_IS_ARM" -eq 1 ]; then
  err "ARM-Surface: dieser Weg funktioniert hier nicht."
  hint "Details in docs/troubleshooting.md → »ARM-Surfaces«."
  exit 2
else
  case "$SURFACE_KERNEL" in
    optional)
      ok "Standard-Kernel genügt – kein Eingriff in Secure Boot nötig."
      hint "sudo ./surface-setup.sh"
      ;;
    *)
      info "Für volle Hardware-Unterstützung den linux-surface-Kernel mitinstallieren:"
      hint "sudo ./surface-setup.sh --surface-kernel"
      ;;
  esac
fi
