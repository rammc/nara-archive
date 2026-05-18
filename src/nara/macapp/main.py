"""Menubar entry point for the bundled macOS ``.app``.

Lifecycle:

1. Cocoa runs the rumps event loop on the *main* thread (required by AppKit).
2. ``Server.run()`` from uvicorn runs in a background thread on its own
   asyncio event loop — uvicorn handles that loop internally; we never
   create one on the main thread.
3. Quit triggers ``server.should_exit = True``; uvicorn closes connections,
   shuts the loop down, and the background thread exits within a second or two.

Designed to be both PyInstaller-bundled (``sys.frozen`` true) and runnable
straight from a venv via ``python -m nara.macapp.main`` for development.
"""

from __future__ import annotations

import logging
import platform
import threading
import time
import webbrowser
from typing import Any

log = logging.getLogger("nara.macapp")


def _require_darwin() -> None:
    if platform.system() != "Darwin":
        raise SystemExit("nara.macapp is macOS-only. Use `nara serve` on Linux / Windows.")


def _is_first_run(cfg: Any) -> bool:
    """Without an API key configured, send the user to /setup."""
    return not bool(cfg.api_key)


class _ServerThread(threading.Thread):
    """Run uvicorn in a background thread and expose a graceful-shutdown hook."""

    def __init__(self, app, *, host: str, port: int):
        super().__init__(daemon=True, name="nara-uvicorn")
        import uvicorn  # local import — keeps startup deferred under PyInstaller

        self._uv_config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(self._uv_config)

    def run(self) -> None:
        try:
            self._server.run()
        except Exception:  # noqa: BLE001 — keep the menubar alive on uvicorn crash
            log.exception("uvicorn server crashed")

    def shutdown(self, *, timeout: float = 5.0) -> None:
        self._server.should_exit = True
        self.join(timeout=timeout)


def _build_app():
    """Import-time work deferred so non-darwin systems can still import this module."""
    from ..config import resolve_config
    from ..server import create_app

    cfg = resolve_config()
    return create_app(cfg), cfg


def main() -> None:
    """PyInstaller console_scripts entry point: ``nara-archive-app``."""
    _require_darwin()
    logging.basicConfig(level=logging.INFO)

    app, cfg = _build_app()
    host = cfg.server_host
    port = cfg.server_port

    # Import rumps last so a missing PyObjC reports clearly instead of poisoning
    # earlier imports.
    try:
        import rumps  # type: ignore[import-not-found]  # noqa: F401 — probe that rumps imports
    except ImportError as e:
        raise SystemExit(
            "rumps + PyObjC are required for the menubar app. Install with "
            "`pip install nara-archive[mac]` or run `nara serve` instead."
        ) from e

    server = _ServerThread(app, host=host, port=port)
    server.start()
    # Wait briefly for the listener so the first webbrowser.open() lands on a live socket.
    _wait_for_port(host, port, timeout=5.0)

    landing = f"http://{host}:{port}/{'setup' if _is_first_run(cfg) else ''}"

    menubar_app = _NaraMenubarApp(server=server, landing_url=landing, version=_version())
    # Open the browser once on launch — users expect the app to "do something".
    try:
        webbrowser.open(landing, new=2)
    except Exception:  # noqa: BLE001
        log.warning("could not auto-open browser; user can use the menu")
    menubar_app.run()


def _wait_for_port(host: str, port: int, *, timeout: float) -> None:
    import socket

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            try:
                s.connect((host, port))
                return
            except OSError:
                time.sleep(0.1)


def _version() -> str:
    try:
        from .. import __version__

        return __version__
    except Exception:  # noqa: BLE001
        return "unknown"


def _build_menubar_class():
    """Build the rumps.App subclass lazily so module import doesn't pull rumps."""
    import rumps  # type: ignore[import-not-found]

    class NaraMenubarApp(rumps.App):
        def __init__(self, *, server: _ServerThread, landing_url: str, version: str):
            super().__init__(
                name="nara",
                title="NARA",
                quit_button=None,  # custom Quit so we can shut uvicorn down cleanly
            )
            self._server = server
            self._landing_url = landing_url
            self._version = version
            self.menu = [
                rumps.MenuItem("Open in Browser", callback=self._open_browser),
                rumps.MenuItem("Show Status", callback=self._show_status),
                None,
                rumps.MenuItem("Start at Login", callback=self._toggle_login_item),
                None,
                rumps.MenuItem("Quit", callback=self._quit),
            ]

        def _open_browser(self, _sender):
            webbrowser.open(self._landing_url, new=2)

        def _show_status(self, _sender):
            rumps.alert(
                title="NARA Archive",
                message=(
                    f"Version {self._version}\n"
                    f"Local server: {self._landing_url}\n\n"
                    "Logs in ~/.nara/output/run.log"
                ),
                ok="OK",
            )

        def _toggle_login_item(self, sender):
            # Stub for now — real LaunchAgent wiring is a follow-up. Toggling
            # the menu mark gives the right affordance to the user.
            sender.state = not sender.state
            rumps.notification(
                title="NARA Archive",
                subtitle="Start-at-Login (preview)",
                message="This setting is not yet persisted; will land in a future build.",
            )

        def _quit(self, _sender):
            self._server.shutdown()
            rumps.quit_application()

    return NaraMenubarApp


def _NaraMenubarApp(**kwargs):  # type: ignore[no-untyped-def]
    """Tiny indirection so main() reads naturally without exposing the lazy class."""
    return _build_menubar_class()(**kwargs)


if __name__ == "__main__":
    main()
