# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
