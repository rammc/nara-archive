"""Library routes: list local manifests, drill into one, search within."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from ...utils import (
    manifest_name_from_path,
    manifest_path_for_name,
    validate_filter_name,
)
from ..models import (
    LibraryDetail,
    LibraryEntry,
    LibraryFileUnit,
    LibraryListResponse,
    LibrarySearchResponse,
)

router = APIRouter(prefix="/api/library", tags=["library"])


def _load_manifest(path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _to_entry(name: str, doc: dict[str, Any]) -> LibraryEntry:
    source = doc.get("source", {}) or {}
    stats = doc.get("stats", {}) or {}
    return LibraryEntry(
        name=name,
        parent_naid=source.get("parent_naid"),
        parent_title=source.get("parent_title"),
        file_unit_count=int(stats.get("total_file_units", 0) or 0),
        pdf_count=int(stats.get("successful_pdfs", 0) or 0),
        total_size_bytes=int(stats.get("total_size_bytes", 0) or 0),
        generated_at=doc.get("generated_at"),
    )


def _resolve_manifest_path(request: Request, name: str):
    """Pick the manifest file for ``name``; 404 if missing."""
    cfg = request.app.state.config
    try:
        if name != "default":
            validate_filter_name(name)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    path = manifest_path_for_name(cfg.output_dir, name)
    if not path.exists():
        raise HTTPException(404, f"manifest {name!r} not found")
    return path


@router.get("", response_model=LibraryListResponse)
def list_manifests(request: Request) -> LibraryListResponse:
    cfg = request.app.state.config
    out = cfg.output_dir
    items: list[LibraryEntry] = []
    if out.exists():
        for path in sorted(
            out.glob("manifest*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            doc = _load_manifest(path)
            if not doc:
                continue
            items.append(_to_entry(manifest_name_from_path(path), doc))
    return LibraryListResponse(manifests=items)


@router.get("/{name}", response_model=LibraryDetail)
def manifest_detail(name: str, request: Request) -> LibraryDetail:
    path = _resolve_manifest_path(request, name)
    doc = _load_manifest(path)
    if doc is None:
        raise HTTPException(500, f"manifest {name!r} is unreadable")
    return LibraryDetail(
        name=name,
        schema_version=doc.get("schema_version"),
        source=doc.get("source", {}) or {},
        stats=doc.get("stats", {}) or {},
        file_units=[LibraryFileUnit(**u) for u in doc.get("file_units", []) or []],
    )


@router.get("/{name}/search", response_model=LibrarySearchResponse)
def search_manifest(
    name: str,
    q: str = Query(..., min_length=1),
    request: Request = None,  # type: ignore[assignment]
) -> LibrarySearchResponse:
    path = _resolve_manifest_path(request, name)
    doc = _load_manifest(path)
    if doc is None:
        raise HTTPException(500, f"manifest {name!r} is unreadable")
    pattern = re.compile(re.escape(q), re.IGNORECASE)
    matches: list[LibraryFileUnit] = []
    for u in doc.get("file_units", []) or []:
        title = u.get("title") or ""
        note = u.get("scope_and_content_note") or ""
        if pattern.search(title) or pattern.search(note):
            matches.append(LibraryFileUnit(**u))
    return LibrarySearchResponse(name=name, query=q, total=len(matches), matches=matches)
