"""Presets route: serve the curated starter-search list."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...presets import PresetError, load_presets
from ..models import Preset, PresetListResponse

router = APIRouter(prefix="/api/presets", tags=["presets"])


@router.get("", response_model=PresetListResponse)
def list_presets() -> PresetListResponse:
    try:
        data = load_presets()
    except PresetError as e:
        raise HTTPException(500, f"preset bundle is malformed: {e}") from e
    return PresetListResponse(presets=[Preset(**p) for p in data])
