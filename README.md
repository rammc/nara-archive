# nara-archive

Bulk-downloads every digital object under a NARA (US National Archives) parent
NAID via the Catalog API v2 and assembles one consolidated PDF per child File
Unit. Output is a self-describing `manifest.json` ready to be fed into a static
search frontend.

## Setup

Requires Python 3.11+.

```bash
# with uv
uv sync

# or with pip
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and add your NARA API key:

```bash
cp .env.example .env
# edit .env and set NARA_API_KEY=<your key>
```

Request a key at <https://www.archives.gov/research/catalog/help/api>.

## Quickstart

Run all three phases for the default parent NAID (`7840517`):

```bash
nara run --parent-naid 7840517
```

Or step by step:

```bash
nara metadata --parent-naid 7840517   # Phase 1: fetch + normalize metadata
nara download                          # Phase 2: pull every digital object
nara build-pdfs                        # Phase 3: one PDF per File Unit
```

Diagnostics:

```bash
nara stats     # counts, sizes, error summary
nara verify    # check manifest entries exist on disk
```

## Output structure

All artifacts land in `./output/` (override with `--output-dir`):

```
output/
├── metadata-raw.json     # raw API response, audit trail
├── metadata.json         # normalized File Unit metadata
├── manifest.json         # final consolidated catalog (search frontend input)
├── state.json            # per-file download state
├── errors.log            # download / build failures (NAID + filename + reason)
├── run.log               # DEBUG log for the run
├── raw/
│   └── {naid}/           # downloaded binaries, one folder per File Unit
└── pdfs/
    └── {seq:04d}-{naid}_{slug}.pdf
```

## Filtering subsets

Long collections are easier to work with one topic at a time. `nara filter`
takes the full `metadata.json` and emits a topic-scoped subset that the other
phases can be pointed at.

```bash
# Build an I.G. Farben subset from the full metadata
nara filter --query "I\.?G\.?\s*Farben" --name igfarben

# Run download + PDF build against just that subset
nara download --metadata-file output/metadata-igfarben.json
nara build-pdfs --metadata-file output/metadata-igfarben.json
```

- `--query` is a Python regex matched case-insensitively against the
  configured fields (default: `title` and `scope_and_content_note`).
- `--name` becomes the suffix of the output file (`metadata-{name}.json`) and
  of the manifest written by `build-pdfs` (`manifest-{name}.json`). Names must
  match `[A-Za-z0-9][A-Za-z0-9_-]*` — no path separators, no spaces.
- The filtered file gets an extra `filter` block recording the query, matched
  field list, source file, match count and timestamp; everything else stays
  byte-identical to the source schema so downstream tools don't need to care.
- Phase 2 and Phase 3 share `output/raw/` and `output/pdfs/` across filters —
  a file unit downloaded by one filter is reused by any other filter that
  references it. Sequence numbering (`{seq:04d}`) is per-subset, so a filtered
  run produces `0001-...pdf` through `{N:04d}-...pdf`.
- Zero matches exit with status 2 and no output file is written.

## Resume / re-run semantics

- **Phase 1 (`metadata`)** always re-fetches and overwrites `metadata.json` /
  `metadata-raw.json`. Cheap, single API call.
- **Phase 2 (`download`)** is resume-safe by default. A local file is skipped
  when it exists and its size matches `objectFileSize`. Pass `--resume` for
  explicitness; the default behaviour is the same. `state.json` is written
  atomically per file. Pass `--metadata-file output/metadata-{name}.json` to
  download only a filtered subset.
- **Phase 3 (`build-pdfs`)** skips File Units whose output PDF already exists
  and is non-empty. Use `--force` to rebuild. Pass `--metadata-file` to build
  PDFs for a subset; the manifest is written next to the input metadata file
  (e.g. `manifest-{name}.json`).
- **`output/run.log`** is rotated at 10 MB with 5 backups (`run.log.1` …
  `run.log.5`). DEBUG-level events are written only when `--verbose` is
  passed; otherwise the file stays at INFO.

Errors in either phase are isolated to the affected File Unit and logged to
`output/errors.log`. The pipeline never aborts on a single failure.

## Rate limits and politeness

The NARA Catalog API allows up to 10,000 requests per key per month. Their
terms of use discourage aggressive scraping, so this tool defaults to **1
request per second** for both metadata calls and binary downloads. Override
with `--rate` (seconds between requests, e.g. `--rate 0.5`).

See <https://www.archives.gov/research/catalog/help/api> for full terms.

## Attribution

> This product uses the National Archives Catalog API but is not endorsed or
> certified by the National Archives and Records Administration.

## Development

```bash
pytest        # run unit tests (no network calls)
ruff check .  # lint
```

Tests use only local fixtures under `tests/fixtures/` and complete in well
under two seconds.
