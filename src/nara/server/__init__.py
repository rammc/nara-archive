"""FastAPI server for the nara web UI. Mount via ``nara.server.app.create_app``."""
from .app import create_app

__all__ = ["create_app"]
