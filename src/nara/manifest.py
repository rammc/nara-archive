"""Build the final manifest.json from per-File-Unit build results."""

from __future__ import annotations

import json
from pathlib import Path

from .utils import OutputPaths, atomic_write_text, get_logger, utc_now_iso

SCHEMA_VERSION = "1.0"


def write_manifest(
    paths: OutputPaths,
    *,
    metadata: dict,
    build_results: list[dict],
    out_path: Path | None = None,
) -> dict:
    """Combine metadata.source + build_results into a manifest file. Returns the doc.

    ``out_path`` defaults to ``paths.manifest`` (i.e. ``output/manifest.json``).
    Pass an explicit path to write a subset manifest like ``manifest-igfarben.json``.
    """
    log = get_logger()

    by_naid = {str(r.get("naid")): r for r in build_results if r.get("naid")}

    file_units: list[dict] = []
    for unit in metadata.get("file_units", []):
        naid = str(unit.get("naid") or "")
        r = by_naid.get(naid)
        if not r:
            file_units.append(
                {
                    "naid": unit.get("naid"),
                    "title": unit.get("title"),
                    "slug": unit.get("slug"),
                    "scope_and_content_note": unit.get("scope_and_content_note"),
                    "inclusive_start_year": unit.get("inclusive_start_year"),
                    "inclusive_end_year": unit.get("inclusive_end_year"),
                    "pdf_path": None,
                    "pdf_size_bytes": 0,
                    "page_count": 0,
                    "source_object_count": unit.get("digital_object_count", 0),
                    "status": "missing",
                }
            )
            continue
        file_units.append(
            {
                "naid": r.get("naid"),
                "title": r.get("title"),
                "slug": r.get("slug"),
                "scope_and_content_note": r.get("scope_and_content_note"),
                "inclusive_start_year": r.get("inclusive_start_year"),
                "inclusive_end_year": r.get("inclusive_end_year"),
                "pdf_path": r.get("pdf_path"),
                "pdf_size_bytes": r.get("pdf_size_bytes", 0),
                "page_count": r.get("page_count", 0),
                "source_object_count": r.get("source_object_count", 0),
                "status": r.get("status", "ok"),
            }
        )

    stats = _compute_stats(file_units)

    doc = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "source": metadata.get("source", {}),
        "stats": stats,
        "file_units": file_units,
    }
    target = out_path if out_path is not None else paths.manifest
    atomic_write_text(target, json.dumps(doc, indent=2, ensure_ascii=False))
    log.info(
        "Manifest written to %s: %d units (ok=%d failed=%d skipped_non_document=%d)",
        target,
        stats["total_file_units"],
        stats["successful_pdfs"],
        stats["failed_pdfs"],
        stats["skipped_non_document"],
    )
    return doc


def _compute_stats(units: list[dict]) -> dict:
    total = len(units)
    ok = sum(1 for u in units if u["status"] == "ok")
    failed = sum(1 for u in units if u["status"] in ("failed", "missing"))
    skipped = sum(1 for u in units if u["status"] == "skipped_non_document")
    pages = sum(int(u.get("page_count") or 0) for u in units)
    bytes_ = sum(int(u.get("pdf_size_bytes") or 0) for u in units)
    return {
        "total_file_units": total,
        "successful_pdfs": ok,
        "failed_pdfs": failed,
        "skipped_non_document": skipped,
        "total_pages": pages,
        "total_size_bytes": bytes_,
    }


def verify_manifest(
    paths: OutputPaths, *, manifest_path: Path | None = None
) -> tuple[int, list[str]]:
    """Check every manifest entry resolves to a real, non-empty file on disk.

    Returns ``(exit_code, problems)``. Skipped/failed entries with ``pdf_path=None``
    are allowed; only ``status == "ok"`` entries must have a present file. Pass
    ``manifest_path`` to verify a subset manifest like ``manifest-igfarben.json``.
    """
    target = manifest_path if manifest_path is not None else paths.manifest
    if not target.exists():
        return 1, [f"manifest not found: {target}"]
    doc = json.loads(target.read_text(encoding="utf-8"))
    problems: list[str] = []
    for u in doc.get("file_units", []):
        status = u.get("status")
        path = u.get("pdf_path")
        if status != "ok":
            continue
        if not path:
            problems.append(f"naid={u.get('naid')} ok but pdf_path missing")
            continue
        full = paths.root / path
        if not full.exists():
            problems.append(f"naid={u.get('naid')} pdf_path not on disk: {full}")
            continue
        if full.stat().st_size <= 0:
            problems.append(f"naid={u.get('naid')} pdf is empty: {full}")
            continue
        expected = u.get("pdf_size_bytes")
        if isinstance(expected, int) and expected > 0 and full.stat().st_size != expected:
            problems.append(
                f"naid={u.get('naid')} size mismatch on-disk={full.stat().st_size} "
                f"manifest={expected}"
            )
    return (0 if not problems else 1), problems
