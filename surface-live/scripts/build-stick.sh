#!/usr/bin/env bash
# build-stick.sh – baut aus der laufenden Live-Sitzung heraus ein vollständiges,
# portables Linux auf einen USB-Datenträger. Ersetzt das Klicken im Installer.
#
# In der Live-Sitzung (»Try Ubuntu«) starten:
#   sudo ./build-stick.sh --watch            # wartet auf den Stick und legt los
#   sudo ./build-stick.sh /dev/sdc           # Zielgerät direkt angeben
#   ./build-stick.sh --dry-run /dev/sdc      # nur zeigen, was passieren würde
#
# Optionen:
#   --watch            wartet, bis ein USB-Datenträger eingesteckt wird
#   --benutzer NAME    Benutzername (sonst Rückfrage)
#   --rechnername NAME Hostname, Standard: surface
#   --dry-run          zeigt jeden Schritt, führt keinen aus
#   --yes              keine Rückfragen (Achtung: löscht das Ziel ohne Nachfrage)
#   --force            auch nicht-USB-Datenträger zulassen (sehr gefährlich)
#   --min-groesse GB   Mindestgröße des Ziels, Standard: 28
#
# Das Ziel wird VOLLSTÄNDIG GELÖSCHT.
set -euo pipefail

SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
. "$SKRIPT_DIR/lib/common.sh"

ZIEL=""
WATCH=0
BENUTZER=""
RECHNERNAME="surface"
FORCE=0
MIN_GB=28
MNT=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --watch)        WATCH=1 ;;
    --benutzer)     shift; BENUTZER="${1:-}" ;;
    --rechnername)  shift; RECHNERNAME="${1:-surface}" ;;
    --min-groesse)  shift; MIN_GB="${1:-28}" ;;
    --dry-run)      DRY_RUN=1 ;;
    --yes|-y)       ASSUME_YES=1 ;;
    --force)        FORCE=1 ;;
    -h|--help)      sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)             die "Unbekannte Option: $1 (--help für Hilfe)" ;;
    *)              ZIEL="$1" ;;
  esac
  shift
done

need_root
detect_distro

[ "$PKG_MANAGER" = "apt" ] || die "Dieses Skript setzt eine Ubuntu-/Debian-Live-Sitzung voraus."

# ---------------------------------------------------------------- Hilfsmittel
# Datenträger, auf dem ein Pfad liegt (z. B. das laufende Live-System).
traeger_von() {
  local pfad="$1" quelle basis
  quelle="$(findmnt -no SOURCE --target "$pfad" 2>/dev/null | head -n1 || true)"
  [ -n "$quelle" ] || return 0
  basis="$(lsblk -no PKNAME "$quelle" 2>/dev/null | head -n1 || true)"
  if [ -n "$basis" ]; then
    printf '/dev/%s' "$basis"
  else
    # Kein übergeordneter Datenträger: das Dateisystem liegt direkt auf dem Gerät.
    printf '%s' "$quelle"
  fi
}

# Ist irgendetwas von diesem Datenträger als / oder /cdrom eingehängt?
traegt_laufendes_system() {
  lsblk -lnpo NAME,MOUNTPOINTS "$1" 2>/dev/null \
    | awk '$2=="/" || $2=="/cdrom" || $2=="/rofs" {gefunden=1} END {exit !gefunden}'
}

usb_datentraeger() {
  lsblk -dpno NAME,TYPE,TRAN 2>/dev/null | awk '$2=="disk" && $3=="usb" {print $1}'
}

groesse_gb() {
  local bytes
  bytes="$(lsblk -bdno SIZE "$1" 2>/dev/null | head -n1 || echo 0)"
  printf '%d' "$((bytes / 1000000000))"
}

beschreibung() {
  lsblk -dno MODEL,SIZE,TRAN "$1" 2>/dev/null | sed 's/[[:space:]]\+/ /g;s/^ //' | head -n1
}

# ------------------------------------------------------------ Ziel bestimmen
auf_stick_warten() {
  local vorher jetzt neu
  vorher="$(usb_datentraeger | sort)"
  # Alle Meldungen nach stderr: stdout trägt ausschließlich den Gerätenamen.
  step "Warte auf den Stick" >&2
  info "Jetzt den Ziel-Stick einstecken. Abbruch mit Strg+C." >&2
  hint "Bereits angeschlossen: $(printf '%s' "$vorher" | tr '\n' ' ')" >&2
  while true; do
    sleep 2
    jetzt="$(usb_datentraeger | sort)"
    neu="$(comm -13 <(printf '%s\n' "$vorher") <(printf '%s\n' "$jetzt") | head -n1)"
    if [ -n "$neu" ]; then
      # Kurz warten, bis der Kernel alle Partitionen eingelesen hat.
      sleep 2
      ok "Neuer Datenträger erkannt: $neu — $(beschreibung "$neu")" >&2
      printf '%s' "$neu"
      return 0
    fi
    vorher="$jetzt"
  done
}

ziel_pruefen() {
  local dev="$1" gb tran
  [ -b "$dev" ] || die "$dev ist kein Blockgerät."
  [ "$(lsblk -dno TYPE "$dev" | head -n1)" = "disk" ] || die "$dev ist eine Partition – bitte den ganzen Datenträger angeben (z. B. /dev/sdc)."

  local live_root live_iso
  live_root="$(traeger_von / || true)"
  live_iso="$(traeger_von /cdrom || true)"
  [ "$dev" = "${live_root:-}" ] && die "$dev trägt das laufende System. Abbruch."
  [ "$dev" = "${live_iso:-}" ] && die "$dev ist der Installer-Stick, von dem du gerade bootest. Abbruch."
  if traegt_laufendes_system "$dev"; then
    die "$dev ist gerade als / bzw. /cdrom eingehängt – das ist das laufende System. Abbruch."
  fi

  tran="$(lsblk -dno TRAN "$dev" | head -n1 | tr -d ' ')"
  if [ "$tran" != "usb" ] && [ "$FORCE" -ne 1 ]; then
    err "$dev ist nicht per USB angeschlossen (Anbindung: ${tran:-unbekannt})."
    hint "Das sieht nach einer internen Platte aus. Wenn du absolut sicher bist: --force."
    exit 1
  fi

  gb="$(groesse_gb "$dev")"
  if [ "$gb" -lt "$MIN_GB" ]; then
    die "$dev hat nur ${gb} GB, gebraucht werden mindestens ${MIN_GB} GB."
  fi
  return 0
}

if [ "$WATCH" -eq 1 ]; then
  [ -n "$ZIEL" ] && die "--watch und ein Zielgerät schließen sich aus."
  ZIEL="$(auf_stick_warten)"
fi
[ -n "$ZIEL" ] || die "Kein Ziel angegeben. --watch oder Gerät nennen (z. B. /dev/sdc)."
ziel_pruefen "$ZIEL"

# --------------------------------------------------------------- Bestätigung
step "Ziel"
printf 'Gerät:       %s\n' "$ZIEL"
printf 'Beschreibung:%s\n' " $(beschreibung "$ZIEL")"
printf 'Größe:       %s GB\n' "$(groesse_gb "$ZIEL")"
echo
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINTS "$ZIEL" 2>/dev/null || true

warn "ALLE DATEN auf $ZIEL werden gelöscht."
if ! confirm "Fortfahren?"; then
  info "Abgebrochen – nichts verändert."
  exit 0
fi

# ------------------------------------------------------------- Zugangsdaten
if [ -z "$BENUTZER" ]; then
  if [ "$DRY_RUN" = "1" ]; then
    BENUTZER="benutzer"
  else
    read -r -p "Benutzername für das neue System: " BENUTZER
  fi
fi
printf '%s' "$BENUTZER" | grep -qE '^[a-z_][a-z0-9_-]*$' \
  || die "Ungültiger Benutzername: nur Kleinbuchstaben, Ziffern, - und _."

PASSWORT=""
if [ "$DRY_RUN" != "1" ]; then
  while :; do
    read -r -s -p "Passwort: " PASSWORT; echo
    read -r -s -p "Passwort wiederholen: " PASSWORT2; echo
    [ -n "$PASSWORT" ] && [ "$PASSWORT" = "$PASSWORT2" ] && break
    warn "Passwörter stimmen nicht überein oder sind leer."
  done
fi

# ----------------------------------------------------------------- Werkzeuge
step "1/8  Werkzeuge prüfen"
FEHLENDE=()
for werkzeug in rsync sgdisk mkfs.ext4 mkfs.vfat; do
  have "$werkzeug" || FEHLENDE+=("$werkzeug")
done
if [ "${#FEHLENDE[@]}" -gt 0 ]; then
  info "Nachinstallieren: ${FEHLENDE[*]}"
  pkg_refresh
  pkg_install rsync gdisk e2fsprogs dosfstools
else
  ok "Alles vorhanden."
fi

# --------------------------------------------------------------- Partitionen
step "2/8  Partitionieren"
for part in $(lsblk -lnpo NAME "$ZIEL" | tail -n +2); do
  run_soft umount -q "$part" || true
done
run wipefs -a "$ZIEL"
run sgdisk --zap-all "$ZIEL"
run sgdisk -n1:0:+512M -t1:ef00 -c1:"EFI" "$ZIEL"
run sgdisk -n2:0:0     -t2:8300 -c2:"linux" "$ZIEL"
run partprobe "$ZIEL"
run udevadm settle

# nvme0n1p1 vs sdc1
if printf '%s' "$ZIEL" | grep -qE '[0-9]$'; then
  P1="${ZIEL}p1"; P2="${ZIEL}p2"
else
  P1="${ZIEL}1";  P2="${ZIEL}2"
fi
ok "EFI: $P1   System: $P2"

step "3/8  Formatieren"
run mkfs.vfat -F32 -n SURFACE_EFI "$P1"
run mkfs.ext4 -F -L surface-linux "$P2"

# ------------------------------------------------------------------ Kopieren
step "4/8  System kopieren"
if [ "$DRY_RUN" = "1" ]; then
  MNT="/tmp/surface-stick.dry-run"
else
  MNT="$(mktemp -d /tmp/surface-stick.XXXXXX)"
fi
run mount "$P2" "$MNT"
run mkdir -p "$MNT/boot/efi"
run mount "$P1" "$MNT/boot/efi"

info "Kopiere das laufende System – das dauert 10 bis 20 Minuten."
run rsync -aHAX --info=progress2 \
  --exclude=/dev/\* --exclude=/proc/\* --exclude=/sys/\* --exclude=/run/\* \
  --exclude=/tmp/\* --exclude=/mnt/\* --exclude=/media/\* --exclude=/cdrom/\* \
  --exclude=/rofs/\* --exclude=/swapfile --exclude=/lost+found \
  --exclude=/var/log/\* --exclude=/var/cache/apt/archives/\*.deb \
  --exclude="$MNT" \
  / "$MNT/"

# ---------------------------------------------------------------- Konfiguration
step "5/8  System einrichten"
UUID_ROOT="$(blkid -s UUID -o value "$P2" 2>/dev/null || echo ROOT-UUID)"
UUID_EFI="$(blkid -s UUID -o value "$P1" 2>/dev/null || echo EFI-UUID)"

write_file "$MNT/etc/fstab" <<EOF
# Von build-stick.sh erzeugt.
UUID=$UUID_ROOT  /          ext4  defaults,noatime  0 1
UUID=$UUID_EFI   /boot/efi  vfat  umask=0077        0 1
tmpfs            /tmp       tmpfs defaults,noatime,mode=1777 0 0
EOF

write_file "$MNT/etc/hostname" <<EOF
$RECHNERNAME
EOF

write_file "$MNT/etc/hosts" <<EOF
127.0.0.1   localhost
127.0.1.1   $RECHNERNAME
::1         localhost ip6-localhost ip6-loopback
ff02::1     ip6-allnodes
ff02::2     ip6-allrouters
EOF

# Chroot vorbereiten
for verz in /dev /dev/pts /proc /sys /run; do
  run mkdir -p "$MNT$verz"
  run mount --bind "$verz" "$MNT$verz"
done

im_chroot() {
  if [ "$DRY_RUN" = "1" ]; then
    printf '%s[dry-run]%s chroot: %s\n' "$C_DIM" "$C_RESET" "$*"
    return 0
  fi
  chroot "$MNT" /bin/bash -c "$*"
}

# Live-Ballast entfernen – sonst startet das System wieder als Live-Sitzung.
step "6/8  Live-Bestandteile entfernen"
for paket in casper lupin-casper ubiquity ubiquity-casper ubiquity-frontend-gtk \
             ubuntu-desktop-bootstrap live-installer; do
  im_chroot "dpkg -s $paket >/dev/null 2>&1 && DEBIAN_FRONTEND=noninteractive apt-get purge -y $paket || true"
done
im_chroot "rm -f /etc/sudoers.d/*casper* /etc/sudoers.d/*live* /etc/systemd/system/*live*"
im_chroot "sed -i '/AutomaticLogin/d;/AutomaticLoginEnable/d' /etc/gdm3/custom.conf 2>/dev/null || true"
im_chroot "id ubuntu >/dev/null 2>&1 && deluser --remove-home ubuntu || true"
# Neue Maschinen-Identität, sonst kollidieren DHCP-Leases mit dem Live-System.
im_chroot ": > /etc/machine-id; rm -f /var/lib/dbus/machine-id"

step "7/8  Benutzer und Bootloader"
im_chroot "useradd -m -s /bin/bash -c '$BENUTZER' -G sudo,adm,dip,plugdev,lpadmin,cdrom $BENUTZER"
if [ "$DRY_RUN" = "1" ]; then
  printf '%s[dry-run]%s chroot: Passwort für %s setzen\n' "$C_DIM" "$C_RESET" "$BENUTZER"
else
  printf '%s:%s' "$BENUTZER" "$PASSWORT" | chroot "$MNT" chpasswd
fi
unset PASSWORT PASSWORT2 2>/dev/null || true

im_chroot "DEBIAN_FRONTEND=noninteractive apt-get install -y grub-efi-amd64 grub-efi-amd64-signed shim-signed"
# --removable schreibt EFI/BOOT/BOOTX64.EFI und fasst den NVRAM nicht an:
# genau das macht den Stick auf fremden Geräten bootfähig.
im_chroot "grub-install --target=x86_64-efi --efi-directory=/boot/efi --removable --no-nvram --recheck"
im_chroot "update-initramfs -c -k all"
im_chroot "update-grub"

step "8/8  Surface-Feinschliff"
run mkdir -p "$MNT/opt/surface-live"
run cp -a "$(dirname "$SKRIPT_DIR")/." "$MNT/opt/surface-live/"
im_chroot "/opt/surface-live/scripts/surface-setup.sh --yes --skip-portable"

# ------------------------------------------------------------------ Aufräumen
aufraeumen() {
  [ -n "$MNT" ] || return 0
  [ "$DRY_RUN" = "1" ] && return 0
  local verz
  for verz in /run /sys /proc /dev/pts /dev; do
    umount -lq "$MNT$verz" 2>/dev/null || true
  done
  umount -q "$MNT/boot/efi" 2>/dev/null || true
  umount -q "$MNT" 2>/dev/null || true
  rmdir "$MNT" 2>/dev/null || true
}
trap aufraeumen EXIT

run sync
aufraeumen
trap - EXIT

step "Fertig"
ok "$ZIEL trägt jetzt ein vollständiges, portables Linux."
printf '   Benutzer:     %s\n' "$BENUTZER"
printf '   Rechnername:  %s\n' "$RECHNERNAME"
echo
printf '   1. Herunterfahren, Stick abziehen.\n'
printf '   2. Am Surface: Lautstärke LEISER halten, Power kurz drücken → Bootmenü.\n'
printf '   3. Nach dem Start: /opt/surface-live/scripts/surface-check.sh\n'
[ "$DRY_RUN" = "1" ] && warn "Das war ein Dry-Run – es wurde nichts verändert."
exit 0
