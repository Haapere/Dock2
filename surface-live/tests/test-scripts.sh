#!/usr/bin/env bash
# Testet die surface-live-Skripte ohne echte Surface-Hardware.
#   ./tests/test-scripts.sh
set -uo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASIS="$(dirname "$TEST_DIR")"
SCRIPTS="$BASIS/scripts"

FEHLER=0
OK=0

pruefe() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf '  ✓ %s\n' "$name"; OK=$((OK + 1))
  else
    printf '  ✗ %s\n' "$name"; FEHLER=$((FEHLER + 1))
  fi
}

enthaelt() {
  local name="$1" muster="$2" ausgabe="$3"
  if printf '%s' "$ausgabe" | grep -qi -- "$muster"; then
    printf '  ✓ %s\n' "$name"; OK=$((OK + 1))
  else
    printf '  ✗ %s (»%s« fehlt)\n' "$name" "$muster"; FEHLER=$((FEHLER + 1))
    printf '%s\n' "$ausgabe" | sed 's/^/      /'
  fi
}

printf '\nSyntax\n'
while IFS= read -r datei; do
  pruefe "bash -n $(basename "$datei")" bash -n "$datei"
done < <(find "$BASIS" -name '*.sh' | sort)

printf '\nModellerkennung\n'
AUSGABE="$(SURFACE_DMI_DIR="$TEST_DIR/fixtures/surface-go-2" NO_COLOR=1 "$SCRIPTS/surface-detect.sh" 2>&1)"
enthaelt "Go 2 wird erkannt"            "Surface Go 2"                "$AUSGABE"
enthaelt "Go 2: Familie go"             "Familie:          go"        "$AUSGABE"
enthaelt "Go 2: Kernel nicht nötig"     "nicht nötig"                 "$AUSGABE"
enthaelt "Go 2: Intel-WLAN"             "Intel"                       "$AUSGABE"

AUSGABE="$(SURFACE_DMI_DIR="$TEST_DIR/fixtures/surface-go-2" NO_COLOR=1 "$SCRIPTS/surface-detect.sh" --json 2>&1)"
enthaelt "JSON: familie go"             '"familie": "go"'             "$AUSGABE"
enthaelt "JSON: unterstuetzt true"      '"unterstuetzt": true'        "$AUSGABE"

AUSGABE="$(SURFACE_DMI_DIR="$TEST_DIR/fixtures/surface-pro-7" NO_COLOR=1 "$SCRIPTS/surface-detect.sh" 2>&1)"
enthaelt "Pro 7: Familie pro"           "Familie:          pro"       "$AUSGABE"
enthaelt "Pro 7: Kernel empfohlen"      "empfohlen"                   "$AUSGABE"
enthaelt "Pro 7: IPTS-Hinweis"          "IPTS"                        "$AUSGABE"

AUSGABE="$(SURFACE_DMI_DIR="$TEST_DIR/fixtures/surface-pro-x" SURFACE_ARCH_OVERRIDE=aarch64 NO_COLOR=1 "$SCRIPTS/surface-detect.sh" 2>&1)"
enthaelt "Pro X: als ARM erkannt"       "ARM-Surface"                 "$AUSGABE"

AUSGABE="$(SURFACE_DMI_DIR="$TEST_DIR/fixtures/kein-surface" NO_COLOR=1 "$SCRIPTS/surface-detect.sh" 2>&1)"
enthaelt "Fremdgerät erkannt"           "Kein Surface"                "$AUSGABE"

printf '\nDry-Run von surface-setup.sh\n'
MARKER=/etc/sysctl.d/99-surface-usb.conf
VORHER="nein"; [ -e "$MARKER" ] && VORHER="ja"
AUSGABE="$(SURFACE_DMI_DIR="$TEST_DIR/fixtures/surface-go-2" NO_COLOR=1 "$SCRIPTS/surface-setup.sh" --dry-run --yes 2>&1)"
STATUS=$?
if [ "$STATUS" -eq 0 ]; then
  printf '  ✓ läuft ohne root durch\n'; OK=$((OK + 1))
else
  printf '  ✗ Abbruch mit Status %s\n' "$STATUS"; FEHLER=$((FEHLER + 1))
  printf '%s\n' "$AUSGABE" | sed 's/^/      /'
fi
enthaelt "meldet Dry-Run"               "Dry-Run"                     "$AUSGABE"
enthaelt "erkennt das Go 2"             "Surface Go 2"                "$AUSGABE"
enthaelt "Kernel-Schritt übersprungen"  "nicht nötig"                 "$AUSGABE"

NACHHER="nein"; [ -e "$MARKER" ] && NACHHER="ja"
if [ "$VORHER" = "$NACHHER" ]; then
  printf '  ✓ Dry-Run hat nichts geschrieben\n'; OK=$((OK + 1))
else
  printf '  ✗ Dry-Run hat %s angelegt!\n' "$MARKER"; FEHLER=$((FEHLER + 1))
fi

AUSGABE="$(SURFACE_DMI_DIR="$TEST_DIR/fixtures/surface-pro-7" NO_COLOR=1 "$SCRIPTS/surface-setup.sh" --dry-run --yes --surface-kernel 2>&1)"
enthaelt "Kernel-Pfad: Repo-URL"        "pkg.surfacelinux.com"        "$AUSGABE"
enthaelt "Kernel-Pfad: Paketliste"      "linux-image-surface"         "$AUSGABE"

AUSGABE="$(SURFACE_DMI_DIR="$TEST_DIR/fixtures/surface-pro-x" SURFACE_ARCH_OVERRIDE=aarch64 NO_COLOR=1 "$SCRIPTS/surface-setup.sh" --dry-run --yes --surface-kernel 2>&1)"
enthaelt "ARM: Kernel wird verweigert"  "ARM-Surface"                 "$AUSGABE"

printf '\nsurface-check.sh\n'
AUSGABE="$(NO_COLOR=1 "$SCRIPTS/surface-check.sh" 2>&1)"
enthaelt "Bericht mit Boot-Abschnitt"   "Boot"                        "$AUSGABE"
enthaelt "Bericht mit Speicher"         "RAM"                         "$AUSGABE"

printf '\n%s bestanden, %s fehlgeschlagen\n\n' "$OK" "$FEHLER"
[ "$FEHLER" -eq 0 ]
