# Architecture

## Module map

```
src/actari/
├── cli.py             # Typer CLI (metadata|filter|download|build-pdfs|run|stats|verify|init|presets|serve)
├── api.py             # NaraClient: requests + tenacity + TLS/HTML-fallback handling
├── config.py          # resolve_config(): env > .env > ~/.actari/config.toml
├── init_wizard.py     # interactive setup (rich.prompt)
├── metadata.py        # Phase 1 normalizer
├── downloader.py      # Phase 2; supports progress_callback + cancel_event
├── pdfbuild.py        # Phase 3; img2pdf + pypdf + magic-byte classification,
│                       #          optional recompression + OCR
├── filter.py          # regex-based subset selection
├── manifest.py        # final manifest writer + verifier
├── jobs.py            # JobManager: asyncio worker, persistence, cancellation
├── presets.py         # bundled + user-extensible starter searches
├── updater.py         # GitHub-release update check
├── utils.py           # OutputPaths, slugify, logging, safe_get, atomic writes
├── macapp/            # macOS menubar wrapper (rumps) — bundled in .app only
└── server/
    ├── app.py         # FastAPI factory + lifespan
    ├── models.py      # Pydantic DTOs
    ├── routes/        # search.py | jobs.py | library.py | config.py |
    │                  # firstrun.py | presets.py | updates.py
    └── static/        # SPA shell; one JS file per tab; no build step
```

## Request flow — full diagram

```
┌──────────────────────────────────────────────────────┐
│  Browser: http://localhost:8765                      │
│  ┌────────────┐ ┌──────────┐ ┌────────┐ ┌──────┐     │
│  │ Discovery  │ │Downloads │ │Library │ │ ⚙   │     │
│  └────────────┘ └──────────┘ └────────┘ └──────┘     │
│       index.html + four small vanilla-JS files       │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP/JSON; Downloads polls every 2 s
                        ▼
┌──────────────────────────────────────────────────────┐
│  FastAPI (src/actari/server/app.py)                  │
│   /api/search   /api/records/*   /api/jobs           │
│   /api/library  /api/config      /api/presets        │
│   /api/updates  /setup           /pdfs/*             │
└───────────┬───────────────────────────┬──────────────┘
            │                           │
            ▼                           ▼
┌────────────────────────┐   ┌────────────────────────┐
│  NaraClient (api.py)   │   │   JobManager (jobs.py) │
│  HTTPS → catalog.      │   │   asyncio FIFO worker  │
│  archives.gov          │   │   one job at a time    │
│  retries 5xx / network │   │   threading.Event for  │
│  rejects HTML 200 OK   │   │   cooperative cancel   │
└────────────────────────┘   └───────────┬────────────┘
                                          │
                ┌─────────────────────────┼─────────────────────┐
                ▼                         ▼                     ▼
   ┌──────────────────────┐  ┌──────────────────────┐  ┌────────────────┐
   │ metadata.py          │  │ downloader.py        │  │ pdfbuild.py    │
   │ Phase 1              │  │ Phase 2              │  │ Phase 3        │
   │ /records/parentNaId  │  │ s3.amazonaws.com/    │  │ img2pdf+pypdf  │
   │ → metadata.json      │  │ NARAprodstorage/...  │  │ → pdfs/{seq}-… │
   └──────────────────────┘  └──────────────────────┘  └────────────────┘
                                          │
                                          ▼
                            ┌────────────────────────┐
                            │   ~/.actari/output/    │
                            │   (or ./output/)       │
                            │  ├── metadata.json     │
                            │  ├── metadata-{name}…  │
                            │  ├── manifest.json     │
                            │  ├── manifest-{name}…  │
                            │  ├── jobs.json         │
                            │  ├── state.json        │
                            │  ├── raw/{naid}/…      │
                            │  └── pdfs/{seq}-…pdf   │
                            └────────────────────────┘
```

## State machines

### Job lifecycle

```
queued ─► fetching_metadata ─► downloading ─► building_pdfs ─► done
   │           │                   │                │
   │           └──► failed         └──► failed     └──► failed
   │
   └──► cancelled (DELETE while still queued)

  any active state ─► cancelled (DELETE during run; cancel_event polled
                                  between files / units)
  active-on-disk   ─► interrupted (server restart finds it mid-flight)
```

The active set `{fetching_metadata, downloading, building_pdfs}` is what the
manager rewrites to `interrupted` at startup. The terminal set
`{done, failed, cancelled, interrupted}` is the only set for which DELETE
purges history (otherwise DELETE cancels).

### Config resolution

```
env var (NARA_API_KEY)
    │
    └─► .env in CWD (loaded into env, never overrides existing values)
            │
            └─► ~/.actari/config.toml
                    │
                    └─► defaults baked into config.py
```

For `output_dir`:

```
--output-dir flag
    │
    └─► [api].output_dir from TOML
            │
            └─► ./output if it exists (back-compat for project-local installs)
                    │
                    └─► ~/.actari/output
```

## Operational notes

- **NARA's CloudFront serves the SPA index.html (5454 bytes, HTML) for any
  unknown API route.** Our `_get_json` detects HTML responses and raises
  `NaraUpstreamDown`. `get_record` swallows that as "not found" since the
  symptom is route-shaped, not outage-shaped.
- **PDFs are huge by default.** Source TIFFs and 6 MB JPGs flow through
  verbatim unless `--recompress` is passed to Phase 3. Expect ~1.5 TB for
  the 255k-object T83 microform Series at archival fidelity.
- **Progress events from worker threads** are marshalled back onto the
  asyncio loop via `loop.call_soon_threadsafe`. All `Job` mutations happen
  on the asyncio side; no locks.
- **State persistence is throttled.** Every 25 progress events, plus on
  every state transition. Writes use atomic temp+rename.
- **`/pdfs/*` is mounted via Starlette's `StaticFiles`** which natively
  supports HTTP `Range` (browser PDF viewers fetch pages on demand) and
  blocks `..` traversal via `os.path.commonpath`.

## Adding a new route

1. Define Pydantic DTOs in `src/actari/server/models.py`.
2. Write the handler in `src/actari/server/routes/{topic}.py`. If you need
   `NaraClient`, accept it via `Depends(get_nara_client)` so tests can
   swap a fake.
3. Register the router in `src/actari/server/app.py`.
4. Add a test in `tests/test_{topic}_routes.py` using `TestClient`. For
   routes that need the lifespan (job manager, etc.), use the
   `with TestClient(app) as c:` form.
