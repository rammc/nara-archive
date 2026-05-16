# Contributing to nara-archive

Thanks for considering a contribution! This is a small project and we'd like
to keep it that way — fewer features, sharper edges.

## Dev setup

```bash
git clone https://github.com/rammc/nara-archive.git
cd nara-archive
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

- `test_config_resolution.py` — env / .env / TOML precedence.
- `test_api_parsing.py` — defensive normalisation of NARA responses.
- `test_filter.py` — pure regex filter logic.
- `test_pdfbuild.py` — image classification + PDF assembly with three JPGs.
- `test_server_routes.py` — `/api/search`, `/api/records/*` with a stubbed
  `NaraClient` via FastAPI `Depends`.
- `test_jobs_routes.py` — full HTTP lifecycle through the lifespan.
- `test_job_manager.py` — JobManager state machine, cancellation,
  persistence, startup recovery.
- `test_library_routes.py` — manifest listing, detail, in-doc search.
- `test_pdf_serving_security.py` — path-traversal blocked, Range works.
- `test_config_routes.py` — masked key, PATCH persists to TOML.
- `test_init_wizard.py` — wizard happy path + retry/abort branches.
- `test_smoke_ui.py` — SPA shell + /api/health.

## Lint and format

```bash
ruff check .
ruff format --check .   # CI uses this; `ruff format .` to auto-fix
```

## PR checklist

Before opening a PR:

- [ ] `pytest` passes locally
- [ ] `ruff check .` passes
- [ ] `ruff format --check .` passes
- [ ] CHANGELOG.md updated under `[Unreleased]` (if user-visible)
- [ ] New behaviour has at least one test

Keep PRs small and focused. If a change spans config + routes + frontend,
that's three commits, ideally three PRs. Easier to review, easier to revert.

## Architecture quick reference

```
src/nara/
├── cli.py             # Typer CLI surface
├── api.py             # NaraClient + retry / TLS-fallback handling
├── config.py          # env > .env > ~/.nara/config.toml; single source of truth
├── init_wizard.py     # `nara init` interactive flow
├── metadata.py        # Phase 1 normaliser
├── downloader.py      # Phase 2 (now with progress_callback + cancel_event)
├── pdfbuild.py        # Phase 3 (img2pdf + pypdf, magic-byte classification)
├── filter.py          # subset selection by regex
├── manifest.py        # final manifest writer + verifier
├── jobs.py            # JobManager: asyncio worker, persistence, cancellation
├── utils.py           # OutputPaths, logging, slugify, safe_get, atomic writes
└── server/
    ├── app.py         # FastAPI factory + lifespan
    ├── models.py      # Pydantic DTOs
    ├── routes/        # search / jobs / library / config
    └── static/        # SPA shell, one JS file per tab
```

`docs/ARCHITECTURE.md` has more detail and a sequence diagram.

## Reporting bugs

A useful bug report includes:

- Python version (`python --version`)
- nara-archive version (`nara --help` shows it in the footer, or check
  `pyproject.toml`)
- The command you ran and its full output, including the stack trace
- `output/run.log` tail (last 50 lines) if it's a runtime issue
- `output/errors.log` if it's a download or build failure

## Code of conduct

Be kind. Disagreements happen; we resolve them in code review with concrete
suggestions. Personal attacks of any kind aren't welcome.
