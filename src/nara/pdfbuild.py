"""Phase 3: assemble one consolidated PDF per File Unit."""

from __future__ import annotations

import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Literal

import img2pdf
import pypdf
from PIL import Image, ImageOps
from tqdm import tqdm

from .downloader import JobCancelled
from .utils import OutputPaths, get_logger

ProgressCallback = Callable[[dict[str, Any]], None]

SourceKind = Literal["image", "pdf", "skip"]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".gif", ".bmp"}
PDF_EXTS = {".pdf"}
NON_DOCUMENT_EXTS = {".mp3", ".mp4", ".wav", ".m4a", ".mov", ".avi", ".aac", ".flac", ".ogg"}

# Recompression defaults — sized for "readable on screen and printable at
# letter size" rather than archival fidelity. NARA's reference scans tend
# to be 4000-6000px wide at 300-600 DPI; 2400px / Q82 keeps detail for
# typewritten and handwritten text while typically shrinking files 5-10x.
RECOMPRESS_QUALITY = 82
RECOMPRESS_MAX_DIM = 2400
RECOMPRESS_SKIP_BELOW_BYTES = 200_000  # don't bother with already-small images


def classify_source(path: Path) -> SourceKind:
    """Decide how a file participates in PDF assembly.

    Prefers magic bytes over file extension because NARA filenames are
    occasionally misleading.
    """
    try:
        with path.open("rb") as fh:
            head = fh.read(12)
    except OSError:
        return "skip"

    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\xff\xd8\xff"):  # JPEG
        return "image"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image"
    if head[:4] in (b"II*\x00", b"MM\x00*"):  # TIFF
        return "image"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "image"
    if head.startswith(b"BM"):
        return "image"
    if head.startswith(b"ID3") or head[:2] == b"\xff\xfb":
        return "skip"
    if head[4:8] == b"ftyp":  # MP4 / MOV / M4A
        return "skip"
    if head.startswith(b"RIFF"):  # WAV / AVI
        return "skip"

    # Fall back to suffix if magic bytes were uninformative (e.g. empty file).
    suffix = path.suffix.lower()
    if suffix in NON_DOCUMENT_EXTS:
        return "skip"
    if suffix in PDF_EXTS:
        return "pdf"
    if suffix in IMAGE_EXTS:
        return "image"
    return "skip"


def _convert_tiff_to_jpg(src: Path, work_dir: Path, *, quality: int = 92) -> Path:
    """img2pdf rejects many real-world TIFFs; route them through Pillow→JPEG."""
    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / (src.stem + "__from-tiff.jpg")
    with Image.open(src) as img:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(out, format="JPEG", quality=quality)
    return out


def _recompress_to_jpeg(
    src: Path,
    work_dir: Path,
    *,
    quality: int = RECOMPRESS_QUALITY,
    max_dim: int = RECOMPRESS_MAX_DIM,
) -> Path:
    """Re-encode ``src`` as a downsized, lower-quality JPEG. Always lossy."""
    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / (src.stem + "__recompressed.jpg")
    with Image.open(src) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        elif img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        img.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
    return out


def _prepare_image(src: Path, work_dir: Path, *, recompress: bool = False) -> Path:
    """Return an img2pdf-friendly path for ``src``. May convert TIFFs and/or
    re-encode large JPEGs/PNGs into smaller JPEGs when ``recompress`` is set.
    """
    log = get_logger()
    suffix = src.suffix.lower()
    is_tiff = suffix in {".tif", ".tiff"}

    if recompress:
        # TIFFs are always re-encoded when recompress is on (they're huge).
        # Other images skip recompression when already smaller than the threshold.
        try:
            if is_tiff or src.stat().st_size > RECOMPRESS_SKIP_BELOW_BYTES:
                return _recompress_to_jpeg(src, work_dir)
        except Exception as e:  # noqa: BLE001 — Pillow raises many types on weird inputs
            log.warning("recompress failed for %s (%s) — falling back to original", src.name, e)
            # fall through to the non-recompress path below

    if is_tiff:
        try:
            # img2pdf can handle some TIFFs; try first to avoid lossy re-encode.
            with src.open("rb") as fh:
                img2pdf.convert(fh.read())
            return src
        except Exception:  # noqa: BLE001 — img2pdf raises many exception types
            return _convert_tiff_to_jpg(src, work_dir)
    return src


def assemble_pdf(
    sources: list[Path],
    out_path: Path,
    *,
    work_dir: Path,
    recompress: bool = False,
) -> int:
    """Assemble ``sources`` (in order) into a single PDF at ``out_path``.

    Returns the page count of the resulting PDF. When ``recompress`` is set,
    JPEGs/PNGs above 200 KB and all TIFFs are re-encoded as 2400px max,
    quality-82 JPEGs before being fed to img2pdf — typically shrinks the
    final PDF 5-10x with no perceptible loss for typewritten text.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    parts: list[Path] = []
    images_run: list[Path] = []

    def _flush_images() -> None:
        if not images_run:
            return
        prepared = [_prepare_image(p, work_dir, recompress=recompress) for p in images_run]
        partial = work_dir / f"images-{len(parts):03d}.pdf"
        with partial.open("wb") as fh:
            fh.write(img2pdf.convert([str(p) for p in prepared]))
        parts.append(partial)
        images_run.clear()

    for src in sources:
        kind = classify_source(src)
        if kind == "image":
            images_run.append(src)
        elif kind == "pdf":
            _flush_images()
            parts.append(src)
        else:
            get_logger().warning("assemble_pdf: skipping non-document %s", src.name)

    _flush_images()

    if not parts:
        raise ValueError(f"no usable sources to assemble for {out_path.name}")

    merger = pypdf.PdfWriter()
    for part in parts:
        merger.append(str(part))
    with out_path.open("wb") as fh:
        merger.write(fh)
    merger.close()

    reader = pypdf.PdfReader(str(out_path))
    return len(reader.pages)


def _sorted_sources(unit: dict, unit_dir: Path) -> list[tuple[Path, dict]]:
    """Order digital objects by ``sort_number`` ASC, fall back to filename."""
    objs = list(unit.get("digital_objects", []))

    def key(o: dict) -> tuple[int, str]:
        sn = o.get("sort_number")
        return (sn if isinstance(sn, int) else 10**9, o.get("filename") or "")

    objs.sort(key=key)
    out: list[tuple[Path, dict]] = []
    for o in objs:
        p = unit_dir / o["filename"]
        if p.exists():
            out.append((p, o))
        else:
            get_logger().warning("naid=%s missing on disk: %s", unit.get("naid"), o.get("filename"))
    return out


def build_pdfs(
    paths: OutputPaths,
    *,
    force: bool = False,
    recompress: bool = False,
    metadata: dict | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    show_progress_bars: bool = True,
) -> list[dict]:
    """Build one PDF per File Unit. Returns per-unit result rows for the manifest.

    Cancel/progress hooks mirror :func:`download_all`. Cancellation is checked
    *between* File Units — a unit already mid-build runs to completion to keep
    the on-disk state clean. When ``recompress=True``, source images are
    downsized/re-encoded before PDF assembly to keep output sizes manageable.
    Note: existing PDFs are still skipped unless ``force=True`` — if you turn
    recompression on after an initial build, also pass ``--force`` to rebuild.
    """
    import json

    log = get_logger()
    paths.ensure()
    if metadata is None:
        metadata = json.loads(paths.metadata.read_text(encoding="utf-8"))

    units = metadata.get("file_units", [])
    results: list[dict] = []
    total = len(units)

    def _emit(seq: int, naid: str, status: str, page_count: int = 0) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(
                {
                    "phase": "building_pdfs",
                    "current": seq,
                    "total": total,
                    "current_naid": naid,
                    "status": status,
                    "page_count": page_count,
                }
            )
        except Exception:  # noqa: BLE001
            log.exception("progress_callback raised; continuing")

    iterable = tqdm(units, desc="pdfs", unit="unit", disable=not show_progress_bars)
    for seq, unit in enumerate(iterable, start=1):
        if cancel_event is not None and cancel_event.is_set():
            raise JobCancelled("build-pdfs cancelled by user")
        naid = str(unit.get("naid") or "").strip()
        slug = unit.get("slug") or "untitled"
        if not naid:
            log.warning("seq=%04d empty NAID — skipping", seq)
            continue

        unit_dir = paths.raw_dir_for(naid)
        ordered = _sorted_sources(unit, unit_dir)
        if not ordered:
            results.append(
                _result_row(
                    unit,
                    seq,
                    status="failed",
                    pdf_path=None,
                    pdf_size=0,
                    page_count=0,
                    reason="no files on disk",
                )
            )
            log.error("naid=%s no source files on disk — failed", naid)
            _append_build_error(paths, naid, "no files on disk")
            _emit(seq, naid, "failed")
            continue

        # Classify everything once to decide doc vs non-doc.
        kinds = [classify_source(p) for (p, _o) in ordered]
        usable_count = sum(1 for k in kinds if k in ("image", "pdf"))
        if usable_count == 0:
            results.append(
                _result_row(
                    unit,
                    seq,
                    status="skipped_non_document",
                    pdf_path=None,
                    pdf_size=0,
                    page_count=0,
                )
            )
            log.info("naid=%s skipped_non_document (all %d sources non-doc)", naid, len(ordered))
            _emit(seq, naid, "skipped_non_document")
            continue

        out_path = paths.pdfs_dir / f"{seq:04d}-{naid}_{slug}.pdf"
        if out_path.exists() and out_path.stat().st_size > 0 and not force:
            page_count = _safe_page_count(out_path)
            results.append(
                _result_row(
                    unit,
                    seq,
                    status="ok",
                    pdf_path=out_path,
                    pdf_size=out_path.stat().st_size,
                    page_count=page_count,
                )
            )
            log.info("naid=%s skip rebuild (exists, %d pages)", naid, page_count)
            _emit(seq, naid, "ok", page_count)
            continue

        source_size_total = sum(p.stat().st_size for (p, _o) in ordered if p.exists())
        with tempfile.TemporaryDirectory(prefix=f"nara-{naid}-") as work:
            try:
                page_count = assemble_pdf(
                    [p for (p, _o) in ordered],
                    out_path,
                    work_dir=Path(work),
                    recompress=recompress,
                )
            except Exception as e:  # noqa: BLE001
                log.exception("naid=%s assemble failed: %s", naid, e)
                _append_build_error(paths, naid, f"assemble failed: {e}")
                if out_path.exists():
                    out_path.unlink(missing_ok=True)
                results.append(
                    _result_row(
                        unit,
                        seq,
                        status="failed",
                        pdf_path=None,
                        pdf_size=0,
                        page_count=0,
                        reason=str(e),
                    )
                )
                _emit(seq, naid, "failed")
                continue

        size = out_path.stat().st_size
        results.append(
            _result_row(
                unit,
                seq,
                status="ok",
                pdf_path=out_path,
                pdf_size=size,
                page_count=page_count,
                source_size_bytes=source_size_total,
            )
        )
        if recompress and source_size_total > 0:
            ratio = size / source_size_total
            log.info(
                "naid=%s built %s pages=%d size=%d (recompressed: %.2fx of %d source bytes)",
                naid,
                out_path.name,
                page_count,
                size,
                ratio,
                source_size_total,
            )
        else:
            log.info("naid=%s built %s pages=%d size=%d", naid, out_path.name, page_count, size)
        _emit(seq, naid, "ok", page_count)

    return results


def _safe_page_count(pdf_path: Path) -> int:
    try:
        return len(pypdf.PdfReader(str(pdf_path)).pages)
    except Exception:  # noqa: BLE001
        return 0


def _append_build_error(paths: OutputPaths, naid: str, reason: str) -> None:
    paths.errors_log.parent.mkdir(parents=True, exist_ok=True)
    with paths.errors_log.open("a", encoding="utf-8") as fh:
        fh.write(f"naid={naid}\tphase=build\treason={reason}\n")


def _result_row(
    unit: dict,
    seq: int,
    *,
    status: str,
    pdf_path: Path | None,
    pdf_size: int,
    page_count: int,
    reason: str | None = None,
    source_size_bytes: int | None = None,
) -> dict:
    return {
        "seq": seq,
        "naid": unit.get("naid"),
        "title": unit.get("title"),
        "slug": unit.get("slug"),
        "scope_and_content_note": unit.get("scope_and_content_note"),
        "inclusive_start_year": unit.get("inclusive_start_year"),
        "inclusive_end_year": unit.get("inclusive_end_year"),
        "pdf_path": None if pdf_path is None else f"pdfs/{pdf_path.name}",
        "pdf_size_bytes": pdf_size,
        "page_count": page_count,
        "source_object_count": unit.get("digital_object_count", 0),
        "status": status,
        **({"reason": reason} if reason else {}),
        **({"source_size_bytes": source_size_bytes} if source_size_bytes is not None else {}),
    }


def cleanup_tempdir_if_empty(tmp: Path) -> None:
    """Best-effort cleanup. Unused safety net for future callers."""
    try:
        shutil.rmtree(tmp)
    except OSError:
        pass
