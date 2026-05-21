"""Tests for the GitHub-release update checker."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from actari.config import Config
from actari.server import create_app
from actari.updater import UpdateInfo, check_for_update, is_newer


def _config(tmp_path: Path, *, check_for_updates: bool = True) -> Config:
    return Config(
        api_key="fake-key",
        api_base_url="https://example.test/api/v2/",
        default_rate=0.5,
        output_dir=tmp_path,
        server_host="127.0.0.1",
        server_port=8765,
        auto_open_browser=False,
        config_path=None,
        terms_acknowledged=True,
        acknowledged_at="2026-05-18T00:00:00Z",
        check_for_updates=check_for_updates,
    )


# --- version comparison ---


@pytest.mark.parametrize(
    "latest,current,expected",
    [
        ("v0.4.0", "0.3.0", True),
        ("0.3.1", "0.3.0", True),
        ("0.3.0", "0.3.0", False),
        ("0.2.9", "0.3.0", False),
        ("v0.3.0", "v0.3.0", False),
        ("1.0.0", "0.99.99", True),
    ],
)
def test_is_newer_semver_cases(latest, current, expected):
    assert is_newer(latest, current) is expected


def test_is_newer_handles_empty_strings():
    assert is_newer("", "0.3.0") is False
    assert is_newer("0.3.0", "") is False


# --- check_for_update with mocked HTTP ---


class _FakeAsyncClient:
    def __init__(
        self, *, status: int, json: dict | None = None, raise_on_get: Exception | None = None
    ):
        self._status = status
        self._json = json or {}
        self._raise = raise_on_get

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, url, headers=None):
        if self._raise is not None:
            raise self._raise

        class _R:
            def __init__(self, status, body):
                self.status_code = status
                self._body = body

            def json(self):
                return self._body

        return _R(self._status, self._json)

    async def aclose(self):
        return None


def test_check_for_update_finds_newer_release(monkeypatch):
    client = _FakeAsyncClient(
        status=200,
        json={"tag_name": "v0.5.0", "html_url": "https://example.test/release/0.5.0"},
    )
    info = asyncio.run(check_for_update("0.3.0", client=client))
    assert info.latest_version == "0.5.0"
    assert info.release_url == "https://example.test/release/0.5.0"
    assert info.available is True
    assert info.error is None


def test_check_for_update_when_already_latest(monkeypatch):
    client = _FakeAsyncClient(status=200, json={"tag_name": "v0.3.0", "html_url": "x"})
    info = asyncio.run(check_for_update("0.3.0", client=client))
    assert info.available is False
    assert info.latest_version == "0.3.0"


def test_check_for_update_404_treated_as_no_release(monkeypatch):
    """A new repo without any published releases shouldn't be reported as an error."""
    client = _FakeAsyncClient(status=404)
    info = asyncio.run(check_for_update("0.1.0", client=client))
    assert info.error is None
    assert info.available is False
    assert info.latest_version is None


def test_check_for_update_network_error_returns_error_field(monkeypatch):
    client = _FakeAsyncClient(status=200, raise_on_get=httpx.ConnectError("DNS fail"))
    info = asyncio.run(check_for_update("0.1.0", client=client))
    assert info.error and "DNS fail" in info.error
    assert info.available is False


# --- route + lifespan ---


def test_api_updates_returns_default_when_disabled(tmp_path):
    """check_for_updates=False → endpoint still returns an UpdateInfo, just no check fired."""
    app = create_app(_config(tmp_path, check_for_updates=False))
    with TestClient(app) as c:
        r = c.get("/api/updates")
        assert r.status_code == 200
        body = r.json()
        assert body["available"] is False
        assert body["current_version"]  # __version__


def test_api_updates_reflects_startup_check(tmp_path, monkeypatch):
    """Force the lifespan check to set a known UpdateInfo and verify the route echoes it."""
    import actari.server.app as app_module

    async def fake_check(current_version, **_kwargs):
        return UpdateInfo(
            current_version=current_version,
            latest_version="9.9.9",
            release_url="https://example.test/release/9.9.9",
            available=True,
        )

    monkeypatch.setattr("actari.updater.check_for_update", fake_check)
    # schedule_startup_check uses the SAME module-level name, so monkeypatch
    # affects the scheduled task too.
    _ = app_module  # keep import for clarity

    app = create_app(_config(tmp_path, check_for_updates=True))
    with TestClient(app) as c:
        # Give the background task a tiny window to flip the state.
        for _ in range(10):
            body = c.get("/api/updates").json()
            if body.get("available"):
                break
            import time as _t

            _t.sleep(0.05)
        assert body["available"] is True
        assert body["latest_version"] == "9.9.9"
        assert body["release_url"].endswith("9.9.9")
