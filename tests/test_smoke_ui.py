"""Server smoke tests: routes resolve, SPA shell renders, no API key required."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nara.config import Config


def _config(tmp_path) -> Config:
    return Config(
        api_key="test-key",
        api_base_url="https://example.test/api/v2/",
        default_rate=0.5,
        output_dir=tmp_path,
        server_host="127.0.0.1",
        server_port=8765,
        auto_open_browser=False,
        config_path=None,
        terms_acknowledged=True,
        acknowledged_at="2026-05-16T00:00:00Z",
    )


@pytest.fixture
def client(tmp_path):
    from nara.server import create_app

    app = create_app(_config(tmp_path))
    return TestClient(app)


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert body["has_api_key"] is True
    assert body["terms_acknowledged"] is True


def test_health_reflects_missing_key(tmp_path):
    cfg = _config(tmp_path)
    cfg = Config(**{**cfg.__dict__, "api_key": None})
    from nara.server import create_app

    c = TestClient(create_app(cfg))
    body = c.get("/api/health").json()
    assert body["has_api_key"] is False


def test_index_serves_html_shell(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    html = r.text
    # All four tab anchors must be in the shell.
    for anchor in ('id="discovery"', 'id="downloads"', 'id="library"', 'id="settings"'):
        assert anchor in html, f"missing tab anchor: {anchor}"
    assert 'href="#discovery"' in html
    assert "/static/app.js" in html
    assert "/static/app.css" in html


def test_static_assets_are_served(client):
    css = client.get("/static/app.css")
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")

    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert "TABS" in js.text  # smoke: our routing constant ships
