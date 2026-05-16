# nara archive

Bulk-download every digital object under a NARA Catalog parent NAID, assemble
one consolidated PDF per File Unit, and browse the result in a local web UI.

<!--
TODO before announce: replace this placeholder with an animated GIF showing
Discovery → Download → Library → PDF preview. docs/screenshots/ holds the
stills used for the README; the GIF stitches them.
-->

> [Screenshots placeholder — see `docs/screenshots/` once they're captured.]

## Quickstart

```bash
pipx install nara-archive
nara init       # interactive setup: paste an API key, accept the terms
nara serve      # opens http://127.0.0.1:8765 in your browser
```

That's the whole loop:

1. **Discovery** — search NARA's Catalog by query, level of description,
   year range, and "has digital objects".
2. **Download** — click *Download* on a result card; the next tab shows the
   job assembling metadata, fetching binaries, and building PDFs.
3. **Library** — open the resulting manifest and read the assembled PDFs in
   a side panel.

CLI commands are first-class too — `nara metadata`, `nara filter`,
`nara download`, `nara build-pdfs`, `nara run`, `nara stats`, `nara verify`.
`nara --help` lists them all.

## Getting a NARA API key

The key is free for research and educational use.

1. Visit <https://www.archives.gov/research/catalog/help/api>.
2. Email **Catalog_API@nara.gov** describing your project (one or two
   sentences is enough — name, affiliation, intended use).
3. They reply with a 40-character API key. Paste it into `nara init`.

## NARA terms of use

> This product uses the National Archives Catalog API but is not endorsed or
> certified by the National Archives and Records Administration.

NARA grants 10,000 API requests per key per month and asks consumers to keep
usage polite. For full-archive transfers (millions of files), they
explicitly recommend the [AWS Open Data mirror](https://registry.opendata.aws/nara/)
instead of the live API. This tool defaults to **0.5 seconds between
requests** and never parallelises downloads.

Phase 2 fetches binaries directly from `s3.amazonaws.com/NARAprodstorage/...`
URLs (referenced from the metadata response). Those object reads don't count
against the 10k API quota.

## What it doesn't do

This is a single-user research tool, not an archive-grade preservation
suite. Out of scope (intentionally):

- **No OCR / full-text search inside PDFs.** Titles and scope notes are
  searchable; PDF body content is not.
- **No image recompression.** Source TIFFs and 6 MB JPGs are passed
  through verbatim into the assembled PDF. Expect roughly 1.5 TB for a
  full 255k-object Series.
- **No multi-user accounts, no cloud sync, no telemetry.** The server
  binds to `127.0.0.1` by default; nothing leaves your machine.

## Output structure

Defaults to `~/.nara/output/` (overridable in `nara init`, or
`--output-dir` per command):

```
~/.nara/
├── config.toml          # API key + preferences (chmod 600 recommended)
├── jobs.json            # job-history snapshot (persisted across restarts)
└── output/
    ├── metadata.json
    ├── metadata-{name}.json     # one per `nara filter` subset
    ├── manifest.json            # consolidated catalog (search frontend input)
    ├── manifest-{name}.json     # per-subset manifest
    ├── state.json               # per-file download status
    ├── errors.log               # NAID + filename + reason on failure
    ├── run.log                  # rotating, 10 MB cap, 5 backups
    ├── raw/
    │   └── {naid}/              # downloaded binaries, one folder per File Unit
    └── pdfs/
        └── {seq:04d}-{naid}_{slug}.pdf
```

Back-compat: if a `./output` folder already exists in your current
directory, the CLI uses it instead of `~/.nara/output/`.

## CLI cheat sheet

```bash
nara metadata --parent-naid 7840517        # Phase 1: fetch + normalize metadata
nara filter --query "I\.?G\.?\s*Farben" --name igfarben
nara download --metadata-file output/metadata-igfarben.json --rate 0.5
nara build-pdfs --metadata-file output/metadata-igfarben.json
nara stats                                  # counts + error summary
nara verify                                 # check manifest entries vs. disk
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for module overview and
sequence diagrams.

## License

[MIT](LICENSE) — © 2026 Christopher Ramm.

## Contributing

Issues and PRs welcome at <https://github.com/rammc/nara-archive/issues>.
See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, tests, and PR
checklist.
