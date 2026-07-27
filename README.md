# actari — your local research companion for the U.S. National Archives Catalog

[![CI](https://github.com/rammc/actari/actions/workflows/test.yml/badge.svg)](https://github.com/rammc/actari/actions/workflows/test.yml)
[![macOS DMG](https://img.shields.io/github/v/release/rammc/actari?include_prereleases&label=mac%20DMG&color=d97706)](https://github.com/rammc/actari/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

> **Disclaimer:** **actari** is not affiliated with or endorsed by the
> U.S. National Archives and Records Administration (NARA). It uses
> NARA's public Catalog API under their published terms of use.

<!--
PyPI badges are intentionally absent until `actari` is published
on PyPI. Once the first PyPI release ships, add:
  [![PyPI](https://img.shields.io/pypi/v/actari.svg)](https://pypi.org/project/actari/)
  [![Python](https://img.shields.io/pypi/pyversions/actari.svg)](https://pypi.org/project/actari/)
-->

Bulk-download every digital object under a [NARA Catalog](https://catalog.archives.gov/)
parent NAID, assemble one consolidated PDF per File Unit, and browse the
result in a local web UI.

## Quickstart

```bash
# macOS — drag-and-drop, no terminal
#   Open the releases page, download the .dmg, drag the app to
#   Applications, double-click. Signed + notarized — no Gatekeeper warning.
open https://github.com/rammc/actari/releases/latest

# Cross-platform — Python CLI (Linux, Windows, Intel Macs)
pipx install actari
actari init      # paste your free NARA API key
actari serve     # opens the web UI at http://127.0.0.1:8765
```

[Full installation guide →](#installation) · [Get a free NARA API key →](#getting-a-nara-api-key)

> **Screenshots** land with v1.0.x. Until then, `actari serve` gives you
> the same UI as a live preview. Placeholders live under
> [`docs/screenshots/`](docs/screenshots/).

<!--
TODO before announce: replace the screenshots placeholder above with an
animated GIF showing Discovery → Download → Library → PDF preview.
docs/screenshots/ holds the stills used for the README.
-->

## Why

NARA's Catalog API is excellent but low-level: paginated JSON, no batch
downloads, no PDF assembly, no local index. Historians, genealogists, and
researchers end up writing throwaway scripts. `actari` replaces those
scripts with a small, well-tested pipeline plus an optional local UI — so
you can spend time reading the records, not glueing JSON together.

## Features

- **Three-phase pipeline** — metadata fetch → bulk download → PDF assembly,
  with state tracking, resumable runs, and atomic writes.
- **Local web UI** (`actari serve`) — Discovery (live search with downloadability
  badges and Record Group filter), Downloads (one-click job creation, live
  progress, cancel/restart, inline PDF list, "Open output folder"), Library
  (manifests with in-browser PDF preview), Settings (masked key, editable rate).
- **Curated starter searches** (`actari presets`) — 8 hand-picked entry points
  for IG Farben / WWII industrial / Nuremberg-trials research, plus your own
  via [`~/.actari/presets.json`](#custom-presets).
- **Optional image recompression** ([`--recompress`](#recompression)) —
  shrinks output PDFs 5–10× while keeping typewritten text readable.
- **Optional OCR text layer** ([`--ocr`](#ocr)) — searchable PDFs via
  ocrmypdf + Tesseract; defaults to English + German for the captured-records
  corpus.
- **Leaf-record fallback** — if you select a single-record NAID with its own
  digital objects, the pipeline treats it as a one-file-unit job rather than
  failing silently.
- **Regex-based topic filter** (`actari filter`) — carve a subset out of a
  giant Series and download only that.
- **Cooperative cancellation, resumable downloads, rotating logs.**
- **Two distribution paths** — a signed + notarized [macOS .app](#option-a--macos-app-no-terminal-needed)
  for users who never want to see a terminal, plus a
  [pipx CLI](#option-b--python-cli-via-pipx-cross-platform) for Linux,
  Windows, Intel Macs, and anyone who prefers `actari serve` from a shell.
- **Background update check** — on `actari serve` startup, a single
  anonymous request to GitHub Releases surfaces a banner in Settings when a
  newer version is out; disable via `[updates] check_on_startup = false` in
  `~/.actari/config.toml`.
- **Zero telemetry, no cloud sync.** Server binds to `127.0.0.1` by default.

## Installation

Two paths — pick whichever fits.

- **Option A — [macOS app via DMG](#option-a--macos-app-no-terminal-needed)**: drag-and-drop
  install, no terminal, Apple Silicon (M1/M2/M3/M4) Macs only. Easiest for
  non-technical users.
- **Option B — [Python CLI via pipx](#option-b--python-cli-via-pipx-cross-platform)**:
  works on macOS (Intel + Apple Silicon), Linux, and Windows. Same web UI,
  same features, you just start it from a terminal once.

Both options give you the same `http://127.0.0.1:8765` web UI and the
same on-disk layout under `~/.actari/`. You can swap between them later
without losing any data.

### Option A — macOS app (no terminal needed)

1. **Download the latest DMG** from the project's
   [releases page](https://github.com/rammc/actari/releases/latest).
   The file is called `actari-x.y.z.dmg` (≈ 35 MB).
2. **Open the DMG.** A small Finder window appears with the **actari**
   app icon next to an **Applications** shortcut.
3. **Drag the app onto the Applications shortcut.** macOS copies the
   bundle into `/Applications`. On first install this can take up to
   **2 minutes** while Gatekeeper re-validates every file in the bundle —
   the progress bar may say "Copying 0 items" near the end; that's normal,
   wait it out.
4. **Eject the DMG** (right-click → Eject in the Finder sidebar).
5. **Launch the app** from `/Applications/actari`. The label **"NARA"**
   appears in the menu bar (top-right of the screen), and your
   default browser opens to `http://127.0.0.1:8765`.
6. **First-run setup runs in the browser** — paste your NARA API key
   ([how to request one](#getting-a-nara-api-key)), confirm the output
   directory, tick the NARA-terms acknowledgment, click *Get started*.

To **quit**, click the menu-bar **"NARA"** label → **Quit**. The local server
shuts down cleanly. Launch again any time from `/Applications`.

**Requirements:**
- macOS 11 (Big Sur) or newer
- **Apple Silicon (M1/M2/M3/M4)** — Intel Macs aren't supported yet by
  the DMG. Intel users go to [Option B](#option-b--python-cli-via-pipx-cross-platform).
- The app is signed by Apple Developer ID and notarized, so you won't
  see any *"developer cannot be verified"* dialog.

### Option B — Python CLI via pipx (cross-platform)

> **Already comfortable with the terminal and pipx?**
> `pipx install actari` and skip to [First steps](#first-steps).

This section walks through installation from scratch. It assumes you have
**no prior programming experience**. Everything below is copy-paste — you
do not need to memorise any of it.

#### What you'll be doing

In plain language: you'll open a small "command window" and run **six
short commands** that download and set up the program. Each command takes
a few seconds. After that, the tool runs in your regular web browser like
any other website.

#### What you need

- A computer running **macOS**, **Windows**, or **Linux**.
- About **15 minutes** for first-time setup (5 minutes if Python is
  already installed).
- **5 GB+ of free disk space** for downloaded archives. Plan for much
  more if you intend to bulk-download a long microform Series — those
  can be hundreds of gigabytes.
- A free **NARA API key** ([how to request one](#getting-a-nara-api-key)).
  You can start the installation now and request the key while you wait
  for NARA's reply.

You do **not** need to be a programmer. You can't break your computer by
mistyping a command in the terminal — at worst you'll see a polite error
message and try again.

#### A note about copy-pasting commands

When you copy a command from this README, copy only the command itself
(e.g. `python3 --version`) — never the `$` or `>` symbols that some
tutorials show at the start of a line. Click inside the command block,
select the text with your mouse, and use <kbd>⌘</kbd>+<kbd>C</kbd> (macOS)
or <kbd>Ctrl</kbd>+<kbd>C</kbd> (Windows/Linux) to copy. In the terminal,
paste with **<kbd>⌘</kbd>+<kbd>V</kbd>** on macOS or
**<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>V</kbd>** on Windows/Linux —
note the extra <kbd>Shift</kbd> on non-Mac systems.

After pasting, press <kbd>Enter</kbd> (also called <kbd>Return</kbd>) to
run the command. The terminal will print some text in response. When it's
done, you'll see a fresh blank line waiting for the next command.

#### Step 1 — Open the terminal

The "terminal" is a window where you type commands instead of clicking
buttons. It looks intimidating but it's just a text-only window. You'll
see your username, a prompt symbol (often `$` or `>`), and a blinking
cursor waiting for input.

**macOS:**
1. Press <kbd>⌘</kbd>+<kbd>Space</kbd> to open Spotlight search.
2. Type `Terminal`.
3. Press <kbd>Enter</kbd>. A small white-on-black (or black-on-white)
   window opens — that's your terminal.

**Windows 11:**
1. Press the <kbd>Windows</kbd> key.
2. Type `Terminal`.
3. Press <kbd>Enter</kbd>. A dark window with a tab bar opens — that's
   **Windows Terminal**.

**Windows 10:**
1. Press the <kbd>Windows</kbd> key.
2. Type `Command Prompt` (or `PowerShell`).
3. Press <kbd>Enter</kbd>.

**Linux:**
- Most desktops: press <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>T</kbd>.
- Or open the application menu and search for "Terminal" /
  "Konsole" / "GNOME Terminal".

Keep this window open for the rest of the installation. You'll alternate
between reading this README in your browser and typing commands here.

#### Step 2 — Check whether Python is already installed

`actari` is written in Python. Many computers (especially Macs and
Linux machines) already have it. Let's check.

In the terminal, type the command below and press <kbd>Enter</kbd>:

```bash
python3 --version
```

**What success looks like** — one line of output, something like:

```
Python 3.12.4
```

If the number after `Python ` is **3.11.0 or higher**, you're set — skip
to [Step 4](#step-4--install-pipx).

**If you see an error** like `command not found` or `Python was not
found`, or a version **below 3.11**, continue with Step 3.

#### Step 3 — Install Python (only if Step 2 failed)

**macOS:**
- Easiest: install [Homebrew](https://brew.sh) (paste the one-line
  command from their homepage), then run `brew install python@3.12` in
  your terminal.
- Or: download the installer from <https://www.python.org/downloads/>,
  open it, and click through with the defaults.

**Windows:**
1. Open the **Microsoft Store** app.
2. Search for `Python 3.12` and install it.
3. Or: download from <https://www.python.org/downloads/>. **During the
   installer, tick the box that says "Add Python to PATH"** before
   clicking Install. This is the single most common cause of "command not
   found" errors later — please don't skip it.

**Linux (Debian/Ubuntu):**

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

(You'll be prompted for your password — that's normal; the password
won't show as you type it.)

After installing, **close the terminal and open a new one**, then re-run
the check from Step 2 to confirm.

#### Step 4 — Install `pipx`

`pipx` is a small helper that installs Python applications cleanly,
keeping each one in its own little sandbox so they don't conflict with
each other or with your system. It's the recommended way to install
tools like `actari`.

Pick the line that matches your system and paste it into the terminal:

```bash
# macOS (using Homebrew)
brew install pipx

# Windows (in Windows Terminal, Command Prompt, or PowerShell)
python -m pip install --user pipx

# Linux (Debian/Ubuntu)
sudo apt install pipx
```

Then, no matter which system, run this **once**:

```bash
pipx ensurepath
```

This tells your terminal where to find programs that pipx installs.

**Important:** After running `pipx ensurepath`, **close the terminal
window and open a new one**. The change only takes effect in newly
opened terminals. If you skip this, the next command will fail with
"command not found".

The official pipx guide is at <https://pipx.pypa.io/stable/installation/>
if you want more detail.

#### Step 5 — Install actari

In your fresh terminal window, type:

```bash
pipx install actari
```

You'll see several lines of output as pipx downloads the package and
its dependencies. This takes 30–90 seconds depending on your internet
connection. **What success looks like** — the last line will be
something like:

```
  installed package actari 1.0.0, installed using Python 3.12.4
  These apps are now globally available
    - actari
done! ✨ 🌟 ✨
```

Verify it worked:

```bash
actari --help
```

You should see a list of available commands (`init`, `serve`, `presets`,
`metadata`, `download`, `build-pdfs`, …). If you instead see "command
not found", you almost certainly forgot to close and reopen the terminal
after `pipx ensurepath` — do that now and try again.

#### Step 6 — First-run setup

```bash
actari init
```

This launches a friendly interactive wizard that:
1. **Asks for your NARA API key** — paste it when prompted (the 40-character
   string NARA emailed you).
2. **Validates the key** by making one test request to the Catalog API.
3. **Saves it** to `~/.actari/config.toml` along with sensible defaults.
4. **Asks you to accept** NARA's terms of use (one sentence, see below).

If you don't have a key yet, see [Getting a NARA API key](#getting-a-nara-api-key)
below. You can re-run `actari init` later once the key arrives.

#### Step 7 — Launch the web UI

```bash
actari serve
```

Within a second or two, your default browser opens at
<http://127.0.0.1:8765>. This is `actari` running locally on your
own machine — the page is not on the internet, only you can see it.

From here on, you live in the browser:
- The **Discovery** tab is for searching NARA.
- The **Downloads** tab shows your bulk-download jobs.
- The **Library** tab is where finished PDFs appear, with a built-in
  reader.
- The **⚙ Settings** tab lets you edit your rate limit and reveal the
  output folder.

To **stop the server**, switch back to the terminal window and press
<kbd>Ctrl</kbd>+<kbd>C</kbd>. You can launch it again any time with
`actari serve`.

#### If something doesn't work

| You see… | What to do |
| --- | --- |
| `command not found: actari` | Close the terminal, open a new one, and try again. If still failing, re-run `pipx ensurepath` then close & reopen the terminal. |
| `command not found: python3` (after installing Python on Windows) | The "Add Python to PATH" checkbox was missed during install. Re-run the Python installer, untick everything except that checkbox, and click "Modify". |
| The browser doesn't open after `actari serve` | The server is still running — just open <http://127.0.0.1:8765> manually in any browser. |
| `pipx: command not found` | pipx was installed but `pipx ensurepath` wasn't run, or the terminal wasn't reopened. Do both. |
| `command not found: brew` on macOS, even though Homebrew installed cleanly | Apple-Silicon Macs (M1/M2/M3/M4) put brew at `/opt/homebrew/`, which isn't on the default `PATH`. The Homebrew installer prints a "Next steps" block at the end with the exact lines — if you missed it, run: <br>`echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile` <br>`eval "$(/opt/homebrew/bin/brew shellenv)"` <br>then close & reopen the terminal. `brew --version` should now print a version number. |
| `actari init` says my key is invalid | Double-check there are no extra spaces around the key. If NARA emailed it within quotes, copy only the characters inside the quotes. |
| Anything else | Copy the exact error message and [open an issue](https://github.com/rammc/actari/issues). Include your operating system. |

#### Updating to a newer version

```bash
pipx upgrade actari
```

For the macOS app (Option A): download the newer DMG from the
[releases page](https://github.com/rammc/actari/releases/latest)
and drag the new app onto Applications — overwrites the old install.
Your config under `~/.actari/` is preserved.

#### Uninstalling

```bash
# Option B (pipx):
pipx uninstall actari

# Option A (macOS app):
# Drag /Applications/actari to the Trash.
```

Your downloaded PDFs and configuration live under `~/.actari/`. Delete that
folder too if you want to remove everything, including your API key.

## First steps

Once installed and configured:

1. **Discovery** — search NARA's Catalog by query, level of description,
   year range, Record Group, or "has digital objects". Badges hint at
   downloadability before you click. The "Starter searches" panel offers
   one-click entry points for IG-Farben / WWII research.
2. **Download** — click *Download* on a result card; the next tab shows
   the job assembling metadata, fetching binaries, and building PDFs.
3. **Library** — open the resulting manifest and read the assembled PDFs
   in a side panel.

CLI commands are first-class too — `actari metadata`, `actari filter`,
`actari download`, `actari build-pdfs`, `actari run`, `actari stats`, `actari verify`,
`actari presets`. `actari --help` lists them all.

## Getting a NARA API key

The key is free for research and educational use.

1. Visit <https://www.archives.gov/research/catalog/help/api>.
2. Email **Catalog_API@nara.gov** describing your project (one or two
   sentences is enough — name, affiliation, intended use).
3. They reply with a 40-character API key. Paste it into `actari init`.

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

- **No full-text search across your local library.** Per-manifest title
  and scope-note search exists; cross-manifest search and full-text
  search across OCR'd body content are not built in. (Drop the resulting
  PDFs into Spotlight, recoll, or Zotero if you want that.)
- **Source images are passed through verbatim by default.** TIFFs and
  6 MB reference JPEGs land in the output PDF as-is unless you turn on
  `--recompress` ([see Recompression](#recompression)). The default
  preserves archival fidelity; expect roughly 1.5 TB for a full
  255k-object Series.
- **No multi-user accounts, no cloud sync, no telemetry.** The server
  binds to `127.0.0.1` by default; nothing leaves your machine.

## Output structure

Defaults to `~/.actari/output/` (overridable in `actari init`, or
`--output-dir` per command):

```
~/.actari/
├── config.toml          # API key + preferences (chmod 600 recommended)
└── output/
    ├── metadata.json
    ├── metadata-{name}.json     # one per `actari filter` subset
    ├── manifest.json            # consolidated catalog (search frontend input)
    ├── manifest-{name}.json     # per-subset manifest
    ├── state.json               # per-file download status
    ├── jobs.json                # job-history snapshot (persisted across restarts)
    ├── errors.log               # NAID + filename + reason on failure
    ├── run.log                  # rotating, 10 MB cap, 5 backups
    ├── raw/
    │   └── {naid}/              # downloaded binaries, one folder per File Unit
    └── pdfs/
        └── {seq:04d}-{naid}_{slug}.pdf
```

Back-compat: if a `./output` folder already exists in your current
directory, the CLI uses it instead of `~/.actari/output/`.

## CLI cheat sheet

```bash
# Discovery + presets
actari presets                                  # curated starter searches
actari presets --path                           # print ~/.actari/presets.json location
actari presets --bundled-only                   # ignore your custom presets file

# Three-phase pipeline
actari metadata --parent-naid 7840517           # Phase 1: fetch + normalize metadata
actari filter --query "I\.?G\.?\s*Farben" --name igfarben
actari download --metadata-file output/metadata-igfarben.json --rate 0.5
actari build-pdfs --metadata-file output/metadata-igfarben.json

# Build with size reduction and/or OCR
actari build-pdfs --recompress --force          # 5–10× smaller PDFs
actari build-pdfs --ocr --ocr-language eng+deu  # searchable text layer
actari build-pdfs --recompress --ocr --force    # both — recommended combo

# End-to-end shortcut
actari run --parent-naid 7840517 --recompress --ocr

# Maintenance
actari stats                                    # counts + error summary
actari verify                                   # check manifest entries vs. disk
actari serve                                    # local web UI
actari --version                                # print the installed version
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for module overview and
sequence diagrams.

## Development

```bash
git clone https://github.com/rammc/actari
cd actari
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                # 100+ unit/integration tests
ruff check . && ruff format --check .
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full development workflow.

## Roadmap

- ~~Image recompression option.~~ ✓ Shipped — see [Recompression](#recompression).
- ~~OCR pass with `ocrmypdf`.~~ ✓ Shipped — see [OCR](#ocr).
- ~~User-extensible presets via `~/.actari/presets.json`.~~ ✓ Shipped — see
  [Custom presets](#custom-presets).
- ~~Signed macOS `.app` distributed via `.dmg`.~~ ✓ Shipped — see
  [Option A](#option-a--macos-app-no-terminal-needed) and
  [`docs/RELEASE.md`](docs/RELEASE.md). Currently
  **Apple Silicon only**; Intel-Mac build via a parallel `macos-13`
  + `lipo`-merge job is the next macOS-side item.
- **Publish to PyPI** so `pipx install actari` works without a
  source clone. Trusted-publishing workflow lives at
  `.github/workflows/release.yml`; first publish is a manual gating
  step before adding the PyPI badge back to the README.
- Optional sibling tool against the AWS Open Data S3 mirror for
  full-archive workloads.

Issues and feature requests welcome at
<https://github.com/rammc/actari/issues>.

## Recompression

NARA serves reference scans at archival fidelity — 6 MB JPEGs and 50 MB
TIFFs per page are common, so a single File Unit can produce a 400 MB+
PDF. Opt-in **recompression** re-encodes source images during Phase 3 to
get research-readable output at a fraction of the size.

What it does:
- Re-encodes JPEGs (and converts TIFFs) at **JPEG quality 82**, downsized
  to **max 2400 px**. Typical reduction: 5–10× for typewritten material.
- Skips images already smaller than 200 KB — no point re-encoding.
- Original sources on disk under `raw/` are **never touched**; only the
  intermediate copies fed to img2pdf are recompressed. You can rebuild
  at archival quality any time by re-running without `--recompress`.

How to use it:

```bash
# CLI
actari build-pdfs --recompress --force        # --force needed to rebuild existing
actari run --recompress --parent-naid 12345

# Web UI: Discovery → Download → tick "Recompress images during PDF assembly"
```

When to skip it: if you need bit-perfect reproductions for citation or
publication, leave it off — the default passes scans through verbatim.

## OCR

NARA serves image-only PDFs and JPEGs — you can read them but you can't
search the text inside. Opt-in **OCR** adds a searchable text layer to
each assembled PDF via [ocrmypdf](https://github.com/ocrmypdf/OCRmyPDF)
+ [Tesseract](https://github.com/tesseract-ocr/tesseract).

### One-time setup

OCR is an optional extra because it pulls in heavy external dependencies.
Install both the Python package and the system Tesseract binary:

```bash
# 1. Add ocrmypdf to your pipx-installed actari
pipx inject actari ocrmypdf

# 2. Install Tesseract + the language packs you want
# macOS:
brew install tesseract tesseract-lang   # tesseract-lang ships eng+deu+more
# Debian / Ubuntu:
sudo apt install tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng
# Windows:
# Download the installer from https://github.com/UB-Mannheim/tesseract/wiki
# and check the German + English language data during install.
```

### Using it

```bash
# CLI — pair with --recompress for the smallest searchable PDFs
actari build-pdfs --ocr --recompress --force
actari run --ocr --ocr-language eng+deu --parent-naid 12345

# Web UI: Discovery → Download → tick "Add OCR text layer to assembled PDFs"
# A language input appears (default eng+deu — Tesseract codes, '+' separated)
```

### Notes

- **Default language is `eng+deu`** — the IG-Farben / NARA captured-German
  corpus that motivated this tool is mostly bilingual. Tune via
  `--ocr-language` (e.g. `eng+deu+fra`, `lat`, `nld`).
- **Skip-text mode** is on by default — pages that already contain text
  (rare for NARA scans but common for native PDFs) are kept as-is.
- **OCR is slow** — expect 3–15 seconds per page on a typical laptop.
  For a 100-page File Unit, plan for several minutes per PDF. Run
  overnight for bulk jobs.
- **Original sources under `raw/` are never touched.** The OCR pass
  rewrites the assembled PDF in place via a temp-and-rename, so a
  partial OCR run can never corrupt the file you already have.
- **Missing dependency = clean error.** If you turn on `--ocr` without
  ocrmypdf or Tesseract installed, the tool exits with a one-line
  install hint instead of a stack trace.

## Custom presets

You can add your own starter searches without modifying the package.
Create a file at `~/.actari/presets.json` (run `actari presets --path` to
print the exact location) using the same shape as the bundled list:

```json
{
  "presets": [
    {
      "id": "my-research-bayer",
      "title": "Bayer Leverkusen — my project",
      "description": "Starting points for the IG-Farben successor company.",
      "category": "My research",
      "search": {
        "q": "Bayer Leverkusen",
        "record_group": ["242", "260"]
      },
      "tags": ["bayer", "successor-firms"]
    }
  ]
}
```

Rules:
- New `id`s are appended to the end of the list.
- An `id` that matches a bundled entry **overrides** it in-place.
- The web UI tags user entries with a small "user" badge.
- If the file is invalid JSON or fails validation, the web UI logs a
  warning and falls back to bundled-only — your `~/.actari/presets.json`
  never blanks the Starter-searches panel.
- `actari presets` lists everything; `actari presets --bundled-only` skips
  your file; `actari presets --path` prints the file location.

## Acknowledgments

This tool is built on a stack of excellent open-source libraries. Thanks
to all of their maintainers.

**Runtime dependencies**

| Library | Purpose | License |
| --- | --- | --- |
| [requests](https://github.com/psf/requests) | HTTP client for the NARA API and S3 binary fetches | Apache-2.0 |
| [tenacity](https://github.com/jd/tenacity) | Retry-with-backoff for transient upstream errors | Apache-2.0 |
| [httpx](https://github.com/encode/httpx) | Async HTTP (FastAPI test client) | BSD-3-Clause |
| [typer](https://github.com/tiangolo/typer) | CLI framework | MIT |
| [rich](https://github.com/Textualize/rich) | Terminal formatting (tables, prompts) | MIT |
| [tqdm](https://github.com/tqdm/tqdm) | Progress bars for long-running phases | MIT + MPL-2.0 |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | Legacy `.env` loading | BSD-3-Clause |
| [python-slugify](https://github.com/un33k/python-slugify) | Stable filename slugs from titles | MIT |
| [img2pdf](https://gitlab.mister-muffin.de/josch/img2pdf) | Lossless JPEG/TIFF → PDF assembly | LGPL-3.0 |
| [pypdf](https://github.com/py-pdf/pypdf) | PDF merging and metadata stamping | BSD-3-Clause |
| [Pillow](https://github.com/python-pillow/Pillow) | Image decoding for TIFF fallback paths | HPND |
| [FastAPI](https://github.com/tiangolo/fastapi) | Web API framework for the local UI | MIT |
| [Starlette](https://github.com/encode/starlette) | ASGI toolkit (HTTP, StaticFiles, Range support) | BSD-3-Clause |
| [Pydantic](https://github.com/pydantic/pydantic) | API DTOs and validation | MIT |
| [uvicorn](https://github.com/encode/uvicorn) | ASGI server | BSD-3-Clause |
| [keyring](https://github.com/jaraco/keyring) *(optional)* | OS-keyring storage for the API key | MIT |
| [ocrmypdf](https://github.com/ocrmypdf/OCRmyPDF) *(optional, `[ocr]` extra)* | Adds a searchable text layer to assembled PDFs | MPL-2.0 |
| [Tesseract](https://github.com/tesseract-ocr/tesseract) *(external binary, required by `[ocr]`)* | OCR engine that backs ocrmypdf | Apache-2.0 |

**Development & build**

| Tool | Purpose | License |
| --- | --- | --- |
| [pytest](https://github.com/pytest-dev/pytest) | Test runner | MIT |
| [ruff](https://github.com/astral-sh/ruff) | Linter + formatter | MIT |
| [hatchling](https://github.com/pypa/hatch) | Build backend | MIT |

**Data and services**

- [National Archives Catalog API v2](https://catalog.archives.gov/) — the
  records themselves are works of the US government and, per
  [17 U.S.C. § 105](https://www.copyright.gov/title17/92chap1.html#105),
  not subject to copyright in the United States.
- [NARA on AWS Open Data](https://registry.opendata.aws/nara/) — the
  recommended bulk mirror for full-archive workloads.

If you ship a downstream project that uses `actari`, please keep
this acknowledgments list intact so the chain of credit stays visible.

## Citation

If you use this tool in academic or journalistic work, please cite it:

```bibtex
@software{nara_archive,
  author  = {Ramm, Christopher},
  title   = {actari: bulk-download and PDF assembly for the NARA Catalog},
  year    = {2026},
  url     = {https://github.com/rammc/actari},
  version = {1.0.0}
}
```

## License

[MIT](LICENSE) — © 2026 Christopher Ramm.

The license applies to the source code in this repository only. The
records you download from NARA are US government works; see the NARA terms
of use linked above for the (very permissive) rules that apply to them.

## Contributing

Issues and PRs welcome at <https://github.com/rammc/actari/issues>.
See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, tests, and PR
checklist. A [changelog](CHANGELOG.md) lives alongside.
