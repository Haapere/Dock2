#!/usr/bin/env bash
# surface-check.sh – prüft auf dem laufenden System, was tatsächlich funktioniert.
# Rein lesend, braucht kein root (ein paar Details bleiben ohne root leer).
#
#   ./surface-check.sh
#   ./surface-check.sh > bericht.txt    # zum Weiterschicken
set -euo pipefail

SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
. "$SKRIPT_DIR/lib/common.sh"
# shellcheck source=lib/surface-model.sh
. "$SKRIPT_DIR/lib/surface-model.sh"

case "${1:-}" in
  -h|--help) sed -n '2,7p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
  "") : ;;
  *) die "Unbekannte Option: $1" ;;
esac

PROBLEME=0

zeile() {
  local status="$1" label="$2" detail="${3:-}"
  local zeichen farbe
  case "$status" in
    ok)   zeichen="✓"; farbe="$C_GREEN" ;;
    warn) zeichen="!"; farbe="$C_YELLOW"; PROBLEME=$((PROBLEME + 1)) ;;
    fail) zeichen="✗"; farbe="$C_RED";    PROBLEME=$((PROBLEME + 1)) ;;
    *)    zeichen="·"; farbe="$C_DIM" ;;
  esac
  printf '%s%s%s %-22s %s\n' "$farbe" "$zeichen" "$C_RESET" "$label" "$detail"
}

# Erstes existierendes Element eines Globs, sonst leer.
erstes_glob() {
  local kandidat
  for kandidat in "$@"; do
    [ -e "$kandidat" ] && { printf '%s' "$kandidat"; return 0; }
  done
  printf ''
}

input_hat() {
  local muster="$1"
  [ -r /proc/bus/input/devices ] || return 1
  grep -qi "N: Name=.*$muster" /proc/bus/input/devices
}

detect_distro
surface_identify

step "Gerät"
zeile info "Modell" "$SURFACE_MODEL"
zeile info "Distribution" "$DISTRO_NAME"

KERNEL="$(uname -r)"
case "$KERNEL" in
  *-surface*) zeile ok "Kernel" "$KERNEL (linux-surface)" ;;
  *)
    if [ "$SURFACE_KERNEL" = "optional" ]; then
      zeile ok "Kernel" "$KERNEL (Standard – für dieses Modell ausreichend)"
    else
      zeile warn "Kernel" "$KERNEL (ohne Surface-Patches; siehe docs/04-surface-optimieren.md)"
    fi
    ;;
esac

step "Boot"
if [ -d /sys/firmware/efi ]; then
  zeile ok "Boot-Modus" "UEFI"
else
  zeile fail "Boot-Modus" "Legacy/BIOS – am Surface bootet das nicht"
fi

SB="unbekannt"
if have mokutil; then
  SB="$(mokutil --sb-state 2>/dev/null | head -n1 || echo unbekannt)"
fi
zeile info "Secure Boot" "$SB"

ROOT_QUELLE=""
if have findmnt; then
  ROOT_QUELLE="$(findmnt -no SOURCE / 2>/dev/null || true)"
  BASIS="$(lsblk -no PKNAME "$ROOT_QUELLE" 2>/dev/null | head -n1 || true)"
  if [ -n "${BASIS:-}" ]; then
    TRAN="$(lsblk -dno TRAN "/dev/$BASIS" 2>/dev/null | tr -d ' ' || true)"
    if [ "$TRAN" = "usb" ]; then
      zeile ok "Systemdatenträger" "/dev/$BASIS (USB) – läuft portabel"
    else
      zeile info "Systemdatenträger" "/dev/$BASIS (${TRAN:-unbekannt})"
    fi
  fi
fi

ESP="$(findmnt -no TARGET /boot/efi 2>/dev/null || echo /boot/efi)"
if [ -f "$ESP/EFI/BOOT/BOOTX64.EFI" ]; then
  zeile ok "EFI-Fallback" "EFI/BOOT/BOOTX64.EFI vorhanden"
else
  zeile fail "EFI-Fallback" "fehlt – Stick erscheint auf fremden Geräten nicht im Bootmenü"
fi

step "Eingabegeräte"
if input_hat "touchscreen\|ipts\|digitizer\|touch"; then
  zeile ok "Touchscreen" "erkannt"
else
  zeile warn "Touchscreen" "nicht gefunden (bei Surface Pro: iptsd installieren)"
fi

if input_hat "pen\|stylus"; then
  zeile ok "Stift" "erkannt"
else
  zeile info "Stift" "nicht gefunden (nur relevant, wenn du einen Surface Pen nutzt)"
fi

if input_hat "type cover\|keyboard"; then
  zeile ok "Tastatur" "erkannt"
else
  zeile warn "Tastatur" "nicht gefunden"
fi

if input_hat "touchpad\|trackpad"; then
  zeile ok "Touchpad" "erkannt"
else
  zeile warn "Touchpad" "nicht gefunden"
fi

step "Funk"
WLAN_PFAD="$(erstes_glob /sys/class/net/wl*)"
if [ -n "$WLAN_PFAD" ]; then
  WLAN_IF="$(basename "$WLAN_PFAD")"
  TREIBER="$(basename "$(readlink -f "$WLAN_PFAD/device/driver" 2>/dev/null)" 2>/dev/null || echo '?')"
  zeile ok "WLAN" "$WLAN_IF (Treiber: $TREIBER)"
else
  zeile fail "WLAN" "kein Interface – siehe docs/troubleshooting.md"
fi

if [ -n "$(erstes_glob /sys/class/bluetooth/hci*)" ]; then
  zeile ok "Bluetooth" "vorhanden"
else
  zeile warn "Bluetooth" "nicht gefunden"
fi

step "Energie und Sensoren"
BAT="$(erstes_glob /sys/class/power_supply/BAT*)"
if [ -n "$BAT" ]; then
  KAP="$(cat "$BAT/capacity" 2>/dev/null || echo '?')"
  zeile ok "Akku" "$(basename "$BAT"), Ladung ${KAP}%"
else
  zeile warn "Akku" "nicht gefunden"
fi

if [ -r /sys/power/mem_sleep ]; then
  zeile info "Standby-Modus" "$(cat /sys/power/mem_sleep)"
fi

if [ -n "$(erstes_glob /sys/bus/iio/devices/iio:device*)" ]; then
  if systemctl is-active --quiet iio-sensor-proxy 2>/dev/null; then
    zeile ok "Lagesensor" "aktiv – Bildschirmdrehung funktioniert"
  else
    zeile warn "Lagesensor" "Hardware da, iio-sensor-proxy läuft nicht"
  fi
else
  zeile warn "Lagesensor" "nicht gefunden"
fi

VIDEO="$(erstes_glob /dev/video*)"
if [ -n "$VIDEO" ]; then
  zeile ok "Kamera" "Gerät vorhanden ($VIDEO)"
else
  zeile info "Kamera" "keine – bei Surface-Geräten normal, Support ist upstream unfertig"
fi

step "Speicher"
MEM_GB="$(awk '/MemTotal/ {printf "%.1f", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo '?')"
zeile info "RAM" "${MEM_GB} GB"
if grep -q zram /proc/swaps 2>/dev/null; then
  ZGROESSE="$(awk '/zram/ {printf "%.1f", $3/1024/1024}' /proc/swaps | head -n1)"
  zeile ok "zram-Swap" "${ZGROESSE} GB aktiv"
else
  zeile warn "zram-Swap" "nicht aktiv (bei 4 GB RAM spürbar) – surface-setup.sh ausführen"
fi
if have df; then
  zeile info "Platz auf /" "$(df -h / | awk 'NR==2 {print $4" frei von "$2}')"
fi

step "Ergebnis"
if [ "$PROBLEME" -eq 0 ]; then
  ok "Alles im grünen Bereich."
else
  warn "$PROBLEME Punkt(e) auffällig – Lösungen in docs/troubleshooting.md."
fi
exit 0
