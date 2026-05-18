"""Config routes: read masked config, patch non-secret fields, reveal folder."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response

from ...config import delete_keychain_key, user_config_dir, write_config
from ..models import ConfigDto, ConfigPatch, RevealResponse

router = APIRouter(prefix="/api/config", tags=["config"])


def _mask(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}…{key[-4:]}"


def _keychain_active() -> bool:
    """True iff this process actually uses macOS Keychain for the API key.

    Mirrors the logic in ``config._keychain_available`` without importing the
    private name. The Settings tab uses this to show the Keychain badge and
    enable the Reset-Key button.
    """
    import platform
    import sys

    if platform.system() != "Darwin":
        return False
    if not getattr(sys, "frozen", False) and "NARA_FORCE_KEYCHAIN" not in __import__("os").environ:
        return False
    try:
        import keyring  # noqa: F401

        return True
    except ImportError:
        return False


def _config_dto(cfg) -> ConfigDto:  # type: ignore[no-untyped-def]
    return ConfigDto(
        has_api_key=cfg.has_api_key,
        api_key_masked=_mask(cfg.api_key),
        api_base_url=cfg.api_base_url,
        default_rate=cfg.default_rate,
        output_dir=str(cfg.output_dir),
        server_host=cfg.server_host,
        server_port=cfg.server_port,
        auto_open_browser=cfg.auto_open_browser,
        terms_acknowledged=cfg.terms_acknowledged,
        acknowledged_at=cfg.acknowledged_at,
        config_path=str(cfg.config_path) if cfg.config_path else None,
        keychain_active=_keychain_active(),
    )


@router.get("", response_model=ConfigDto)
def get_config(request: Request) -> ConfigDto:
    return _config_dto(request.app.state.config)


@router.patch("", response_model=ConfigDto)
def patch_config(body: ConfigPatch, request: Request) -> ConfigDto:
    cfg = request.app.state.config
    if cfg.config_path is None:
        raise HTTPException(
            409,
            "no ~/.nara/config.toml to update — run `nara init` first.",
        )
    if not cfg.api_key:
        raise HTTPException(
            409,
            "config has no API key on disk; refusing to overwrite an "
            "incomplete config from the web UI.",
        )
    new_rate = body.default_rate if body.default_rate is not None else cfg.default_rate
    new_browser = (
        body.auto_open_browser if body.auto_open_browser is not None else cfg.auto_open_browser
    )
    write_config(
        api_key=cfg.api_key,
        output_dir=cfg.output_dir,
        default_rate=new_rate,
        server_host=cfg.server_host,
        server_port=cfg.server_port,
        auto_open_browser=new_browser,
        api_base_url=cfg.api_base_url,
        terms_acknowledged=cfg.terms_acknowledged,
        target=cfg.config_path,
    )
    new_cfg = replace(cfg, default_rate=new_rate, auto_open_browser=new_browser)
    request.app.state.config = new_cfg
    return _config_dto(new_cfg)


_PLATFORM_OPENERS = {
    "darwin": ["open"],
    "win32": ["explorer"],
}


def _opener_for_platform(platform: str) -> list[str] | None:
    if platform in _PLATFORM_OPENERS:
        return _PLATFORM_OPENERS[platform]
    if platform.startswith("linux"):
        return ["xdg-open"]
    return None


def _reveal(target: Path) -> str:
    """Cross-platform 'show in file manager' — returns the path that was opened."""
    target.mkdir(parents=True, exist_ok=True)
    opener = _opener_for_platform(sys.platform)
    if opener is None:
        raise HTTPException(501, f"don't know how to open a folder on platform={sys.platform!r}")
    try:
        subprocess.run([*opener, str(target)], check=False, timeout=5)
    except (OSError, subprocess.SubprocessError) as e:
        raise HTTPException(500, f"could not open folder: {e}") from e
    return str(target)


@router.post("/reveal", response_model=RevealResponse)
def reveal_config_dir(request: Request) -> RevealResponse:
    """Open the platform file-manager pointed at ``~/.nara``."""
    cfg = request.app.state.config
    target: Path = cfg.config_path.parent if cfg.config_path else user_config_dir()
    return RevealResponse(opened=_reveal(target))


@router.post("/reset-key", status_code=204)
def reset_api_key(request: Request) -> Response:
    """Wipe the API key — from Keychain when active, and from in-memory state.

    The TOML on disk is left alone; the user can still re-paste the key in the
    setup wizard which writes a fresh TOML. After this call the next HTML
    navigation will hit the first-run redirect and land on ``/setup``.
    """
    cfg = request.app.state.config
    delete_keychain_key()  # no-op when keychain isn't active; safe to call always
    request.app.state.config = replace(cfg, api_key=None)
    return Response(status_code=204)


@router.post("/reveal-output", response_model=RevealResponse)
def reveal_output_dir(request: Request) -> RevealResponse:
    """Open the file manager at the output dir. Prefers ``pdfs/`` if it exists."""
    cfg = request.app.state.config
    pdfs = cfg.output_dir / "pdfs"
    target: Path = pdfs if pdfs.exists() else cfg.output_dir
    return RevealResponse(opened=_reveal(target))
