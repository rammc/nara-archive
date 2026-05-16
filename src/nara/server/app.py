"""FastAPI app factory for the nara web UI."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import Config, resolve_config
from .. import __version__

STATIC_DIR = Path(__file__).parent / "static"


def create_app(config: Config | None = None) -> FastAPI:
    """Build the FastAPI application. ``config`` is injectable for tests."""
    cfg = config or resolve_config()
    app = FastAPI(
        title="nara-archive",
        version=__version__,
        docs_url=None,           # no /docs in the user-facing UI
        redoc_url=None,
        openapi_url=None,
    )

    # Stash config on app state so route handlers can grab it without
    # re-resolving — keeps the env > toml precedence stable for the run.
    app.state.config = cfg

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/api/health", response_class=JSONResponse)
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "has_api_key": cfg.has_api_key,
            "terms_acknowledged": cfg.terms_acknowledged,
            "output_dir": str(cfg.output_dir),
        }

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app
