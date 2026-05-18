"""Background "is there a newer version?" check against GitHub Releases.

Hits ``https://api.github.com/repos/{owner}/{repo}/releases/latest`` exactly
once at server startup, caches the result on ``app.state.update_info``, and
exposes it via :func:`get_update_info`. There is no telemetry, no phone-home
beyond this single anonymous GET, and the entire feature can be turned off
by setting ``[updates] check_on_startup = false`` in ``~/.nara/config.toml``.

Version comparison uses :class:`packaging.version.Version` when available
and falls back to a tuple-of-ints split that's correct for the
``MAJOR.MINOR.PATCH`` scheme this project uses.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger("nara.updater")

DEFAULT_REPO = "rammc/nara-archive"
RELEASES_URL_TEMPLATE = "https://api.github.com/repos/{repo}/releases/latest"
TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str | None = None
    release_url: str | None = None
    available: bool = False
    error: str | None = None  # short reason if the check failed; UI can hide


def _normalize(tag: str) -> str:
    """Strip a leading 'v' or 'V' so version compare is consistent."""
    return tag[1:] if tag and tag[:1] in ("v", "V") else tag


_VERSION_PART = re.compile(r"\d+")


def _as_tuple(v: str) -> tuple[int, ...]:
    """Fallback tuple-of-ints parser. Handles ``1.2.3`` and ``1.2.3-rc1`` safely."""
    parts = _VERSION_PART.findall(_normalize(v))
    return tuple(int(p) for p in parts[:4]) if parts else (0,)


def is_newer(latest: str, current: str) -> bool:
    """True iff ``latest`` is strictly newer than ``current``."""
    if not latest or not current:
        return False
    try:
        from packaging.version import InvalidVersion, Version

        try:
            return Version(_normalize(latest)) > Version(_normalize(current))
        except InvalidVersion:
            return _as_tuple(latest) > _as_tuple(current)
    except ImportError:
        return _as_tuple(latest) > _as_tuple(current)


async def check_for_update(
    current_version: str,
    *,
    repo: str = DEFAULT_REPO,
    client: httpx.AsyncClient | None = None,
) -> UpdateInfo:
    """One-shot release check. Never raises — returns ``error`` on failure."""
    url = RELEASES_URL_TEMPLATE.format(repo=repo)
    own_client = client is None
    try:
        if own_client:
            client = httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
        assert client is not None
        try:
            resp = await client.get(url, headers={"Accept": "application/vnd.github+json"})
        finally:
            if own_client:
                await client.aclose()
    except httpx.RequestError as e:
        log.info("update check failed: %s", e)
        return UpdateInfo(current_version=current_version, error=str(e))

    if resp.status_code == 404:
        # No published releases yet — perfectly normal pre-v1; not an error.
        return UpdateInfo(current_version=current_version)
    if resp.status_code >= 400:
        return UpdateInfo(
            current_version=current_version, error=f"GitHub returned HTTP {resp.status_code}"
        )

    body: Any = resp.json()
    if not isinstance(body, dict):
        return UpdateInfo(current_version=current_version, error="unexpected payload shape")

    latest = body.get("tag_name") or body.get("name") or ""
    release_url = body.get("html_url") or None
    return UpdateInfo(
        current_version=current_version,
        latest_version=_normalize(latest) or None,
        release_url=release_url,
        available=is_newer(latest, current_version),
    )


def schedule_startup_check(app, *, current_version: str, enabled: bool) -> None:
    """Fire the update check from the FastAPI lifespan without blocking startup."""
    app.state.update_info = UpdateInfo(current_version=current_version)
    if not enabled:
        return

    async def _run():
        info = await check_for_update(current_version)
        app.state.update_info = info
        if info.available:
            log.info(
                "newer release available: %s (current %s)", info.latest_version, current_version
            )

    # ``asyncio.create_task`` requires a running loop; lifespan provides one.
    asyncio.create_task(_run())
