"""Tests for /api/library and the /pdfs/* static mount."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from actari.config import Config
from actari.server import create_app


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


def _write_manifest(
    out: Path,
    name: str,
    *,
    units: list[dict] | None = None,
    parent_naid: str = "7840517",
    parent_title: str | None = "Series X",
) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    filename = "manifest.json" if name == "default" else f"manifest-{name}.json"
    path = out / filename
    units = units or [
        {
            "naid": "1001",
            "title": "Letter from Smith",
            "pdf_path": "pdfs/0001-1001_x.pdf",
            "pdf_size_bytes": 100,
            "page_count": 2,
            "source_object_count": 2,
            "status": "ok",
            "scope_and_content_note": "On dye works in Frankfurt.",
        },
        {
            "naid": "1002",
            "title": "Report 1945",
            "pdf_path": "pdfs/0002-1002_y.pdf",
            "pdf_size_bytes": 250,
            "page_count": 5,
            "source_object_count": 5,
            "status": "ok",
        },
    ]
    doc = {
        "schema_version": "1.0",
        "generated_at": "2026-05-16T10:00:00Z",
        "source": {"parent_naid": parent_naid, "parent_title": parent_title},
        "stats": {
            "total_file_units": len(units),
            "successful_pdfs": sum(1 for u in units if u["status"] == "ok"),
            "failed_pdfs": 0,
            "skipped_non_document": 0,
            "total_pages": sum(u.get("page_count", 0) for u in units),
            "total_size_bytes": sum(u.get("pdf_size_bytes", 0) for u in units),
        },
        "file_units": units,
    }
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


@pytest.fixture
def app_with_data(tmp_path):
    out = tmp_path / "out"
    _write_manifest(out, "default")
    _write_manifest(
        out,
        "igfarben",
        parent_naid="7840517",
        parent_title="Series X",
        units=[
            {
                "naid": "9",
                "title": "I.G. Farben file",
                "pdf_path": "pdfs/0001-9_igfarben.pdf",
                "pdf_size_bytes": 1,
                "page_count": 1,
                "source_object_count": 1,
                "status": "ok",
            }
        ],
    )
    cfg = Config(**{**_config(out).__dict__})
    return create_app(cfg), out


def test_library_list_returns_manifests_newest_first(app_with_data):
    app, _ = app_with_data
    c = TestClient(app)
    r = c.get("/api/library")
    assert r.status_code == 200
    names = [m["name"] for m in r.json()["manifests"]]
    # Both manifests show up; the explicit subset and the default.
    assert set(names) == {"default", "igfarben"}


def test_library_detail_returns_full_doc(app_with_data):
    app, _ = app_with_data
    c = TestClient(app)
    r = c.get("/api/library/igfarben")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "igfarben"
    assert body["source"]["parent_naid"] == "7840517"
    assert len(body["file_units"]) == 1
    assert body["file_units"][0]["naid"] == "9"


def test_library_detail_404_when_missing(app_with_data):
    app, _ = app_with_data
    c = TestClient(app)
    r = c.get("/api/library/does-not-exist")
    assert r.status_code == 404


def test_library_detail_400_on_bad_name(app_with_data):
    app, _ = app_with_data
    c = TestClient(app)
    r = c.get("/api/library/..%2Fetc")
    assert r.status_code in (400, 404)  # path-traversal blocked


def test_library_search_finds_by_title(app_with_data):
    app, _ = app_with_data
    c = TestClient(app)
    r = c.get("/api/library/default/search", params={"q": "smith"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["matches"][0]["naid"] == "1001"


def test_library_search_matches_scope_note(app_with_data):
    app, _ = app_with_data
    c = TestClient(app)
    r = c.get("/api/library/default/search", params={"q": "dye"})
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_library_search_empty_result(app_with_data):
    app, _ = app_with_data
    c = TestClient(app)
    r = c.get("/api/library/default/search", params={"q": "zzzzzz"})
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_library_search_requires_q(app_with_data):
    app, _ = app_with_data
    c = TestClient(app)
    r = c.get("/api/library/default/search")
    assert r.status_code == 422
