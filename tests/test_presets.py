"""Tests for the curated preset bundle, loader, /api/presets, and CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from nara.cli import app as cli_app
from nara.config import Config
from nara.presets import DATA_FILE, PresetError, load_presets
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
    runner = CliRunner()
    result = runner.invoke(cli_app, ["presets"])
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
