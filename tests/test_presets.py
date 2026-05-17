"""Tests for the curated preset bundle, loader, /api/presets, and CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from nara.cli import app as cli_app
from nara.config import Config
from nara.presets import (
    DATA_FILE,
    PresetError,
    load_all_presets,
    load_presets,
    user_presets_path,
)
from nara.server import create_app


def _config(tmp_path: Path) -> Config:
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
        acknowledged_at="2026-05-16T00:00:00Z",
    )


# --- bundled data ---


def test_bundled_presets_file_loads_and_validates():
    """The shipped JSON loads, validates, and has at least the IG-Farben T83 anchor."""
    data = load_presets()
    assert len(data) >= 5
    by_id = {p["id"]: p for p in data}
    assert "ig-farben-t83" in by_id, "missing the canonical T83 entry"
    t83 = by_id["ig-farben-t83"]
    assert t83["direct_naid"] == "7840517"
    assert t83["search"]["q"]
    assert "242" in (t83["search"].get("record_group") or [])


def test_bundled_presets_have_unique_ids_and_required_fields():
    data = load_presets()
    ids = [p["id"] for p in data]
    assert len(set(ids)) == len(ids), "duplicate preset ids"
    for p in data:
        assert p["title"] and p["description"] and p["category"]
        # Either search.q must be present, or direct_naid — validator enforces, but double-check.
        assert (p.get("search") and p["search"]["q"]) or p.get("direct_naid")


# --- loader edge cases ---


def test_loader_rejects_unknown_search_key(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "presets": [
                    {
                        "id": "x",
                        "title": "x",
                        "description": "x",
                        "category": "x",
                        "search": {"q": "a", "bogus_key": "v"},
                    }
                ]
            }
        )
    )
    with pytest.raises(PresetError, match="unknown search key"):
        load_presets(path=bad)


def test_loader_rejects_duplicate_id(tmp_path):
    bad = tmp_path / "dup.json"
    p = {
        "id": "same",
        "title": "x",
        "description": "x",
        "category": "x",
        "search": {"q": "a"},
    }
    bad.write_text(json.dumps({"presets": [p, p]}))
    with pytest.raises(PresetError, match="duplicate id"):
        load_presets(path=bad)


def test_loader_requires_search_or_direct_naid(tmp_path):
    bad = tmp_path / "empty.json"
    bad.write_text(
        json.dumps(
            {
                "presets": [
                    {"id": "x", "title": "x", "description": "x", "category": "x"},
                ]
            }
        )
    )
    with pytest.raises(PresetError, match="search or direct_naid"):
        load_presets(path=bad)


# --- route ---


def test_api_presets_returns_validated_list(tmp_path):
    app = create_app(_config(tmp_path))
    c = TestClient(app)
    r = c.get("/api/presets")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "presets" in body
    by_id = {p["id"]: p for p in body["presets"]}
    assert "ig-farben-t83" in by_id


# --- CLI ---


def test_cli_presets_table_lists_entries():
    # Force a wide terminal so Rich doesn't truncate the id column to "ig-far…".
    runner = CliRunner(env={"COLUMNS": "200"})
    result = runner.invoke(cli_app, ["presets"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "ig-farben-t83" in result.output


def test_cli_presets_json_output_parses():
    runner = CliRunner()
    result = runner.invoke(cli_app, ["presets", "--format", "json"])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert isinstance(parsed["presets"], list)
    assert any(p["id"] == "ig-farben-t83" for p in parsed["presets"])


def test_data_file_resides_inside_package():
    """Sanity: the shipped JSON sits at src/nara/data/presets.json (gets packaged)."""
    assert DATA_FILE.name == "presets.json"
    assert DATA_FILE.parent.name == "data"
    assert DATA_FILE.parent.parent.name == "nara"


# --- user-extensible presets (roadmap #3) ---


def test_user_presets_path_uses_nara_home(monkeypatch, tmp_path):
    """user_presets_path() honours NARA_HOME — same convention as user_config_dir."""
    monkeypatch.setenv("NARA_HOME", str(tmp_path))
    assert user_presets_path() == tmp_path / "presets.json"


def test_load_all_returns_bundled_when_no_user_file(tmp_path):
    """No user file → bundled-only, every entry tagged source=bundled."""
    missing = tmp_path / "presets.json"  # does not exist
    data = load_all_presets(user_path=missing)
    assert len(data) >= 5
    assert all(p["source"] == "bundled" for p in data)


def test_user_preset_with_new_id_is_appended(tmp_path):
    user_file = tmp_path / "presets.json"
    user_file.write_text(
        json.dumps(
            {
                "presets": [
                    {
                        "id": "my-custom-search",
                        "title": "My personal IG search",
                        "description": "Local override for testing.",
                        "category": "My research",
                        "search": {"q": "Bayer Leverkusen"},
                    }
                ]
            }
        )
    )
    data = load_all_presets(user_path=user_file)
    by_id = {p["id"]: p for p in data}
    assert "my-custom-search" in by_id
    assert by_id["my-custom-search"]["source"] == "user"
    # Bundled ones still present and still marked bundled.
    assert by_id["ig-farben-t83"]["source"] == "bundled"
    # User-only additions go to the end.
    assert data[-1]["id"] == "my-custom-search"


def test_user_preset_overrides_bundled_by_id(tmp_path):
    """A user entry with the same id replaces the bundled one in-place."""
    user_file = tmp_path / "presets.json"
    user_file.write_text(
        json.dumps(
            {
                "presets": [
                    {
                        "id": "ig-farben-t83",
                        "title": "My override of T83",
                        "description": "Personal description.",
                        "category": "Custom",
                        "search": {"q": "T83 customized"},
                        "direct_naid": "7840517",
                    }
                ]
            }
        )
    )
    data = load_all_presets(user_path=user_file)
    by_id = {p["id"]: p for p in data}
    overridden = by_id["ig-farben-t83"]
    assert overridden["source"] == "user"
    assert overridden["title"] == "My override of T83"
    # Order preserved: it's still at the position the bundled one was at.
    bundled_only = load_presets()
    bundled_position = next(i for i, p in enumerate(bundled_only) if p["id"] == "ig-farben-t83")
    assert data[bundled_position]["id"] == "ig-farben-t83"


def test_invalid_user_file_raises(tmp_path):
    bad = tmp_path / "presets.json"
    bad.write_text(json.dumps({"presets": [{"id": "nope"}]}))  # missing fields
    with pytest.raises(PresetError):
        load_all_presets(user_path=bad)


def test_api_presets_falls_back_when_user_file_invalid(tmp_path, monkeypatch):
    """A broken ~/.nara/presets.json must not blank the UI — bundled stays available."""
    monkeypatch.setenv("NARA_HOME", str(tmp_path))
    (tmp_path / "presets.json").write_text("{not even json")
    app = create_app(_config(tmp_path))
    c = TestClient(app)
    r = c.get("/api/presets")
    assert r.status_code == 200, r.text
    body = r.json()
    by_id = {p["id"]: p for p in body["presets"]}
    assert "ig-farben-t83" in by_id, "should fall back to bundled when user file rejected"
    assert all(p["source"] == "bundled" for p in body["presets"])


def test_cli_presets_path_prints_user_path(monkeypatch, tmp_path):
    monkeypatch.setenv("NARA_HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli_app, ["presets", "--path"])
    assert result.exit_code == 0, result.output
    assert str(tmp_path / "presets.json") in result.output


def test_cli_presets_bundled_only_skips_user_file(monkeypatch, tmp_path):
    monkeypatch.setenv("NARA_HOME", str(tmp_path))
    (tmp_path / "presets.json").write_text(
        json.dumps(
            {
                "presets": [
                    {
                        "id": "my-thing",
                        "title": "x",
                        "description": "x",
                        "category": "x",
                        "search": {"q": "a"},
                    }
                ]
            }
        )
    )
    runner = CliRunner()
    result = runner.invoke(cli_app, ["presets", "--bundled-only", "--format", "json"])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    ids = [p["id"] for p in parsed["presets"]]
    assert "my-thing" not in ids
    assert "ig-farben-t83" in ids
