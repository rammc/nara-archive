# Release runbook (macOS DMG)

Tagging `vX.Y.Z` triggers `.github/workflows/release-mac.yml`, which builds an
arm64 (Apple Silicon) `.app`, signs and notarizes it with Apple, wraps it in a
`.dmg`, notarizes that too, and uploads the result to the GitHub Release. See
[Architecture coverage](#architecture-coverage-v09x) below.

This document is the one-time setup the maintainer has to do **before** the
first release tag will succeed. After that, releasing is `git tag vX.Y.Z &&
git push --tags` plus a 15-minute wait for Apple's notary service.

## One-time setup checklist

- [ ] **Apple Developer Program** membership is active
  ($99/year — https://developer.apple.com/programs/).

- [ ] **Developer ID Application certificate** exists in Keychain Access.
  Generate from https://developer.apple.com/account/resources/certificates
  → "+" → "Developer ID Application" → follow the CSR flow.

- [ ] **Export the certificate as a `.p12`** with a strong password:
  Keychain Access → right-click the cert → Export → save as `.p12`.

- [ ] **Base64-encode the `.p12`** so it survives the GitHub Secrets store:
  ```bash
  base64 -i ~/Downloads/actari-cert.p12 | pbcopy
  ```

- [ ] **Generate an App-Specific Password** at https://appleid.apple.com
  → Sign In → App-Specific Passwords → "+". Label it `actari-notary`.

- [ ] **Find your Team ID** at https://developer.apple.com/account → Membership.
  Ten-character string, e.g. `AB12CD34EF`.

- [ ] **Add the seven secrets** to the repo (Settings → Secrets and variables
  → Actions):

  | Name | Value |
  | --- | --- |
  | `APPLE_DEVELOPER_ID` | `Developer ID Application: Christopher Ramm (TEAMID)` — copy verbatim from `security find-identity` |
  | `APPLE_ID` | Your Apple ID email |
  | `APPLE_APP_SPECIFIC_PASSWORD` | The password generated above |
  | `APPLE_TEAM_ID` | Ten-character team ID |
  | `APPLE_DEVELOPER_CERT_P12` | The base64 blob from the `pbcopy` step |
  | `APPLE_DEVELOPER_CERT_PASSWORD` | The password you used when exporting the `.p12` |
  | `KEYCHAIN_PASSWORD` | Any random string — used for the ephemeral CI keychain |

- [ ] **Smoke-test with a release-candidate tag** before announcing:
  ```bash
  git tag v0.9.0-rc1
  git push origin v0.9.0-rc1
  ```
  Watch the workflow at `https://github.com/rammc/actari/actions`.
  First runs typically fail twice on certificate plumbing — budget for it.

## Cutting a real release

1. Bump `__version__` in `src/actari/__init__.py` and `pyproject.toml`.
2. Update `CHANGELOG.md`.
3. Commit: `chore: bump to vX.Y.Z`.
4. Tag and push:
   ```bash
   git tag vX.Y.Z
   git push origin main vX.Y.Z
   ```
5. Wait ~15 minutes; the DMG appears on the release page.
6. Verify on a clean Mac user account: download → drag to Applications →
   double-click. **No Gatekeeper warning should appear.**

## When notarization fails

- **"Code object is not signed at all"** — the `--deep` flag in
  `build/sign-and-notarize.sh` should cover this. If it still fires, a new
  nested binary appeared in the bundle; switch to a recursive sign loop.
- **"Hardened Runtime is not enabled"** — check that `--options runtime` is
  present in the `codesign` invocation.
- **"The signature does not include a secure timestamp"** — check `--timestamp`
  is present and Apple's timestamp server (`timestamp.apple.com`) is reachable.
- **Stuck "In Progress" for over 30 minutes** — Apple's notary service is slow
  that day. The workflow has a 45-minute timeout. Re-run after it clears.

## Architecture coverage (v0.9.x)

Current DMGs are **arm64 (Apple Silicon) only.** The CI runs on `macos-14`
which is an Apple-Silicon GitHub runner, and the bundled C-extension
wheels (Pillow, pydantic-core, …) are arm64-specific on that host. Intel
Macs (pre-2020) can't run the resulting `.app`.

Roadmap: add a parallel build on `macos-13` (Intel) and merge the two
`.app` bundles with `lipo` in a follow-up job. Until then, Intel users
fall back to the `pipx install actari` CLI path.

## Local dry-run

```bash
# Generates placeholder icons + builds an unsigned arm64-only .app for testing
make app

# Right-click the resulting dist/actari.app → Open → Open (bypasses
# Gatekeeper for THIS user only). Browser opens; setup wizard appears.
```

For a real universal build locally, install the python.org universal2 Python
into your venv and re-run `make app`. The Makefile prints a warning if the
host Python is single-arch.
