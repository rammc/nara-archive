"""First-run setup routes for the bundled macOS app.

Users who installed via DMG never see a terminal — ``actari init`` is unreachable
for them. This module mirrors that wizard in HTTP form:

- ``GET /setup`` serves the setup HTML (or 302s to ``/`` if already configured)
- ``POST /api/setup/validate-key`` smoke-tests a candidate key against NARA
- ``POST /api/setup/complete`` persists the key (Keychain preferred on macOS,
  TOML fallback) plus terms acknowledgment, then redirects the browser to ``/``

Middleware installed by :func:`actari.server.app.create_app` short-circuits
unconfigured runs by redirecting other HTML routes to ``/setup``.

The module is named ``firstrun`` rather than ``setup`` on purpose:
PyInstaller's static analyser treats ``setup.py`` as a legacy distutils /
setuptools entry point and silently drops it from the bundle. The
v0.9.0-rc5 .app launched cleanly but every ``/setup`` request returned 404
because the module file simply wasn't there. Keep this name.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from ...config import DEFAULT_API_BASE_URL, write_config

log = logging.getLogger("actari")

router = APIRouter(tags=["setup"])

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


# ----- DTOs -----


class ValidateKeyBody(BaseModel):
    api_key: str = Field(..., min_length=10, max_length=80)


class ValidateKeyResponse(BaseModel):
    valid: bool
    message: str


class CompleteBody(BaseModel):
    api_key: str = Field(..., min_length=10, max_length=80)
    output_dir: str | None = None
    terms_acknowledged: bool = False


class CompleteResponse(BaseModel):
    saved_to: str
    used_keychain: bool


# ----- helpers -----


async def _ping_nara(api_key: str, base_url: str) -> tuple[bool, str]:
    """One lightweight call to the catalog API to confirm the key works."""
    url = base_url.rstrip("/") + "/records/search"
    headers = {"x-api-key": api_key, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={"q": "constitution", "limit": 1}, headers=headers)
    except httpx.RequestError as e:
        return False, f"Could not reach NARA ({e}). Check your internet connection."
    if resp.status_code == 401 or resp.status_code == 403:
        return False, "NARA rejected the key (401/403). Double-check it for typos."
    if resp.status_code >= 500:
        return False, f"NARA is having a bad day ({resp.status_code}). Try again in a moment."
    if resp.status_code >= 400:
        return False, f"Unexpected status {resp.status_code} from NARA."
    return True, "Key validated successfully."


def _save_to_keychain(api_key: str) -> bool:
    """Store the key in macOS Keychain. Returns False if unavailable."""
    import platform
    import sys

    if platform.system() != "Darwin":
        return False
    try:
        import keyring  # type: ignore[import-not-found]
    except ImportError:
        return False
    try:
        keyring.set_password("dev.cramm.actari", "api_key", api_key)
        # Heuristic: only count it as "used" when running in the bundled app
        # where Keychain is the documented default. From a pip install, we
        # still write TOML so users keep their familiar workflow.
        return bool(getattr(sys, "frozen", False))
    except Exception as e:  # noqa: BLE001 — keyring backends raise platform-specific errors
        log.warning("keyring write failed, falling back to TOML: %s", e)
        return False


# ----- routes -----


@router.get("/setup", include_in_schema=False)
async def setup_page(request: Request):
    """Serve the setup HTML — but redirect to / if the app is already configured."""
    cfg = request.app.state.config
    if cfg.has_api_key:
        return RedirectResponse(url="/", status_code=302)
    setup_html = STATIC_DIR / "setup.html"
    if not setup_html.exists():
        raise HTTPException(500, "setup.html missing from bundled assets")
    return FileResponse(setup_html)


@router.post("/api/setup/validate-key", response_model=ValidateKeyResponse)
async def validate_key(body: ValidateKeyBody, request: Request) -> ValidateKeyResponse:
    cfg = request.app.state.config
    base = cfg.api_base_url or DEFAULT_API_BASE_URL
    ok, message = await _ping_nara(body.api_key, base)
    return ValidateKeyResponse(valid=ok, message=message)


@router.post("/api/setup/complete", response_model=CompleteResponse)
async def complete_setup(body: CompleteBody, request: Request) -> CompleteResponse:
    if not body.terms_acknowledged:
        raise HTTPException(400, "NARA terms must be acknowledged before continuing.")
    # Validate once more before persisting; first-run users may try to skip the button.
    cfg = request.app.state.config
    base = cfg.api_base_url or DEFAULT_API_BASE_URL
    ok, message = await _ping_nara(body.api_key, base)
    if not ok:
        raise HTTPException(422, message)

    output_dir = Path(body.output_dir).expanduser() if body.output_dir else cfg.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    used_keychain = _save_to_keychain(body.api_key)

    # Always persist TOML too — Keychain is for the .app's runtime resolution,
    # TOML keeps the CLI workflow working from the same machine.
    target = write_config(
        api_key="" if used_keychain else body.api_key,
        output_dir=output_dir,
        default_rate=cfg.default_rate,
        server_host=cfg.server_host,
        server_port=cfg.server_port,
        auto_open_browser=cfg.auto_open_browser,
        api_base_url=cfg.api_base_url or DEFAULT_API_BASE_URL,
        terms_acknowledged=True,
    )

    # Refresh the in-memory config so the rest of the running server sees the new key.
    request.app.state.config = replace(
        cfg,
        api_key=body.api_key,
        output_dir=output_dir,
        terms_acknowledged=True,
        config_path=target,
    )

    return CompleteResponse(saved_to=str(target), used_keychain=used_keychain)


# ----- middleware -----


def install_first_run_redirect(app: Any) -> None:
    """Redirect HTML navigations to ``/setup`` while the app has no API key.

    Scope is intentionally narrow: this only catches *browser* navigations
    (``Accept: text/html``). JSON traffic flows through to the route handlers,
    which keep their existing 503/401 semantics (search.py raises 503 with a
    "Run `actari init`" hint, /api/config still reports a masked-empty status).
    Tooling and tests therefore see the same behaviour as before this patch.
    """

    @app.middleware("http")
    async def _setup_redirect(request: Request, call_next):
        cfg = request.app.state.config
        if cfg.has_api_key:
            return await call_next(request)
        path = request.url.path
        accept = request.headers.get("accept", "")
        if "text/html" not in accept:
            return await call_next(request)
        # The wizard and its assets must always be reachable.
        if (
            path.startswith("/setup")
            or path.startswith("/api/setup/")
            or path.startswith("/static/")
        ):
            return await call_next(request)
        return RedirectResponse(url="/setup", status_code=302)
