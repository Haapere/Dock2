# shellcheck shell=bash
# Gemeinsame Helfer für die surface-live-Skripte.
# Wird per `source` eingebunden, nicht direkt ausgeführt.

# Farben nur, wenn wirklich ein Terminal dranhängt
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_BLUE=$'\033[34m'
else
  C_RESET=''; C_BOLD=''; C_DIM=''
  C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''
fi

DRY_RUN="${DRY_RUN:-0}"
ASSUME_YES="${ASSUME_YES:-0}"

log()   { printf '%s\n' "$*"; }
info()  { printf '%s→%s %s\n' "$C_BLUE" "$C_RESET" "$*"; }
ok()    { printf '%s✓%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn()  { printf '%s!%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
err()   { printf '%s✗%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; }
die()   { err "$*"; exit 1; }
step()  { printf '\n%s%s%s\n' "$C_BOLD" "$*" "$C_RESET"; }
hint()  { printf '  %s%s%s\n' "$C_DIM" "$*" "$C_RESET"; }

have() { command -v "$1" >/dev/null 2>&1; }

# Führt ein Kommando aus – oder zeigt es nur an, wenn --dry-run aktiv ist.
run() {
  if [ "$DRY_RUN" = "1" ]; then
    printf '%s[dry-run]%s %s\n' "$C_DIM" "$C_RESET" "$*"
    return 0
  fi
  "$@"
}

# Wie run(), aber ein Fehlschlag ist kein Abbruchgrund.
run_soft() {
  if [ "$DRY_RUN" = "1" ]; then
    printf '%s[dry-run]%s %s\n' "$C_DIM" "$C_RESET" "$*"
    return 0
  fi
  "$@" || return $?
}

need_root() {
  if [ "$(id -u)" -ne 0 ]; then
    if [ "$DRY_RUN" = "1" ]; then
      warn "Kein root – im Dry-Run ist das in Ordnung, es wird nichts geschrieben."
      return 0
    fi
    die "Bitte mit sudo starten: sudo $0 $*"
  fi
}

confirm() {
  local frage="$1"
  [ "$ASSUME_YES" = "1" ] && return 0
  [ "$DRY_RUN" = "1" ] && return 0
  local antwort
  printf '%s [j/N] ' "$frage"
  read -r antwort || antwort=""
  case "$antwort" in
    j|J|ja|Ja|y|Y|yes) return 0 ;;
    *) return 1 ;;
  esac
}

# Legt genau einmal eine .bak-Kopie an (idempotent).
backup_once() {
  local datei="$1"
  [ -f "$datei" ] || return 0
  [ -f "${datei}.surface-live.bak" ] && return 0
  run cp -a "$datei" "${datei}.surface-live.bak"
}

# Stellt sicher, dass eine Zeile in einer Datei steht. Ein vorhandener
# Schlüssel (KEY=…) wird ersetzt, sonst wird angehängt.
ensure_kv() {
  local datei="$1" schluessel="$2" zeile="$3"
  if [ -f "$datei" ] && grep -q "^[[:space:]]*${schluessel}=" "$datei"; then
    if grep -qxF "$zeile" "$datei"; then
      hint "$(basename "$datei"): $schluessel steht schon richtig"
      return 0
    fi
    backup_once "$datei"
    run sed -i "s|^[[:space:]]*${schluessel}=.*|${zeile}|" "$datei"
    ok "$(basename "$datei"): $schluessel angepasst"
  else
    [ -f "$datei" ] && backup_once "$datei"
    if [ "$DRY_RUN" = "1" ]; then
      printf '%s[dry-run]%s anhängen an %s: %s\n' "$C_DIM" "$C_RESET" "$datei" "$zeile"
    else
      printf '%s\n' "$zeile" >>"$datei"
    fi
    ok "$(basename "$datei"): $schluessel gesetzt"
  fi
}

# Schreibt eine Datei aus stdin – dry-run-fest.
write_file() {
  local ziel="$1"
  local inhalt
  inhalt="$(cat)"
  if [ "$DRY_RUN" = "1" ]; then
    printf '%s[dry-run]%s schreibe %s:\n' "$C_DIM" "$C_RESET" "$ziel"
    printf '%s\n' "$inhalt" | sed 's/^/    /'
    return 0
  fi
  mkdir -p "$(dirname "$ziel")"
  printf '%s\n' "$inhalt" >"$ziel"
  ok "geschrieben: $ziel"
}

# --- Distribution erkennen ------------------------------------------------
# Setzt: DISTRO_ID, DISTRO_LIKE, DISTRO_VERSION, DISTRO_NAME, PKG_MANAGER
# (die Variablen werden von den aufrufenden Skripten gelesen)
# shellcheck disable=SC1090,SC2034
detect_distro() {
  DISTRO_ID="unbekannt"; DISTRO_LIKE=""; DISTRO_VERSION=""; DISTRO_NAME="unbekannt"
  local os_release="${OS_RELEASE_FILE:-/etc/os-release}"
  if [ -r "$os_release" ]; then
    # shellcheck disable=SC1090
    DISTRO_ID="$(. "$os_release"; printf '%s' "${ID:-unbekannt}")"
    DISTRO_LIKE="$(. "$os_release"; printf '%s' "${ID_LIKE:-}")"
    DISTRO_VERSION="$(. "$os_release"; printf '%s' "${VERSION_ID:-}")"
    DISTRO_NAME="$(. "$os_release"; printf '%s' "${PRETTY_NAME:-unbekannt}")"
  fi

  case "$DISTRO_ID $DISTRO_LIKE" in
    *debian*|*ubuntu*) PKG_MANAGER="apt" ;;
    *fedora*|*rhel*)   PKG_MANAGER="dnf" ;;
    *arch*)            PKG_MANAGER="pacman" ;;
    *)                 PKG_MANAGER="" ;;
  esac
}

# Installiert Pakete über den passenden Paketmanager.
pkg_install() {
  [ "$#" -gt 0 ] || return 0
  case "$PKG_MANAGER" in
    apt)    run env DEBIAN_FRONTEND=noninteractive apt-get install -y "$@" ;;
    dnf)    run dnf install -y "$@" ;;
    pacman) run pacman -S --needed --noconfirm "$@" ;;
    *)      warn "Unbekannter Paketmanager – bitte manuell installieren: $*"; return 1 ;;
  esac
}

pkg_installed() {
  case "$PKG_MANAGER" in
    apt)    dpkg-query -W -f='${db:Status-Status}' "$1" 2>/dev/null | grep -q '^installed$' ;;
    dnf)    rpm -q "$1" >/dev/null 2>&1 ;;
    pacman) pacman -Qi "$1" >/dev/null 2>&1 ;;
    *)      return 1 ;;
  esac
}

pkg_refresh() {
  case "$PKG_MANAGER" in
    apt)    run apt-get update ;;
    dnf)    : ;;
    pacman) run pacman -Sy ;;
    *)      return 0 ;;
  esac
}

# Vergleicht Versionen: version_ge "26.04" "26.04" → wahr
version_ge() {
  [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]
}
