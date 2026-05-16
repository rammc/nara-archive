"""Phase 1: fetch parent's children metadata and normalize it."""
from __future__ import annotations

import json
from collections import Counter
from typing import Any

from .api import API_BASE, NaraApiError, NaraClient
from .utils import OutputPaths, atomic_write_text, get_logger, make_slug, utc_now_iso

SCHEMA_VERSION = "1.0"


def _safe_get(d: Any, *path: str, default: Any = None) -> Any:
    """Walk a nested dict/list path, returning ``default`` on any miss."""
    cur = d
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur


def _record_year(record: dict, which: str) -> int | None:
    block = record.get(which)
    if not isinstance(block, dict):
        return None
    year = block.get("year")
    if isinstance(year, int):
        return year
    try:
        return int(year) if year is not None else None
    except (TypeError, ValueError):
        return None


def _normalize_digital_object(obj: dict, naid: str) -> dict | None:
    log = get_logger()
    url = obj.get("objectUrl")
    filename = obj.get("objectFilename")
    if not url or not filename:
        log.warning("naid=%s skipping digital object missing url/filename: %r", naid, obj)
        return None
    size = obj.get("objectFileSize")
    try:
        size_int = int(size) if size is not None else None
    except (TypeError, ValueError):
        size_int = None
    sort_raw = obj.get("sortNumber")
    try:
        sort_int = int(sort_raw) if sort_raw is not None else None
    except (TypeError, ValueError):
        sort_int = None
    if sort_int is None:
        log.warning("naid=%s sortNumber missing for %s — will fall back to filename order",
                    naid, filename)
    return {
        "filename": filename,
        "url": url,
        "type": obj.get("objectType"),
        "size_bytes": size_int,
        "sort_number": sort_int,
    }


def _normalize_record(record: dict) -> dict:
    log = get_logger()
    naid = str(record.get("naId") or "").strip()
    if not naid:
        log.warning("record missing naId — keeping with empty id, downstream will skip: %r",
                    {k: record.get(k) for k in ("title", "levelOfDescription")})
    title = record.get("title")
    raw_objs = record.get("digitalObjects") or []
    if not isinstance(raw_objs, list):
        log.warning("naid=%s digitalObjects not a list (%s) — treating as empty",
                    naid, type(raw_objs).__name__)
        raw_objs = []
    objs: list[dict] = []
    for obj in raw_objs:
        if not isinstance(obj, dict):
            continue
        normalized = _normalize_digital_object(obj, naid)
        if normalized is not None:
            objs.append(normalized)

    return {
        "naid": naid,
        "title": title,
        "slug": make_slug(title),
        "level": record.get("levelOfDescription"),
        "scope_and_content_note": record.get("scopeAndContentNote"),
        "inclusive_start_year": _record_year(record, "inclusiveStartDate"),
        "inclusive_end_year": _record_year(record, "inclusiveEndDate"),
        "digital_objects": objs,
        "digital_object_count": len(objs),
    }


def normalize_response(raw: dict) -> list[dict]:
    """Normalize a NARA ``parentNaId`` response into a list of file-unit dicts.

    The API nests records inside ``body.hits.hits[i]._source.record``. Missing
    fields are tolerated everywhere — we log warnings rather than crashing.
    """
    hits = _safe_get(raw, "body", "hits", "hits", default=[]) or []
    units: list[dict] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        record = _safe_get(hit, "_source", "record", default=None)
        if not isinstance(record, dict):
            continue
        units.append(_normalize_record(record))
    return units


def fetch_and_persist(
    parent_naid: str,
    paths: OutputPaths,
    *,
    limit: int = 300,
    client: NaraClient | None = None,
) -> dict:
    """Phase 1 entry point. Returns the normalized metadata dict it writes."""
    log = get_logger()
    paths.ensure()
    client = client or NaraClient()

    log.info("Fetching children of parent NAID %s (limit=%d)", parent_naid, limit)
    raw = client.get_children(parent_naid, limit=limit)

    total = _safe_get(raw, "body", "hits", "total", "value", default=None)
    if isinstance(total, int) and total > limit:
        log.warning(
            "parent_naid=%s API reports %d children but limit was %d — re-run with --limit %d",
            parent_naid, total, limit, total,
        )

    atomic_write_text(paths.metadata_raw, json.dumps(raw, indent=2, ensure_ascii=False))

    units = normalize_response(raw)
    parent_title = _resolve_parent_title(parent_naid, client)

    doc = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "parent_naid": str(parent_naid),
            "parent_title": parent_title,
            "fetched_at": utc_now_iso(),
            "api_base": API_BASE,
        },
        "file_units": units,
    }
    atomic_write_text(paths.metadata, json.dumps(doc, indent=2, ensure_ascii=False))

    _print_summary(doc, total_reported=total)
    return doc


def _resolve_parent_title(parent_naid: str, client: NaraClient) -> str | None:
    """Best-effort lookup of the parent's title via ``records/search?naIds=``."""
    log = get_logger()
    try:
        rec = client.get_record(parent_naid)
    except Exception as e:  # noqa: BLE001 — title is nice-to-have, never fatal
        log.warning("parent_naid=%s could not resolve title: %s", parent_naid, e)
        return None
    if not rec:
        return None
    hits = _safe_get(rec, "body", "hits", "hits", default=None)
    if isinstance(hits, list) and hits:
        return _safe_get(hits[0], "_source", "record", "title", default=None)
    return None


def _print_summary(doc: dict, *, total_reported: int | None) -> None:
    log = get_logger()
    units = doc["file_units"]
    n_units = len(units)
    n_objs = sum(u["digital_object_count"] for u in units)
    type_counter: Counter[str] = Counter()
    for u in units:
        for o in u["digital_objects"]:
            type_counter[o.get("type") or "Unknown"] += 1

    log.info("== Metadata summary ==")
    log.info("Parent NAID:        %s", doc["source"]["parent_naid"])
    log.info("File units fetched: %d (API reported %s)", n_units,
             total_reported if total_reported is not None else "n/a")
    log.info("Digital objects:    %d", n_objs)
    if type_counter:
        log.info("By objectType:")
        for typ, count in type_counter.most_common():
            log.info("  %5d  %s", count, typ)
