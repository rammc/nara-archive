#!/usr/bin/env bash
#
# Sign and notarize dist/NARA Archive.app for distribution outside the
# Mac App Store. Run after `make app` produced a working bundle.
#
# Required environment variables (export them in your shell or set them in
# the GitHub Actions secrets — see docs/RELEASE.md):
#
#   APPLE_DEVELOPER_ID            "Developer ID Application: Name (TEAMID)"
#   APPLE_ID                      Apple ID email used for notarytool auth
#   APPLE_APP_SPECIFIC_PASSWORD   generated at appleid.apple.com
#   APPLE_TEAM_ID                 10-character team ID
#
# Exit codes:
#   0  success — app is signed, notarized, stapled, and Gatekeeper-clean.
#   1  one of the required env vars is missing.
#   2  codesign / notarization / staple failed (see the log right above).

set -euo pipefail

APP="${APP:-dist/NARA Archive.app}"
ENTITLEMENTS="${ENTITLEMENTS:-build/entitlements.plist}"

# --- env validation ------------------------------------------------------

missing=()
for var in APPLE_DEVELOPER_ID APPLE_ID APPLE_APP_SPECIFIC_PASSWORD APPLE_TEAM_ID; do
  if [[ -z "${!var:-}" ]]; then missing+=("$var"); fi
done
if (( ${#missing[@]} > 0 )); then
  echo "error: missing required env vars: ${missing[*]}" >&2
  echo "see docs/RELEASE.md for how to obtain them." >&2
  exit 1
fi

if [[ ! -d "$APP" ]]; then
  echo "error: $APP not found. Run \`make app\` first." >&2
  exit 1
fi

if [[ ! -f "$ENTITLEMENTS" ]]; then
  echo "error: $ENTITLEMENTS missing." >&2
  exit 1
fi

# --- sign ---------------------------------------------------------------
# --deep is deprecated but still the practical choice for PyInstaller bundles
# that contain dozens of nested unsigned .so / .dylib files. If Apple ever
# removes it, switch to a recursive find+codesign loop.

echo "==> signing $APP with $APPLE_DEVELOPER_ID"
codesign --deep --force --options runtime --timestamp \
  --entitlements "$ENTITLEMENTS" \
  --sign "$APPLE_DEVELOPER_ID" \
  "$APP"

echo "==> verifying signature"
codesign --verify --deep --strict --verbose=2 "$APP"

# --- notarize ----------------------------------------------------------

echo "==> zipping for notarytool"
ZIP="dist/NARA-Archive-notarize.zip"
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"

echo "==> submitting to Apple notary service (this can take 1-10 minutes)"
xcrun notarytool submit "$ZIP" \
  --apple-id "$APPLE_ID" \
  --password "$APPLE_APP_SPECIFIC_PASSWORD" \
  --team-id "$APPLE_TEAM_ID" \
  --wait

# --- staple ------------------------------------------------------------

echo "==> stapling notarization ticket"
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"

# --- final Gatekeeper check ---

echo "==> Gatekeeper assessment"
spctl --assess --type execute --verbose=4 "$APP"

# Clean up the notarization zip — it served its purpose.
rm -f "$ZIP"

echo "==> done. $APP is signed, notarized, and stapled."
