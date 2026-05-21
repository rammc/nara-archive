"""Expose the cached update-check result via ``GET /api/updates``."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ... import __version__
from ...updater import UpdateInfo
from ..models import UpdateInfoDto

router = APIRouter(prefix="/api", tags=["updates"])


@router.get("/updates", response_model=UpdateInfoDto)
def get_updates(request: Request) -> UpdateInfoDto:
    info: UpdateInfo = getattr(request.app.state, "update_info", None) or UpdateInfo(
        current_version=__version__,
    )
    return UpdateInfoDto(
        current_version=info.current_version,
        latest_version=info.latest_version,
        release_url=info.release_url,
        available=info.available,
        error=info.error,
    )
