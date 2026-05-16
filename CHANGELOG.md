# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `nara init` interactive setup wizard with live NARA API key validation.
- `nara serve` launches a local FastAPI web UI at `http://127.0.0.1:8765` with
  Discovery / Downloads / Library / Settings tabs (skeleton; per-tab logic
  lands in follow-up patches).
- `src/nara/config.py` — single source of truth for runtime config. Resolution
  order: env > `.env` > `~/.nara/config.toml`. Back-compat preserved.
- MIT LICENSE, CHANGELOG, and PyPI-ready `pyproject.toml` metadata.

### Changed

- `NaraClient` now reads its key and base URL from `resolve_config()` instead
  of calling `os.getenv` directly. Existing `NARA_API_KEY` env / `.env`
  workflows continue to work.
- Per-command `--output-dir` flags default to ``None``; absent flag falls
  through to the config-resolved output dir (project-local `./output` if it
  exists, else `~/.nara/output`).

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
