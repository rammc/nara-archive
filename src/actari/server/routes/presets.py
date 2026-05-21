"""Presets route: serve the curated starter-search list (bundled + user)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ...presets import PresetError, load_all_presets, load_presets
from ..models import Preset, PresetListResponse

log = logging.getLogger("actari")
router = APIRouter(prefix="/api/presets", tags=["presets"])


@router.get("", response_model=PresetListResponse)
def list_presets() -> PresetListResponse:
    """Return merged bundled + user presets. Falls back to bundled-only on
    user-file errors so a typo in ``~/.actari/presets.json`` never blanks the UI.
    """
    try:
        data = load_all_presets()
    except PresetError as e:
        # User file is malformed — keep the UI usable by falling back to bundled.
        log.warning("user presets file rejected, serving bundled only: %s", e)
        try:
            data = [{**p, "source": "bundled"} for p in load_presets()]
        except PresetError as e2:
            raise HTTPException(500, f"preset bundle is malformed: {e2}") from e2
    return PresetListResponse(presets=[Preset(**p) for p in data])
