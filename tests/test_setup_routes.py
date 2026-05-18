"""Tests for the first-run setup wizard: GET /setup, validate, complete, middleware."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from nara.config import Config
from nara.server import create_app


def _config(tmp_path: Path, *, api_key: str | None = None) -> Config:
    return Config(
        api_key=api_key,
        api_base_url="https://example.test/api/v2/",
        default_rate=0.5,
        output_dir=tmp_path,
        server_host="127.0.0.1",
        server_port=8765,
        auto_open_browser=False,
        config_path=tmp_path / "config.toml",
        terms_acknowledged=False,
        acknowledged_at=None,
    )


def _stub_async_client_factory(*, status_code: int):
    """Return a fake httpx.AsyncClient class that always replies with ``status_code``."""

    class _FakeResp:
        def __init__(self, code: int):
            self.status_code = code
            self.headers = {"content-type": "application/json"}

        def json(self):
            return {"body": {"hits": {"hits": [], "total": {"value": 0}}}}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None, headers=None):
            return _FakeResp(status_code)

    return _FakeClient


def test_get_setup_serves_html_when_unconfigured(tmp_path):
    app = create_app(_config(tmp_path, api_key=None))
    c = TestClient(app)
    r = c.get("/setup", headers={"accept": "text/html"})
    assert r.status_code == 200, r.text
    assert "<html" in r.text.lower()
    assert "nara archive" in r.text.lower()


def test_get_setup_redirects_when_already_configured(tmp_path):
    app = create_app(_config(tmp_path, api_key="kYz0123456789012345678901234567890123vC9"))
    c = TestClient(app, follow_redirects=False)
    r = c.get("/setup", headers={"accept": "text/html"})
    assert r.status_code == 302
    assert r.headers["location"] == "/"


def test_root_redirects_to_setup_when_unconfigured(tmp_path):
    """Middleware must intercept HTML navigations and send them to /setup."""
    app = create_app(_config(tmp_path, api_key=None))
    c = TestClient(app, follow_redirects=False)
    r = c.get("/", headers={"accept": "text/html"})
    assert r.status_code == 302
    assert r.headers["location"] == "/setup"


def test_static_assets_pass_through_during_setup(tmp_path):
    """Without this exception, the wizard couldn't load its own CSS / JS."""
    app = create_app(_config(tmp_path, api_key=None))
    c = TestClient(app, follow_redirects=False)
    r = c.get("/static/app.css")
    # Either the file exists (200) or it's missing in the test layout (404),
    # but in neither case should we get a 302 to /setup.
    assert r.status_code in (200, 404)


def test_api_traffic_during_setup_is_not_redirected(tmp_path):
    """JSON clients bypass the setup-redirect middleware so existing 503/401
    semantics from the route handlers survive (e.g. /api/search → 503 with
    'Run `nara init`' hint)."""
    app = create_app(_config(tmp_path, api_key=None))
    c = TestClient(app, follow_redirects=False)
    r = c.get("/api/library", headers={"accept": "application/json"})
    # /api/library doesn't require a NARA key — it just lists local manifests
    # and should return normally even without configuration.
    assert r.status_code == 200, r.text
    assert r.json() == {"manifests": []}


def test_health_endpoint_always_accessible(tmp_path):
    app = create_app(_config(tmp_path, api_key=None))
    c = TestClient(app)
    r = c.get("/api/health")
    assert r.status_code == 200
    assert r.json()["has_api_key"] is False


def test_validate_key_happy_path(tmp_path, monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _stub_async_client_factory(status_code=200))
    app = create_app(_config(tmp_path, api_key=None))
    c = TestClient(app)
    r = c.post("/api/setup/validate-key", json={"api_key": "kYz0_abc_xvC9_test_key_value"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True


def test_validate_key_rejects_on_401(tmp_path, monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _stub_async_client_factory(status_code=401))
    app = create_app(_config(tmp_path, api_key=None))
    c = TestClient(app)
    r = c.post("/api/setup/validate-key", json={"api_key": "this_is_a_bogus_key_value"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is False
    assert "401" in body["message"] or "rejected" in body["message"].lower()


def test_complete_requires_terms_acknowledged(tmp_path, monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _stub_async_client_factory(status_code=200))
    app = create_app(_config(tmp_path, api_key=None))
    c = TestClient(app)
    r = c.post(
        "/api/setup/complete",
        json={"api_key": "kYz0_some_validated_test_key", "terms_acknowledged": False},
    )
    assert r.status_code == 400
    assert "terms" in r.json()["detail"].lower()


def test_complete_persists_and_swaps_app_state(tmp_path, monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _stub_async_client_factory(status_code=200))
    # Force Keychain-write to be a no-op so we exercise the TOML-only path.
    from nara.server.routes import setup as setup_mod

    monkeypatch.setattr(setup_mod, "_save_to_keychain", lambda _key: False)

    cfg = _config(tmp_path, api_key=None)
    # Use a non-default config_path so write_config doesn't touch the user's real home.
    cfg = replace(cfg, config_path=tmp_path / "config.toml")
    app = create_app(cfg)
    c = TestClient(app)
    r = c.post(
        "/api/setup/complete",
        json={
            "api_key": "kYz0_validated_test_key_with_enough_chars",
            "output_dir": str(tmp_path / "custom-out"),
            "terms_acknowledged": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["used_keychain"] is False
    # In-memory swap landed: the app should now consider itself configured.
    h = c.get("/api/health").json()
    assert h["has_api_key"] is True
    assert h["terms_acknowledged"] is True


def test_complete_revalidates_key_against_nara(tmp_path, monkeypatch):
    """A user could try to POST /api/setup/complete without clicking Validate first.
    The handler must re-check the key and 422 if NARA rejects it."""
    monkeypatch.setattr(httpx, "AsyncClient", _stub_async_client_factory(status_code=403))
    app = create_app(_config(tmp_path, api_key=None))
    c = TestClient(app)
    r = c.post(
        "/api/setup/complete",
        json={
            "api_key": "kYz0_bogus_unvalidated_key_xxx",
            "terms_acknowledged": True,
        },
    )
    assert r.status_code == 422
    assert "rejected" in r.json()["detail"].lower() or "401" in r.json()["detail"]


@pytest.fixture(autouse=True)
def _isolate_nara_home(tmp_path, monkeypatch):
    """Stop tests writing into ~/.nara when complete() goes through the TOML branch."""
    monkeypatch.setenv("NARA_HOME", str(tmp_path / "nara-home"))
