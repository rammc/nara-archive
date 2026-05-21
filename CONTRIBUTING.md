# Contributing to actari

Thanks for considering a contribution! `actari` is a small, focused project
and we'd like to keep it that way — fewer features, sharper edges. If you're
about to spend more than an afternoon on something, please open an issue
first so we can talk through the approach. First-time contributors very
welcome.

## Dev setup

```bash
git clone https://github.com/rammc/actari.git
cd actari
python3.11 -m venv .venv  # or 3.12 / 3.13
source .venv/bin/activate
pip install -e ".[dev]"
```

That installs FastAPI, uvicorn, requests, img2pdf, pypdf, Pillow, tenacity,
typer, rich, slugify, dotenv, plus pytest and ruff.

A NARA API key isn't required to run the tests — they monkey-patch the
network and the wizard's validator. You only need a key for live smoke
testing.

## Run the test suite

```bash
pytest                                # all tests, ~30s
pytest -k jobs                        # one file's worth
pytest tests/test_pdf_serving_security.py -v
```

Tests live in `tests/` and follow a one-file-per-module convention:

- `test_config_resolution.py` — env / .env / TOML precedence + Keychain shim.
- `test_api_parsing.py` — defensive normalisation of NARA responses.
- `test_filter.py` — pure regex filter logic.
- `test_pdfbuild.py` — image classification + PDF assembly + recompression + OCR.
- `test_server_routes.py` — `/api/search`, `/api/records/*` with a stubbed
  `NaraClient` via FastAPI `Depends`.
- `test_jobs_routes.py` — full HTTP lifecycle through the lifespan.
- `test_job_manager.py` — JobManager state machine, cancellation,
  persistence, startup recovery.
- `test_library_routes.py` — manifest listing, detail, in-doc search.
- `test_firstrun_routes.py` — first-run wizard + setup → main redirect.
- `test_pdf_serving_security.py` — path-traversal blocked, Range works.
- `test_config_routes.py` — masked key, PATCH persists to TOML, reset-key.
- `test_init_wizard.py` — CLI wizard happy path + retry/abort branches.
- `test_presets.py` — bundled + user-extensible preset loading.
- `test_updater.py` — GitHub-release update checker.
- `test_smoke_ui.py` — SPA shell + `/api/health`.

## Lint and format

```bash
ruff check .
ruff format --check .   # CI uses this; `ruff format .` to auto-fix
```

## Commit message style

Conventional Commits, lightly enforced:

- Subject line under 60 characters, lowercase, imperative mood:
  `feat(cli): add --version flag` — not `Added a version flag.`
- Body (optional) explains **why**, not what — the diff already shows what.
- Common prefixes: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`,
  `build`. Scope in parens (`feat(ui): …`) is encouraged but optional.

## PR process

Before opening a PR:

- [ ] `pytest` passes locally
- [ ] `ruff check .` passes
- [ ] `ruff format --check .` passes
- [ ] `CHANGELOG.md` updated under `[Unreleased]` (if user-visible)
- [ ] New behaviour has at least one test

Keep PRs small and focused. If a change spans config + routes + frontend,
that's three commits, ideally three PRs. Easier to review, easier to revert.

If you're unsure whether a change is wanted, **open an issue first**.
Better a 5-minute conversation than a 5-hour PR pointing in the wrong
direction.

## Architecture quick reference

```
src/actari/
├── cli.py             # Typer CLI surface
├── api.py             # NaraClient + retry / TLS-fallback handling
├── config.py          # env > Keychain > ~/.actari/config.toml; single source of truth
├── init_wizard.py     # `actari init` interactive flow
├── metadata.py        # Phase 1 normaliser
├── downloader.py      # Phase 2 (with progress_callback + cancel_event)
├── pdfbuild.py        # Phase 3 (img2pdf + pypdf, magic-byte classification,
│                       #          optional recompression + OCR)
├── filter.py          # subset selection by regex
├── manifest.py        # final manifest writer + verifier
├── jobs.py            # JobManager: asyncio worker, persistence, cancellation
├── presets.py         # bundled + user-extensible starter searches
├── updater.py         # GitHub-release update check
├── utils.py           # OutputPaths, logging, slugify, safe_get, atomic writes
├── macapp/            # macOS menubar wrapper (rumps) — bundled in .app only
└── server/
    ├── app.py         # FastAPI factory + lifespan
    ├── models.py      # Pydantic DTOs
    ├── routes/        # search / jobs / library / config / firstrun / presets / updates
    └── static/        # SPA shell, one JS file per tab
```

`docs/ARCHITECTURE.md` has more detail and a sequence diagram.

## Reporting bugs

A useful bug report includes:

- Operating system + version (e.g. macOS 14.4, Ubuntu 22.04)
- Python version (`python --version`)
- actari version (`actari --version` or check `pyproject.toml`)
- The command you ran and its full output, including the stack trace
- `output/run.log` tail (last 50 lines) if it's a runtime issue
- `output/errors.log` if it's a download or build failure

The bug-report template under `.github/ISSUE_TEMPLATE/` collects all of
this automatically.

## Code of conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md).
In short: be kind. Disagreements happen; we resolve them in code review
with concrete suggestions. Personal attacks of any kind aren't welcome.
