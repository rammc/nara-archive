"""FastAPI app factory for the actari web UI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import Config, resolve_config
from ..jobs import JobManager
from ..updater import schedule_startup_check
from .. import __version__
from .routes.config import router as config_router
from .routes.jobs import router as jobs_router
from .routes.library import router as library_router
from .routes.presets import router as presets_router
from .routes.search import router as search_router

# Module is named ``firstrun`` (not ``setup``) so PyInstaller's analyser
# doesn't treat it as a legacy packaging script and silently drop it from
# the bundle — that exact regression cost us the v0.9.0-rc5 .app launch.
# Route paths (``/setup``, ``/api/setup/*``) are unchanged.
from .routes.firstrun import install_first_run_redirect, router as firstrun_router
from .routes.updates import router as updates_router

STATIC_DIR = Path(__file__).parent / "static"


def create_app(config: Config | None = None) -> FastAPI:
    """Build the FastAPI application. ``config`` is injectable for tests."""
    cfg = config or resolve_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager = JobManager(config=cfg)
        await manager.startup()
        app.state.jobs = manager
        schedule_startup_check(app, current_version=__version__, enabled=cfg.check_for_updates)
        try:
            yield
        finally:
            await manager.shutdown()

    app = FastAPI(
        title="actari",
        version=__version__,
        docs_url=None,  # no /docs in the user-facing UI
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    # Stash config on app state so route handlers can grab it without
    # re-resolving — keeps the env > toml precedence stable for the run.
    app.state.config = cfg

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # PDFs are served from the user's output dir. StaticFiles handles HTTP
    # Range requests natively (PDF viewers fetch pages on demand) and uses
    # ``os.path.commonpath`` to block path traversal beneath ``directory``.
    pdfs_dir = cfg.output_dir / "pdfs"
    pdfs_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/pdfs", StaticFiles(directory=str(pdfs_dir)), name="pdfs")

    app.include_router(firstrun_router)
    install_first_run_redirect(app)
    app.include_router(search_router)
    app.include_router(jobs_router)
    app.include_router(library_router)
    app.include_router(config_router)
    app.include_router(presets_router)
    app.include_router(updates_router)

    @app.get("/api/health", response_class=JSONResponse)
    def health(request: Request) -> dict[str, Any]:
        # Read from app.state so the setup wizard's POST /api/setup/complete
        # is visible to /api/health on the same running server.
        live = request.app.state.config
        return {
            "status": "ok",
            "version": __version__,
            "has_api_key": live.has_api_key,
            "terms_acknowledged": live.terms_acknowledged,
            "output_dir": str(live.output_dir),
        }

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app
