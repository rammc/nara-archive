# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] — 2026-05-21

First stable release.

### Highlights

- Local web UI with **Discovery**, **Downloads**, and **Library** tabs,
  served at `http://127.0.0.1:8765`.
- **Signed, notarized macOS DMG** — drag-to-Applications, no Gatekeeper
  warning, no terminal required.
- **Bulk download** of NARA record series as one consolidated PDF per
  File Unit, with state tracking, resumable runs, and atomic writes.
- **Optional OCR text layer** on the assembled PDFs via ocrmypdf +
  Tesseract; defaults to English + German for the captured-records corpus.
- **Optional image recompression** — shrinks output PDFs 5–10× while
  keeping typewritten text readable.
- **macOS Keychain integration** for API-key storage in the bundled app
  (TOML still used for pipx installs).
- **Curated starter searches** (8 bundled, plus user-extensible via
  `~/.actari/presets.json`) targeting IG-Farben / WWII industrial /
  Nuremberg-trials research.
- **Friendly first-run wizard** + welcome banner; empty-state hints on
  every tab.

### Breaking changes from pre-1.0

- **Project renamed** from `nara-archive` to `actari`
  (Latin: *acta* = records, *agere* = to act). Old name carried potential
  trademark concerns with the U.S. National Archives.
- **CLI command:** `nara` → `actari`.
- **Config directory:** `~/.nara/` → `~/.actari/` (auto-migrated on
  first run; helper is removed in v2.0).
- **macOS Bundle ID:** `dev.cramm.nara-archive` → `dev.cramm.actari`.
- **macOS Keychain service** renamed; existing bundled-app users will be
  prompted to re-enter their API key on first launch.
- **DMG asset filename:** `NARA-Archive-x.y.z.dmg` → `actari-x.y.z.dmg`.
- **Repository moved:** <https://github.com/rammc/nara-archive> →
  <https://github.com/rammc/actari>. GitHub's automatic redirects keep
  old URLs working; bookmarks should be updated.

### Why "actari"?

The previous name carried trademark risk with the U.S. National Archives
and Records Administration (NARA). The new name is etymologically
grounded in archival work without any institutional attachment, and was
verified available on PyPI, npm, and major domain registrars.

The string **"NARA"** still refers to the U.S. National Archives and
Records Administration throughout the code, docs, and UI — only the
project / CLI / bundle identifiers changed.

### Notes

- Three env vars previously prefixed `NARA_*` for tool-internal use are
  now `ACTARI_*`: `ACTARI_HOME`, `ACTARI_DEFAULT_RATE`,
  `ACTARI_FORCE_KEYCHAIN`. Env vars that reference the agency's actual
  API (`NARA_API_KEY`, `NARA_API_BASE_URL`) are unchanged.
- `actari --version` flag added.
- New OSS-project files: `CODE_OF_CONDUCT.md`, `SECURITY.md`,
  `CITATION.cff`, GitHub issue + PR templates.

## [0.3.0] - 2026-05-16

### Added — web UI

- `nara init` interactive setup wizard with live NARA API key validation
  (rich.prompt; retry/save-anyway/abort branches).
- `nara serve` launches a local FastAPI web UI at `http://127.0.0.1:8765`.
- **Discovery tab**: debounced search, level/year/has-digital-objects
  filters, result cards with thumbnails, pagination, detail modal,
  Download button → job dialog.
- **Downloads tab**: polls `/api/jobs` every 2 s while visible, status
  badges, progress bars, expandable details, Cancel / Restart /
  Remove-from-history actions.
- **Library tab**: list of manifests, drill-down via URL hash
  (`#library/{name}`), per-manifest substring search, PDF preview in a
  side panel with Range streaming.
- **Settings tab**: masked API key status, editable default rate and
  auto-open-browser, "Open ~/.nara folder" button, NARA terms info.

### Added — backend

- `src/nara/config.py` — single source of truth. Resolution order: env >
  project `.env` > `~/.nara/config.toml`. Back-compat preserved.
- `src/nara/jobs.py` — JobManager with asyncio FIFO worker, persistence
  to `<output_dir>/jobs.json`, cooperative cancellation via
  `threading.Event`, startup recovery marks active jobs `interrupted`.
- Phase 2 (`download_all`) and Phase 3 (`build_pdfs`) accept
  `progress_callback` and `cancel_event` (CLI behaviour unchanged).
- New routes: `/api/search`, `/api/records/{naid}`,
  `/api/records/{naid}/children`, `/api/jobs[/restart]`, `/api/library`,
  `/api/library/{name}[/search]`, `/api/config`, `/api/config/reveal`,
  `/pdfs/*` (StaticFiles with Range + path-traversal protection).

### Added — release engineering

- MIT LICENSE, CHANGELOG, end-user-focused README, CONTRIBUTING.md.
- `docs/ARCHITECTURE.md` and `docs/screenshots/` scaffolding.
- GitHub Actions: `test.yml` matrix on Python 3.11/3.12/3.13 with ruff +
  pytest; `release.yml` tag-triggered build + PyPI trusted publishing.

### Changed

- `NaraClient` now reads its key and base URL from `resolve_config()`
  instead of calling `os.getenv` directly. Existing `NARA_API_KEY` env /
  `.env` workflows continue to work.
- Per-command `--output-dir` flags default to `None`; absent flag falls
  through to the config-resolved output dir (project-local `./output`
  if it exists, else `~/.nara/output`).

## [0.1.0] - 2026-05-15

### Added

- Three-phase pipeline (`metadata`, `download`, `build-pdfs`, `run`) for
  bulk-downloading every digital object under a NARA parent NAID and
  assembling one consolidated PDF per File Unit.
- `nara filter` subcommand for topic-scoped subsets, threaded through Phase 2
  / Phase 3 via `--metadata-file`.
- Defensive HTML-fallback detection so misrouted endpoints fail with a clear
  message instead of a cryptic JSON decode error.
- Rotating run log (10 MB / 5 backups) with global `--verbose` for DEBUG.
