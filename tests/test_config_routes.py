"""Tests for /api/config GET / PATCH and the reveal-folder endpoint."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from nara.config import Config, write_config
from nara.server import create_app


def _config(tmp_path: Path, *, persist: bool = False) -> Config:
    cfg_path = None
    if persist:
        cfg_path = tmp_path / "config.toml"
        write_config(
            api_key="kYz0123456789012345678901234567890123vC9",
            output_dir=tmp_path / "out",
            default_rate=0.5,
            target=cfg_path,
        )
    return Config(
        api_key="kYz0123456789012345678901234567890123vC9",
        api_base_url="https://example.test/api/v2/",
        default_rate=0.5,
        output_dir=tmp_path / "out",
        server_host="127.0.0.1",
        server_port=8765,
        auto_open_browser=True,
        config_path=cfg_path,
        terms_acknowledged=True,
        acknowledged_at="2026-05-16T00:00:00Z",
    )


def test_get_config_masks_api_key(tmp_path):
    app = create_app(_config(tmp_path))
    c = TestClient(app)
    body = c.get("/api/config").json()
    assert body["has_api_key"] is True
    masked = body["api_key_masked"]
    assert masked.startswith("kYz0") and masked.endswith("3vC9")
    assert "…" in masked
    # Real key value must not be in the body.
    assert "kYz0123456789012345678901234567890123vC9" not in str(body)


def test_get_config_handles_missing_key(tmp_path):
    cfg = _config(tmp_path)
    cfg = Config(**{**cfg.__dict__, "api_key": None})
    app = create_app(cfg)
    c = TestClient(app)
    body = c.get("/api/config").json()
    assert body["has_api_key"] is False
    assert body["api_key_masked"] is None


def test_patch_refuses_without_config_path(tmp_path):
    """No TOML on disk → don't try to update."""
    app = create_app(_config(tmp_path))  # config_path = None
    c = TestClient(app)
    r = c.patch("/api/config", json={"default_rate": 0.25})
    assert r.status_code == 409


def test_patch_updates_rate_and_persists(tmp_path):
    app = create_app(_config(tmp_path, persist=True))
    c = TestClient(app)
    r = c.patch("/api/config", json={"default_rate": 1.5, "auto_open_browser": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["default_rate"] == 1.5
    assert body["auto_open_browser"] is False

    # Subsequent GET reflects the change.
    body2 = c.get("/api/config").json()
    assert body2["default_rate"] == 1.5
    assert body2["auto_open_browser"] is False

    # On-disk TOML reflects it too.
    toml = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert "default_rate = 1.5" in toml
    assert "auto_open_browser = false" in toml


def test_patch_rejects_invalid_rate(tmp_path):
    app = create_app(_config(tmp_path, persist=True))
    c = TestClient(app)
    r = c.patch("/api/config", json={"default_rate": 0})
    assert r.status_code == 422


def test_reveal_invokes_platform_opener(tmp_path, monkeypatch):
    calls = []

    class FakeResult:
        returncode = 0

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("sys.platform", "darwin")

    app = create_app(_config(tmp_path, persist=True))
    c = TestClient(app)
    r = c.post("/api/config/reveal")
    assert r.status_code == 200, r.text
    assert r.json()["opened"].endswith("nara") or "config.toml" not in r.json()["opened"]
    assert len(calls) == 1
    assert calls[0][0] == "open"
