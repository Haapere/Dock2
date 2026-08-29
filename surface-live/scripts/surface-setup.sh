#!/usr/bin/env bash
# surface-setup.sh – macht ein frisch auf einen USB-Datenträger installiertes
# Linux zu einem portablen, surface-tauglichen System.
#
# Ausführen als root auf dem installierten System (nicht im Live-System!):
#   sudo ./surface-setup.sh
#   sudo ./surface-setup.sh --surface-kernel   # zusätzlich linux-surface-Kernel
#   ./surface-setup.sh --dry-run               # nur zeigen, nichts ändern
#
# Optionen:
#   --dry-run          zeigt jede Änderung an, führt keine aus
#   --yes              keine Rückfragen
#   --surface-kernel   linux-surface-Kernel + iptsd installieren
#   --skip-portable    EFI-Fallback nicht anfassen
#   --skip-tuning      keine Anpassungen für RAM/Schreiblast
#   --efi-dir VERZ     EFI-Partition abweichend von /boot/efi
#   --force            auch auf nicht-USB-Datenträgern arbeiten (gefährlich)
set -euo pipefail

SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
. "$SKRIPT_DIR/lib/common.sh"
# shellcheck source=lib/surface-model.sh
. "$SKRIPT_DIR/lib/surface-model.sh"

SURFACE_KERNEL_INSTALLIEREN=0
SKIP_PORTABLE=0
SKIP_TUNING=0
FORCE=0
EFI_DIR=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)        DRY_RUN=1 ;;
    --yes|-y)         ASSUME_YES=1 ;;
    --surface-kernel) SURFACE_KERNEL_INSTALLIEREN=1 ;;
    --skip-portable)  SKIP_PORTABLE=1 ;;
    --skip-tuning)    SKIP_TUNING=1 ;;
    --force)          FORCE=1 ;;
    --efi-dir)        shift; EFI_DIR="${1:-}" ;;
    -h|--help)        sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)                die "Unbekannte Option: $1 (--help für Hilfe)" ;;
  esac
  shift
done

need_root "$@"
detect_distro
surface_identify

GEAENDERT=()
NACHHER=()

# ---------------------------------------------------------------- Übersicht
step "1/6  System"
printf 'Distribution:     %s\n' "$DISTRO_NAME"
printf 'Kernel:           %s\n' "$(uname -r)"
surface_report
[ "$DRY_RUN" = "1" ] && warn "Dry-Run: es wird nichts geschrieben."

if [ -z "$PKG_MANAGER" ]; then
  warn "Paketmanager nicht erkannt – Pakete musst du selbst installieren."
fi

# --------------------------------------------------- EFI-Fallback (portabel)
# Ohne EFI/BOOT/BOOTX64.EFI taucht der Stick am Surface gar nicht erst im
# Bootmenü auf: fremde Rechner kennen den NVRAM-Eintrag des Installers nicht.
esp_ermitteln() {
  if [ -n "$EFI_DIR" ]; then printf '%s' "$EFI_DIR"; return 0; fi
  local ziel=""
  if have findmnt; then
    ziel="$(findmnt -no TARGET /boot/efi 2>/dev/null || true)"
  fi
  [ -n "$ziel" ] || ziel="/boot/efi"
  printf '%s' "$ziel"
}

datentraeger_pruefen() {
  local esp="$1" quelle basis transport
  have findmnt || { warn "findmnt fehlt – Datenträgerprüfung übersprungen."; return 0; }
  quelle="$(findmnt -no SOURCE "$esp" 2>/dev/null || true)"
  [ -n "$quelle" ] || { warn "EFI-Partition $esp ist nicht eingehängt."; return 1; }
  if have lsblk; then
    basis="$(lsblk -no PKNAME "$quelle" 2>/dev/null | head -n1 || true)"
    if [ -n "$basis" ]; then
      transport="$(lsblk -dno TRAN "/dev/$basis" 2>/dev/null | tr -d ' ' || true)"
      printf 'EFI-Partition:    %s (Datenträger /dev/%s, Anbindung: %s)\n' \
        "$quelle" "$basis" "${transport:-unbekannt}"
      if [ "$transport" != "usb" ] && [ "$FORCE" -ne 1 ]; then
        err "Das hier ist kein USB-Datenträger – vermutlich läuft das Skript auf der internen Platte."
        hint "Auf einem fremden PC würde das den Windows-Bootloader-Fallback überschreiben."
        hint "Wenn du sicher bist: nochmal mit --force starten."
        return 1
      fi
    fi
  fi
  return 0
}

portabel_machen() {
  local esp="$1" quelle="" datei
  for datei in ubuntu debian fedora Linux; do
    [ -d "$esp/EFI/$datei" ] && { quelle="$esp/EFI/$datei"; break; }
  done
  if [ -z "$quelle" ]; then
    err "Keinen Bootloader unter $esp/EFI gefunden – ist das die richtige EFI-Partition?"
    return 1
  fi
  info "Bootloader gefunden: $quelle"

  # Bevorzugt der offizielle Weg – der setzt Shim und GRUB korrekt.
  local erfolg=0
  if have grub-install; then
    if run grub-install --target=x86_64-efi --efi-directory="$esp" --removable --recheck; then
      erfolg=1
    else
      warn "grub-install --removable schlug fehl, kopiere die Dateien von Hand."
    fi
  fi

  if [ "$erfolg" -ne 1 ]; then
    run mkdir -p "$esp/EFI/BOOT"
    backup_once "$esp/EFI/BOOT/BOOTX64.EFI"
    if [ -f "$quelle/shimx64.efi" ]; then
      run cp -a "$quelle/shimx64.efi" "$esp/EFI/BOOT/BOOTX64.EFI"
      [ -f "$quelle/grubx64.efi" ] && run cp -a "$quelle/grubx64.efi" "$esp/EFI/BOOT/grubx64.efi"
      [ -f "$quelle/mmx64.efi" ]   && run cp -a "$quelle/mmx64.efi"   "$esp/EFI/BOOT/mmx64.efi"
    elif [ -f "$quelle/grubx64.efi" ]; then
      run cp -a "$quelle/grubx64.efi" "$esp/EFI/BOOT/BOOTX64.EFI"
    else
      err "Weder shimx64.efi noch grubx64.efi in $quelle gefunden."
      return 1
    fi
  fi

  if [ "$DRY_RUN" = "1" ] || [ -f "$esp/EFI/BOOT/BOOTX64.EFI" ]; then
    ok "EFI-Fallback vorhanden: EFI/BOOT/BOOTX64.EFI – der Stick bootet jetzt auf fremden Geräten."
    GEAENDERT+=("EFI-Fallback (EFI/BOOT/BOOTX64.EFI)")
  else
    err "EFI-Fallback wurde nicht angelegt."
    return 1
  fi
}

step "2/6  Stick auf fremden Geräten bootfähig machen"
if [ "$SKIP_PORTABLE" -eq 1 ]; then
  info "übersprungen (--skip-portable)"
else
  ESP="$(esp_ermitteln)"
  if datentraeger_pruefen "$ESP"; then
    portabel_machen "$ESP" || warn "EFI-Fallback nicht gesetzt – siehe docs/troubleshooting.md."
  else
    warn "EFI-Schritt übersprungen."
  fi
fi

# --------------------------------------------------------------- GRUB-Config
step "3/6  Bootloader-Einstellungen"
if [ -f /etc/default/grub ]; then
  # Sonst sammelt der Stick die Windows-Einträge jedes Rechners ein, an dem er hängt.
  ensure_kv /etc/default/grub GRUB_DISABLE_OS_PROBER 'GRUB_DISABLE_OS_PROBER=true'
  ensure_kv /etc/default/grub GRUB_TIMEOUT 'GRUB_TIMEOUT=3'
  ensure_kv /etc/default/grub GRUB_TIMEOUT_STYLE 'GRUB_TIMEOUT_STYLE=menu'
  GEAENDERT+=("GRUB: os-prober aus, Timeout 3 s")
  if have update-grub; then
    run update-grub
  elif have grub2-mkconfig; then
    run grub2-mkconfig -o /boot/grub2/grub.cfg
  fi
else
  info "Kein /etc/default/grub – übersprungen."
fi

# ----------------------------------------------------- Tuning für USB + 4 GB
fstab_noatime() {
  local datei=/etc/fstab neu
  [ -f "$datei" ] || return 0
  neu="$(awk 'BEGIN{OFS="\t"}
    /^[[:space:]]*#/ {print; next}
    NF>=4 && $2=="/" { if ($4 !~ /(^|,)noatime(,|$)/) $4=$4",noatime" }
    {print}' "$datei")"
  if [ "$neu" = "$(cat "$datei")" ]; then
    hint "fstab: noatime steht schon"
    return 0
  fi
  backup_once "$datei"
  printf '%s\n' "$neu" | write_file "$datei"
  GEAENDERT+=("fstab: noatime für /")
}

step "4/6  Anpassungen für USB-Betrieb und 4 GB RAM"
if [ "$SKIP_TUNING" -eq 1 ]; then
  info "übersprungen (--skip-tuning)"
else
  fstab_noatime

  write_file /etc/sysctl.d/99-surface-usb.conf <<'EOF'
# Von surface-setup.sh angelegt.
# Wenig RAM + zram: Auslagern ist billig, also aggressiv nutzen.
vm.swappiness = 100
vm.vfs_cache_pressure = 50
# Seltener auf den Stick schreiben – schont Flash und spart Wartezeit.
vm.dirty_writeback_centisecs = 1500
EOF
  GEAENDERT+=("sysctl: swappiness/zram-Tuning")

  write_file /etc/systemd/journald.conf.d/99-surface-usb.conf <<'EOF'
# Von surface-setup.sh angelegt: Logs in den RAM statt auf den Stick.
[Journal]
Storage=volatile
RuntimeMaxUse=32M
EOF
  GEAENDERT+=("journald: Logs im RAM")

  if [ "$PKG_MANAGER" = "apt" ]; then
    if pkg_installed zram-tools; then
      hint "zram-tools ist schon installiert"
    else
      pkg_refresh
      pkg_install zram-tools || warn "zram-tools konnte nicht installiert werden."
    fi
    write_file /etc/default/zramswap <<'EOF'
# Von surface-setup.sh angelegt.
ALGO=zstd
PERCENT=50
PRIORITY=100
EOF
    run_soft systemctl enable --now zramswap.service || warn "zramswap.service startete nicht – nach dem Neustart prüfen."
    GEAENDERT+=("zram-Swap (50 % des RAM, zstd)")

    if pkg_installed iio-sensor-proxy; then
      hint "iio-sensor-proxy ist schon installiert"
    else
      pkg_install iio-sensor-proxy || warn "iio-sensor-proxy fehlt – automatische Bildschirmdrehung bleibt aus."
    fi
    GEAENDERT+=("iio-sensor-proxy (Bildschirmdrehung)")
  elif [ "$PKG_MANAGER" = "dnf" ]; then
    pkg_install zram-generator-defaults iio-sensor-proxy || true
  else
    warn "zram und iio-sensor-proxy bitte manuell installieren."
  fi
fi

# ------------------------------------------------------ linux-surface-Kernel
secure_boot_an() {
  if have mokutil; then
    mokutil --sb-state 2>/dev/null | grep -qi enabled && return 0
    return 1
  fi
  local var
  var="$(find /sys/firmware/efi/efivars -maxdepth 1 -name 'SecureBoot-*' 2>/dev/null | head -n1)"
  [ -n "$var" ] && [ "$(od -An -t u1 -j 4 -N 1 "$var" 2>/dev/null | tr -d ' ')" = "1" ]
}

surface_repo_apt() {
  local key=/usr/share/keyrings/linux-surface.gpg
  local liste=/etc/apt/sources.list.d/linux-surface.list
  local key_url="https://raw.githubusercontent.com/linux-surface/linux-surface/master/pkg/keys/surface.asc"

  if [ -f "$key" ]; then
    hint "Signaturschlüssel liegt schon vor"
  else
    have curl || have wget || die "curl oder wget wird gebraucht."
    if [ "$DRY_RUN" = "1" ]; then
      printf '%s[dry-run]%s Schlüssel von %s holen → %s\n' "$C_DIM" "$C_RESET" "$key_url" "$key"
    else
      if have curl; then
        curl -fsSL "$key_url" | gpg --dearmor >"$key"
      else
        wget -qO- "$key_url" | gpg --dearmor >"$key"
      fi
      ok "Signaturschlüssel importiert"
    fi
  fi

  printf 'deb [arch=amd64 signed-by=%s] https://pkg.surfacelinux.com/debian release main\n' "$key" \
    | write_file "$liste"
  pkg_refresh
}

surface_kernel_apt() {
  local pakete=(linux-image-surface linux-headers-surface iptsd)
  # libwacom-surface ist auf Ubuntu 26.04 / Debian testing defekt (Paketkonflikt)
  if [ "$DISTRO_ID" = "ubuntu" ] && version_ge "${DISTRO_VERSION:-0}" "26.04"; then
    warn "libwacom-surface wird auf Ubuntu ${DISTRO_VERSION} ausgelassen (bekannter Paketfehler)."
  else
    pakete+=(libwacom-surface)
  fi
  pkg_install "${pakete[@]}"

  if secure_boot_an; then
    info "Secure Boot ist aktiv – der Surface-Kernel braucht einen eigenen Schlüssel."
    pkg_install linux-surface-secureboot-mok
    NACHHER+=("Beim nächsten Start erscheint der blaue MokManager: »Enroll MOK« → Continue → Yes → Passwort: surface (US-Tastatur!).")
  fi
  if have update-grub; then run update-grub; fi
  return 0
}

surface_kernel_dnf() {
  run dnf config-manager --add-repo=https://pkg.surfacelinux.com/fedora/linux-surface.repo \
    || run dnf config-manager addrepo --from-repofile=https://pkg.surfacelinux.com/fedora/linux-surface.repo
  run dnf install -y --allowerasing kernel-surface iptsd libwacom-surface
  if secure_boot_an; then
    run dnf install -y surface-secureboot
    run_soft systemctl enable --now linux-surface-default-watchdog.path
    NACHHER+=("Beim nächsten Start MokManager: »Enroll MOK« → Passwort: surface (US-Tastatur!).")
  fi
}

surface_kernel_pacman() {
  local key_url="https://raw.githubusercontent.com/linux-surface/linux-surface/master/pkg/keys/surface.asc"
  if [ "$DRY_RUN" = "1" ]; then
    printf '%s[dry-run]%s pacman-key mit %s\n' "$C_DIM" "$C_RESET" "$key_url"
  else
    curl -s "$key_url" | pacman-key --add -
    pacman-key --lsign-key 56C464BAAC421453
  fi
  if ! grep -q '^\[linux-surface\]' /etc/pacman.conf 2>/dev/null; then
    backup_once /etc/pacman.conf
    if [ "$DRY_RUN" = "1" ]; then
      printf '%s[dry-run]%s [linux-surface]-Repo an /etc/pacman.conf anhängen\n' "$C_DIM" "$C_RESET"
    else
      printf '\n[linux-surface]\nServer = https://pkg.surfacelinux.com/arch/\n' >>/etc/pacman.conf
    fi
  fi
  pkg_refresh
  pkg_install linux-surface linux-surface-headers iptsd
  if [ "$SURFACE_WIFI" = "marvell" ]; then pkg_install linux-firmware-marvell; fi
  return 0
}

step "5/6  linux-surface-Kernel"
if [ "$SURFACE_KERNEL_INSTALLIEREN" -ne 1 ]; then
  case "$SURFACE_KERNEL" in
    optional)
      ok "Für dieses Modell nicht nötig – übersprungen."
      hint "Falls doch etwas fehlt: sudo $0 --surface-kernel"
      ;;
    *)
      warn "Für dieses Modell empfohlen, aber nicht angefordert."
      hint "Nachrüsten mit: sudo $0 --surface-kernel"
      ;;
  esac
else
  if [ "$SURFACE_IS_ARM" -eq 1 ]; then
    die "ARM-Surface – es gibt keinen linux-surface-Kernel dafür."
  fi
  info "Installiere linux-surface-Kernel (Quelle: pkg.surfacelinux.com)."
  case "$PKG_MANAGER" in
    apt)    surface_repo_apt; surface_kernel_apt ;;
    dnf)    surface_kernel_dnf ;;
    pacman) surface_kernel_pacman ;;
    *)      die "Für diese Distribution ist der Weg nicht hinterlegt – siehe docs/04-surface-optimieren.md." ;;
  esac
  GEAENDERT+=("linux-surface-Kernel + iptsd")
  NACHHER+=("Nach dem Neustart prüfen: uname -r muss auf »-surface« enden.")
fi

# ----------------------------------------------------------- Zusammenfassung
step "6/6  Zusammenfassung"
if [ "${#GEAENDERT[@]}" -eq 0 ]; then
  info "Nichts geändert."
else
  ok "Erledigt:"
  for e in "${GEAENDERT[@]}"; do printf '   · %s\n' "$e"; done
fi

if [ "${#NACHHER[@]}" -gt 0 ]; then
  step "Das kommt beim nächsten Start auf dich zu"
  for n in "${NACHHER[@]}"; do printf '   · %s\n' "$n"; done
fi

step "Nächste Schritte"
printf '   1. Herunterfahren, Stick an den USB-C-Port des Surface stecken.\n'
printf '   2. Lautstärke-LEISER halten, Power kurz drücken → Bootmenü → USB wählen.\n'
printf '   3. Nach dem Start: ./surface-check.sh   (zeigt, was tatsächlich läuft)\n'
[ "$DRY_RUN" = "1" ] && warn "Das war ein Dry-Run – es wurde nichts geändert."
exit 0
