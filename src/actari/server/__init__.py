"""FastAPI server for the actari web UI. Mount via ``actari.server.app.create_app``."""

from .app import create_app

__all__ = ["create_app"]
