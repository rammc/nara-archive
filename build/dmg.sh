#!/usr/bin/env bash
#
# Wrap dist/actari.app into a signed, notarized .dmg.
#
# Usage:
#   build/dmg.sh path/to/output.dmg path/to/NARA\ Archive.app
#
# Prerequisites:
#   - `brew install create-dmg`
#   - the .app must already be signed + notarized (run build/sign-and-notarize.sh)
#   - same Apple credentials as sign-and-notarize.sh (see env list there)

set -euo pipefail

DMG_OUT="${1:?usage: dmg.sh OUTPUT.dmg APP_PATH}"
APP="${2:?usage: dmg.sh OUTPUT.dmg APP_PATH}"

if ! command -v create-dmg >/dev/null 2>&1; then
  echo "error: create-dmg not installed. \`brew install create-dmg\`" >&2
  exit 1
fi

if [[ ! -d "$APP" ]]; then
  echo "error: $APP not found" >&2
  exit 1
fi

# --- build the DMG ------------------------------------------------------

BG_OPT=()
if [[ -f build/dmg-background.png ]]; then
  BG_OPT=(--background "build/dmg-background.png")
else
  echo "note: build/dmg-background.png missing — DMG will use plain background."
fi

VOLICON_OPT=()
if [[ -f build/actari.icns ]]; then
  VOLICON_OPT=(--volicon "build/actari.icns")
fi

# Remove a stale output file — create-dmg refuses to overwrite.
rm -f "$DMG_OUT"

echo "==> creating $DMG_OUT"
# ``${VAR[@]+"${VAR[@]}"}`` is the safe-expansion idiom for empty bash arrays
# under ``set -u`` — without it, an unset optional flag list errors with
# "unbound variable" the moment we expand the array. Both flag arrays here
# are populated conditionally (icon / background may be missing on a fresh
# checkout); we always want their absence to mean "skip this flag".
create-dmg \
  --volname "actari" \
  "${VOLICON_OPT[@]+"${VOLICON_OPT[@]}"}" \
  "${BG_OPT[@]+"${BG_OPT[@]}"}" \
  --window-pos 200 120 \
  --window-size 600 380 \
  --icon-size 100 \
  --icon "$(basename "$APP")" 150 180 \
  --hide-extension "$(basename "$APP")" \
  --app-drop-link 450 180 \
  --hdiutil-quiet \
  "$DMG_OUT" \
  "$APP"

# --- sign + notarize the DMG itself ------------------------------------
# Stapling the .app is enough for Gatekeeper, but signing the DMG too gives
# the cleaner "no warning ever" experience users expect from polished apps.

if [[ -n "${APPLE_DEVELOPER_ID:-}" ]]; then
  echo "==> signing DMG"
  codesign --force --sign "$APPLE_DEVELOPER_ID" --timestamp "$DMG_OUT"
fi

if [[ -n "${APPLE_ID:-}" && -n "${APPLE_APP_SPECIFIC_PASSWORD:-}" && -n "${APPLE_TEAM_ID:-}" ]]; then
  echo "==> notarizing DMG"
  xcrun notarytool submit "$DMG_OUT" \
    --apple-id "$APPLE_ID" \
    --password "$APPLE_APP_SPECIFIC_PASSWORD" \
    --team-id "$APPLE_TEAM_ID" \
    --wait

  echo "==> stapling DMG"
  xcrun stapler staple "$DMG_OUT"
  xcrun stapler validate "$DMG_OUT"
fi

echo "==> done. $DMG_OUT"
