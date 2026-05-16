"""Discovery routes: proxy NARA search and record-detail lookups."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ...api import NaraApiError, NaraClient
from ...utils import safe_get as _safe_get
from ..models import ChildrenResponse, RecordDetail, SearchHit, SearchResponse

router = APIRouter(prefix="/api", tags=["search"])


def get_nara_client(request: Request) -> NaraClient:
    """Build a NaraClient from the app config. Tests override this via Depends."""
    cfg = request.app.state.config
    if not cfg.api_key:
        raise HTTPException(503, "NARA API key not configured. Run `nara init`.")
    return NaraClient(api_key=cfg.api_key, base=cfg.api_base_url)


def _hit_to_dto(hit: dict[str, Any]) -> SearchHit | None:
    record = _safe_get(hit, "_source", "record", default=None)
    if not isinstance(record, dict):
        return None
    naid = str(record.get("naId") or "").strip()
    if not naid:
        return None
    objs = record.get("digitalObjects") or []
    if not isinstance(objs, list):
        objs = []
    thumb = None
    for o in objs:
        if isinstance(o, dict) and o.get("objectUrl"):
            thumb = o.get("objectUrl")
            break
    sy = _safe_get(record, "inclusiveStartDate", "year")
    ey = _safe_get(record, "inclusiveEndDate", "year")
    return SearchHit(
        naid=naid,
        title=record.get("title"),
        level=record.get("levelOfDescription"),
        scope_and_content_note=record.get("scopeAndContentNote"),
        inclusive_start_year=sy if isinstance(sy, int) else None,
        inclusive_end_year=ey if isinstance(ey, int) else None,
        digital_object_count=len(objs),
        thumbnail_url=thumb,
    )


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, description="Free-text search; NARA requires non-empty q."),
    level: list[str] | None = Query(None, description="Filter by levelOfDescription."),
    year_from: int | None = Query(None, ge=0),
    year_to: int | None = Query(None, ge=0),
    has_digital_objects: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    client: NaraClient = Depends(get_nara_client),
) -> SearchResponse:
    """Proxy NARA's ``/records/search`` with sensible defaults and a clean schema."""
    params: dict[str, Any] = {"q": q, "page": page, "limit": page_size}
    if level:
        params["levelOfDescription"] = ",".join(level)
    if year_from is not None:
        params["startDate"] = str(year_from)
    if year_to is not None:
        params["endDate"] = str(year_to)
    if has_digital_objects:
        params["availableOnline"] = "true"
    try:
        raw = await asyncio.to_thread(client.search, params)
    except NaraApiError as e:
        raise HTTPException(502, str(e)) from e

    hits_raw = _safe_get(raw, "body", "hits", "hits", default=[]) or []
    total = _safe_get(raw, "body", "hits", "total", "value", default=0) or 0
    hits = [dto for h in hits_raw if isinstance(h, dict) and (dto := _hit_to_dto(h))]
    return SearchResponse(hits=hits, total=int(total), page=page, page_size=page_size)


@router.get("/records/{naid}", response_model=RecordDetail)
async def get_record(
    naid: str,
    client: NaraClient = Depends(get_nara_client),
) -> RecordDetail:
    """Full record details (raw NARA ``_source.record`` shape under ``record``)."""
    try:
        raw = await asyncio.to_thread(client.get_record, naid)
    except NaraApiError as e:
        raise HTTPException(502, str(e)) from e
    if not raw:
        raise HTTPException(404, f"record {naid} not found")
    hits = _safe_get(raw, "body", "hits", "hits", default=[]) or []
    if not hits:
        raise HTTPException(404, f"record {naid} not found")
    record = _safe_get(hits[0], "_source", "record", default={}) or {}
    return RecordDetail(
        naid=str(record.get("naId") or naid),
        title=record.get("title"),
        level=record.get("levelOfDescription"),
        record=record,
        digital_objects=record.get("digitalObjects") or [],
    )


@router.get("/records/{naid}/children", response_model=ChildrenResponse)
async def get_children(
    naid: str,
    limit: int = Query(100, ge=1, le=300),
    client: NaraClient = Depends(get_nara_client),
) -> ChildrenResponse:
    """Immediate children via NARA's ``/records/parentNaId/{naId}`` route."""
    try:
        raw = await asyncio.to_thread(client.get_children, naid, limit=limit)
    except NaraApiError as e:
        raise HTTPException(502, str(e)) from e
    hits_raw = _safe_get(raw, "body", "hits", "hits", default=[]) or []
    total = _safe_get(raw, "body", "hits", "total", "value", default=0) or 0
    hits = [dto for h in hits_raw if isinstance(h, dict) and (dto := _hit_to_dto(h))]
    return ChildrenResponse(parent_naid=naid, total=int(total), hits=hits)


# Re-export for convenience in app.py
__all__ = ["router", "get_nara_client"]
