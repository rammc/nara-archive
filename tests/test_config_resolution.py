"""Tests for the layered config resolver."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from nara import config as cfgmod


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Redirect ~/.nara to a temp dir and CWD to another temp dir."""
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.setenv("NARA_HOME", str(home))
    monkeypatch.chdir(cwd)
    # Make sure no real env key leaks in.
    monkeypatch.delenv("NARA_API_KEY", raising=False)
    monkeypatch.delenv("NARA_API_BASE_URL", raising=False)
    monkeypatch.delenv("NARA_DEFAULT_RATE", raising=False)
    return home, cwd


def _write_toml(home: Path, body: str) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    p = home / "config.toml"
    p.write_text(textwrap.dedent(body).strip() + "\n", encoding="utf-8")
    return p


def test_resolve_falls_back_to_defaults_when_nothing_set(isolated_home):
    home, cwd = isolated_home
    cfg = cfgmod.resolve_config(load_dotenv=False)
    assert cfg.api_key is None
    assert cfg.api_base_url == cfgmod.DEFAULT_API_BASE_URL
    assert cfg.default_rate == cfgmod.DEFAULT_RATE
    # No ./output present → fall through to ~/.nara/output
    assert cfg.output_dir == home / "output"
    assert cfg.has_api_key is False
    assert cfg.config_path is None


def test_toml_supplies_values_when_no_env(isolated_home):
    home, _ = isolated_home
    _write_toml(
        home,
        """
        [api]
        key = "from-toml"
        base_url = "https://example.test/api/"
        default_rate = 0.25

        [storage]
        output_dir = "/tmp/custom-out"

        [meta]
        nara_terms_acknowledged = true
        acknowledged_at = "2026-05-16T10:00:00Z"
    """,
    )
    cfg = cfgmod.resolve_config(load_dotenv=False)
    assert cfg.api_key == "from-toml"
    assert cfg.api_base_url == "https://example.test/api/"
    assert cfg.default_rate == 0.25
    # Resolve both sides — macOS symlinks /tmp → /private/tmp.
    assert cfg.output_dir == Path("/tmp/custom-out").expanduser().resolve()
    assert cfg.terms_acknowledged is True


def test_env_beats_toml(isolated_home, monkeypatch):
    home, _ = isolated_home
    _write_toml(
        home,
        """
        [api]
        key = "from-toml"
    """,
    )
    monkeypatch.setenv("NARA_API_KEY", "from-env")
    cfg = cfgmod.resolve_config(load_dotenv=False)
    assert cfg.api_key == "from-env"


def test_dotenv_beats_toml_when_loaded(isolated_home, monkeypatch):
    home, cwd = isolated_home
    _write_toml(
        home,
        """
        [api]
        key = "from-toml"
    """,
    )
    (cwd / ".env").write_text("NARA_API_KEY=from-dotenv\n", encoding="utf-8")
    # Ensure no real env var pre-empts the .env load.
    monkeypatch.delenv("NARA_API_KEY", raising=False)
    cfg = cfgmod.resolve_config(load_dotenv=True)
    assert cfg.api_key == "from-dotenv"


def test_existing_local_output_dir_wins_over_home(isolated_home):
    home, cwd = isolated_home
    (cwd / "output").mkdir()
    cfg = cfgmod.resolve_config(load_dotenv=False)
    assert cfg.output_dir == (cwd / "output").resolve()


def test_write_and_read_round_trip(isolated_home):
    home, _ = isolated_home
    target = home / "config.toml"
    written = cfgmod.write_config(
        api_key="abc123",
        output_dir=home / "output",
        default_rate=0.7,
        target=target,
    )
    assert written == target
    cfg = cfgmod.resolve_config(load_dotenv=False)
    assert cfg.api_key == "abc123"
    assert cfg.default_rate == 0.7
    assert cfg.terms_acknowledged is True
    assert cfg.acknowledged_at and cfg.acknowledged_at.endswith("Z")


def test_detect_legacy_env_only_when_no_toml(isolated_home):
    home, cwd = isolated_home
    (cwd / ".env").write_text("NARA_API_KEY=foo\n", encoding="utf-8")
    assert cfgmod.detect_legacy_env() == cwd / ".env"

    cfgmod.write_config(api_key="x", output_dir=home / "out", target=home / "config.toml")
    assert cfgmod.detect_legacy_env() is None
