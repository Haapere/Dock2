# shellcheck shell=bash
# Erkennt das Surface-Modell anhand der DMI-Daten der Firmware und leitet
# daraus ab, was dieses Gerät unter Linux braucht.
#
# Wird per `source` eingebunden. Testbar über:
#   SURFACE_DMI_DIR=tests/fixtures/surface-go-2 ./surface-detect.sh

SURFACE_DMI_DIR="${SURFACE_DMI_DIR:-/sys/class/dmi/id}"

# Liest eine DMI-Datei, leer wenn nicht vorhanden.
_dmi() {
  local datei="$SURFACE_DMI_DIR/$1"
  [ -r "$datei" ] || { printf ''; return 0; }
  tr -d '\0' <"$datei" | head -n1 | sed 's/[[:space:]]*$//' || true
}

# Setzt: SURFACE_IS_SURFACE SURFACE_MODEL SURFACE_FAMILY SURFACE_GEN
#        SURFACE_ARCH SURFACE_IS_ARM SURFACE_KERNEL SURFACE_WIFI
#        SURFACE_CAMERA SURFACE_NOTES SURFACE_SUPPORTED
surface_identify() {
  local vendor produkt version klein
  vendor="$(_dmi sys_vendor)"
  produkt="$(_dmi product_name)"
  version="$(_dmi product_version)"

  SURFACE_MODEL="${produkt:-unbekannt}"
  SURFACE_VENDOR="${vendor:-unbekannt}"
  SURFACE_ARCH="${SURFACE_ARCH_OVERRIDE:-$(uname -m)}"
  SURFACE_IS_ARM=0
  SURFACE_FAMILY="unbekannt"
  SURFACE_GEN=""
  SURFACE_MODELLNUMMER=""
  SURFACE_KERNEL="unbekannt"
  SURFACE_WIFI="unbekannt"
  SURFACE_CAMERA="unbekannt"
  SURFACE_SUPPORTED=1
  SURFACE_NOTES=()

  case "$vendor" in
    *Microsoft*) SURFACE_IS_SURFACE=1 ;;
    *)           SURFACE_IS_SURFACE=0 ;;
  esac

  klein="$(printf '%s %s' "$produkt" "$version" | tr '[:upper:]' '[:lower:]')"
  case "$klein" in *surface*) SURFACE_IS_SURFACE=1 ;; esac

  if [ "$SURFACE_IS_SURFACE" -ne 1 ]; then
    SURFACE_FAMILY="kein-surface"
    SURFACE_SUPPORTED=0
    SURFACE_NOTES+=("Das ist kein Surface-Gerät – die Surface-spezifischen Schritte entfallen.")
    return 0
  fi

  # Generation = letzte Zahl im Produktnamen (»Surface Go 2« → 2).
  # Vierstellige Zahlen sind Modellnummern (1926, 1866, …), keine Generation.
  # Achtung: ohne »|| true« killt ein Treffer-loses grep unter pipefail das Skript.
  SURFACE_GEN="$(printf '%s' "$produkt" | grep -oE '[0-9]+' | tail -n1 || true)"
  if [ -n "$SURFACE_GEN" ] && [ "$SURFACE_GEN" -ge 100 ] 2>/dev/null; then
    SURFACE_MODELLNUMMER="$SURFACE_GEN"
    SURFACE_GEN=""
  fi
  # Die Modellnummer (z. B. 1926) steht meist in product_version.
  if [ -z "$SURFACE_MODELLNUMMER" ]; then
    SURFACE_MODELLNUMMER="$(printf '%s' "$version" | grep -oE '[0-9]{4}' | tail -n1 || true)"
  fi

  case "$klein" in
    *"pro x"*)          SURFACE_FAMILY="pro-x"; SURFACE_IS_ARM=1 ;;
    *"laptop go"*)      SURFACE_FAMILY="laptop-go"; : "${SURFACE_GEN:=1}" ;;
    *"laptop studio"*)  SURFACE_FAMILY="laptop-studio"; : "${SURFACE_GEN:=1}" ;;
    *laptop*)           SURFACE_FAMILY="laptop"; : "${SURFACE_GEN:=1}" ;;
    *book*)             SURFACE_FAMILY="book"; : "${SURFACE_GEN:=1}" ;;
    *studio*)           SURFACE_FAMILY="studio" ;;
    *go*)               SURFACE_FAMILY="go"; : "${SURFACE_GEN:=1}" ;;
    *pro*)              SURFACE_FAMILY="pro"; : "${SURFACE_GEN:=5}" ;;
    *"surface 3"*)      SURFACE_FAMILY="surface3"; SURFACE_GEN=3 ;;
    *)                  SURFACE_FAMILY="unbekannt" ;;
  esac

  case "$SURFACE_ARCH" in aarch64|arm64) SURFACE_IS_ARM=1 ;; esac

  if [ "$SURFACE_IS_ARM" -eq 1 ]; then
    SURFACE_SUPPORTED=0
    SURFACE_KERNEL="nicht-verfuegbar"
    SURFACE_NOTES+=("ARM-Surface (Snapdragon/SQ): gewöhnliche x86-Live-Systeme booten hier nicht.")
    SURFACE_NOTES+=("Siehe docs/troubleshooting.md, Abschnitt »ARM-Surfaces«.")
    return 0
  fi

  case "$SURFACE_FAMILY" in
    go)
      SURFACE_KERNEL="optional"
      SURFACE_CAMERA="nein"
      if [ "${SURFACE_GEN:-1}" -le 1 ] 2>/dev/null; then
        SURFACE_WIFI="qualcomm-atheros"
      else
        SURFACE_WIFI="intel"
      fi
      SURFACE_NOTES+=("Surface Go: Touch, Stift, Type Cover, WLAN und Sensoren laufen bereits mit dem Standard-Kernel.")
      SURFACE_NOTES+=("Secure Boot kann deshalb eingeschaltet bleiben – kein BitLocker-Risiko.")
      SURFACE_NOTES+=("Nur ein USB-C-Port: Stick möglichst direkt anstecken, Strom über Surface Connect.")
      ;;
    pro)
      SURFACE_KERNEL="empfohlen"
      SURFACE_CAMERA="nein"
      if [ "${SURFACE_GEN:-5}" -le 6 ] 2>/dev/null; then
        SURFACE_WIFI="marvell"
        SURFACE_NOTES+=("Marvell-WLAN: braucht die Firmware aus linux-firmware; unter Arch zusätzlich linux-firmware-marvell.")
      else
        SURFACE_WIFI="intel"
      fi
      SURFACE_NOTES+=("Surface Pro: Touchscreen und Stift laufen über IPTS – dafür linux-surface-Kernel + iptsd installieren.")
      ;;
    laptop|laptop-go|laptop-studio)
      SURFACE_KERNEL="empfohlen"
      SURFACE_CAMERA="nein"
      if [ "$SURFACE_FAMILY" = "laptop" ] && [ "${SURFACE_GEN:-1}" -le 2 ] 2>/dev/null; then
        SURFACE_WIFI="marvell"
      else
        SURFACE_WIFI="intel"
      fi
      SURFACE_NOTES+=("Tastatur und Touchpad hängen am Surface Aggregator Module – ohne passende Kernel-Module bleiben sie tot.")
      SURFACE_NOTES+=("Vor dem Umbau eine USB-Tastatur bereitlegen.")
      ;;
    book)
      SURFACE_KERNEL="empfohlen"
      SURFACE_CAMERA="nein"
      SURFACE_WIFI="marvell"
      SURFACE_NOTES+=("Surface Book: dGPU und das Abdocken des Displays brauchen den linux-surface-Kernel.")
      ;;
    surface3|studio)
      SURFACE_KERNEL="empfohlen"
      SURFACE_CAMERA="nein"
      SURFACE_NOTES+=("Älteres bzw. seltenes Modell – Support im linux-surface-Wiki gegenprüfen.")
      ;;
    *)
      SURFACE_KERNEL="empfohlen"
      SURFACE_NOTES+=("Modell nicht in der internen Tabelle – die Angaben von surface-check.sh sind hier maßgeblich.")
      ;;
  esac
}

_kernel_text() {
  case "$1" in
    optional)          printf 'nicht nötig (Standard-Kernel reicht)' ;;
    empfohlen)         printf 'empfohlen' ;;
    nicht-verfuegbar)  printf 'nicht verfügbar' ;;
    *)                 printf 'unklar' ;;
  esac
}

_wifi_text() {
  case "$1" in
    intel)             printf 'Intel (läuft ab Werk)' ;;
    marvell)           printf 'Marvell (Firmware nötig)' ;;
    qualcomm-atheros)  printf 'Qualcomm Atheros (läuft ab Werk)' ;;
    *)                 printf 'unbekannt' ;;
  esac
}

# Menschenlesbarer Bericht auf stdout.
surface_report() {
  printf 'Gerät:            %s\n' "$SURFACE_MODEL"
  printf 'Hersteller:       %s\n' "$SURFACE_VENDOR"
  printf 'Architektur:      %s\n' "$SURFACE_ARCH"
  [ -n "${SURFACE_MODELLNUMMER:-}" ] && printf 'Modellnummer:     %s\n' "$SURFACE_MODELLNUMMER"
  printf 'Familie:          %s%s\n' "$SURFACE_FAMILY" \
    "$([ -n "$SURFACE_GEN" ] && printf ' (Generation %s)' "$SURFACE_GEN")"
  printf 'Surface-Kernel:   %s\n' "$(_kernel_text "$SURFACE_KERNEL")"
  printf 'WLAN:             %s\n' "$(_wifi_text "$SURFACE_WIFI")"
  printf 'Kameras:          %s\n' "${SURFACE_CAMERA:-unbekannt}"
  if [ "${#SURFACE_NOTES[@]}" -gt 0 ]; then
    printf 'Hinweise:\n'
    local n
    for n in "${SURFACE_NOTES[@]}"; do printf '  · %s\n' "$n"; done
  fi
}

_json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

surface_json() {
  printf '{\n'
  printf '  "modell": "%s",\n'         "$(_json_escape "$SURFACE_MODEL")"
  printf '  "hersteller": "%s",\n'     "$(_json_escape "$SURFACE_VENDOR")"
  printf '  "familie": "%s",\n'        "$(_json_escape "$SURFACE_FAMILY")"
  printf '  "generation": "%s",\n'     "$(_json_escape "$SURFACE_GEN")"
  printf '  "modellnummer": "%s",\n'  "$(_json_escape "${SURFACE_MODELLNUMMER:-}")"
  printf '  "architektur": "%s",\n'    "$(_json_escape "$SURFACE_ARCH")"
  printf '  "ist_arm": %s,\n'          "$([ "$SURFACE_IS_ARM" -eq 1 ] && echo true || echo false)"
  printf '  "ist_surface": %s,\n'      "$([ "$SURFACE_IS_SURFACE" -eq 1 ] && echo true || echo false)"
  printf '  "unterstuetzt": %s,\n'     "$([ "$SURFACE_SUPPORTED" -eq 1 ] && echo true || echo false)"
  printf '  "surface_kernel": "%s",\n' "$(_json_escape "$SURFACE_KERNEL")"
  printf '  "wlan": "%s",\n'           "$(_json_escape "$SURFACE_WIFI")"
  printf '  "kameras": "%s"\n'         "$(_json_escape "${SURFACE_CAMERA:-unbekannt}")"
  printf '}\n'
}
