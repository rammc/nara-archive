# Convenience targets for the macOS .app + DMG build pipeline.
#
# Most contributors won't touch this — pip install + pytest cover their flow.
# This file is for the maintainer building releases.
#
# Prerequisites for `make app` (and beyond):
#   - macOS host
#   - Python 3.12 universal2 installed from python.org (NOT homebrew)
#   - `pip install -e ".[mac,dev]"` in an active venv
#
# Prerequisites for `make sign` / `make dmg`:
#   - Apple Developer Program membership
#   - Developer ID Application certificate in Keychain Access
#   - APPLE_DEVELOPER_ID / APPLE_ID / APPLE_APP_SPECIFIC_PASSWORD /
#     APPLE_TEAM_ID env vars exported (see docs/RELEASE.md)
#   - `brew install create-dmg`

PROJECT_ROOT := $(shell pwd)
DIST_DIR     := $(PROJECT_ROOT)/dist
APP          := $(DIST_DIR)/NARA Archive.app
ICONSET      := $(PROJECT_ROOT)/build/nara-archive.iconset
ICNS         := $(PROJECT_ROOT)/build/nara-archive.icns
VERSION      := $(shell python -c "import importlib.util,pathlib; s=pathlib.Path('src/nara/__init__.py').read_text(); ns={}; exec(s, ns); print(ns['__version__'])")
DMG          := $(DIST_DIR)/NARA-Archive-$(VERSION).dmg

PYTHON ?= python

.PHONY: help icons app sign dmg notarize-dmg clean check-arch

help:  ## list available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

icons: $(ICNS)  ## (re)generate placeholder .icns from PNGs

$(ICNS): $(ICONSET)/icon_512x512.png
	@iconutil -c icns "$(ICONSET)" -o "$(ICNS)"

$(ICONSET)/icon_512x512.png:
	@echo "generating placeholder icons (replace with real artwork later)…"
	@$(PYTHON) build/generate-placeholder-icons.py

app: icons  ## build dist/NARA Archive.app via PyInstaller
	@$(MAKE) check-arch
	@rm -rf "$(DIST_DIR)" build/work
	@pyinstaller --noconfirm --workpath build/work --distpath "$(DIST_DIR)" build/nara-archive.spec
	@echo
	@echo "Built: $(APP)"
	@file "$(APP)/Contents/MacOS/nara-archive"

check-arch:  ## warn if the host Python isn't universal2
	@PY_ARCHES=$$($(PYTHON) -c "import sysconfig; print(sysconfig.get_platform())"); \
	if ! echo "$$PY_ARCHES" | grep -q universal2; then \
		echo "WARNING: host Python is '$$PY_ARCHES', not universal2."; \
		echo "         The .app will only run on this host's architecture."; \
		echo "         For universal binaries, install Python from python.org's"; \
		echo "         universal2 installer (NOT Homebrew)."; \
	fi

sign:  ## codesign the .app (requires APPLE_DEVELOPER_ID etc.)
	@bash build/sign-and-notarize.sh

dmg:  ## create + sign + notarize the DMG (requires create-dmg + Apple creds)
	@bash build/dmg.sh "$(DMG)" "$(APP)"

clean:  ## remove build/, dist/, generated icons
	@rm -rf build/work build/nara-archive.icns build/nara-archive.iconset/*.png "$(DIST_DIR)"
	@echo "cleaned."
