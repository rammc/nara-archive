# Screenshots

Stills used in the project README and the announce post.

## Naming convention

`{NN}-{tab}.png`, two-digit sequence number:

- `01-discovery.png` — Discovery tab with search results
- `02-downloads.png` — Downloads tab with one job in progress
- `03-library.png` — Library tab showing a manifest
- `04-pdf-preview.png` — One PDF open in the side panel

The animated overview at the top of the project README can stitch these
together — keep individual stills in this folder.

## Capture checklist (manual)

End-to-end run that produces all four shots:

```bash
actari init                               # if not done yet
actari serve --no-browser &
open http://127.0.0.1:8765
```

1. **Discovery** — type `I.G. Farben` into the search bar. Wait for the
   results to render. Take `01-discovery.png` showing at least 4 result
   cards.
2. Click *Download* on a card with a reasonable digital_object_count
   (~50–200), set a recognisable name (e.g. `demo`), accept the rate
   default. Submit. The tab switches.
3. **Downloads** — wait until the job is in `downloading` phase with the
   progress bar partway across. Take `02-downloads.png`.
4. Let the job complete. Switch to **Library**. Take `03-library.png`
   showing the new manifest card plus any older ones.
5. Click the manifest, then click a file unit to open the PDF in the
   side panel. Take `04-pdf-preview.png`.

Use a 1440×900 viewport for consistency. On macOS, ⌘-Shift-4 then Space
captures the active window cleanly.

## Output PDF size disclosure

When demoing on social, mention up-front that PDFs are not recompressed by
default — a single 64-page File Unit in T83 can be 400 MB because NARA's
scans are 6-MB JPGs each. Opt-in recompression (`--recompress`) is available;
see [Recompression](../../README.md#recompression) in the README.
