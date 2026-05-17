"""Tests for the metadata normalizer."""

from __future__ import annotations

import json
from pathlib import Path

from nara.metadata import fetch_and_persist, normalize_response
from nara.utils import OutputPaths

FIXTURE = Path(__file__).parent / "fixtures" / "sample_response.json"


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _empty_children() -> dict:
    return {"body": {"hits": {"total": {"value": 0}, "hits": []}}}


class _FakeClient:
    """In-memory NaraClient stand-in for fetch_and_persist tests."""

    def __init__(self, *, children: dict | None = None, record: dict | None = None):
        self._children = children if children is not None else _empty_children()
        self._record = record

    def get_children(self, parent_naid: str, *, limit: int = 300) -> dict:
        return self._children

    def get_record(self, naid: str) -> dict | None:
        if self._record is None:
            return None
        return {"body": {"hits": {"hits": [{"_source": {"record": self._record}}]}}}


def test_normalize_yields_all_file_units():
    raw = _load()
    units = normalize_response(raw)
    assert len(units) == 4
    assert {u["naid"] for u in units} == {
        "10000001",
        "10000002",
        "10000003",
        "10000004",
    }


def test_normalize_preserves_sort_order_and_filenames():
    raw = _load()
    units = normalize_response(raw)
    by_naid = {u["naid"]: u for u in units}

    unit_a = by_naid["10000001"]
    assert unit_a["digital_object_count"] == 3
    assert [d["filename"] for d in unit_a["digital_objects"]] == [
        "page-001.jpg",
        "page-002.jpg",
        "page-003.jpg",
    ]
    assert all(d["sort_number"] is not None for d in unit_a["digital_objects"])


def test_normalize_handles_missing_fields():
    raw = _load()
    units = normalize_response(raw)
    by_naid = {u["naid"]: u for u in units}

    # Unit B has no scopeAndContentNote and no inclusive dates.
    unit_b = by_naid["10000002"]
    assert unit_b["scope_and_content_note"] is None
    assert unit_b["inclusive_start_year"] is None
    assert unit_b["inclusive_end_year"] is None

    # Third digital object in unit B is missing sort_number.
    assert unit_b["digital_objects"][2]["sort_number"] is None


def test_normalize_extracts_year_only_dates():
    raw = _load()
    units = normalize_response(raw)
    by_naid = {u["naid"]: u for u in units}

    unit_c = by_naid["10000003"]
    assert unit_c["inclusive_start_year"] == 1946
    # No end date provided → None.
    assert unit_c["inclusive_end_year"] is None


def test_slug_is_kebab_case_and_bounded():
    raw = _load()
    units = normalize_response(raw)
    by_naid = {u["naid"]: u for u in units}

    slug = by_naid["10000001"]["slug"]
    assert slug == "letter-from-general-smith-june-1944"
    assert len(slug) <= 80
    assert " " not in slug


def test_normalize_survives_completely_empty_record():
    raw = {
        "body": {
            "hits": {
                "total": {"value": 1},
                "hits": [{"_source": {"record": {"naId": "999"}}}],
            }
        }
    }
    units = normalize_response(raw)
    assert len(units) == 1
    u = units[0]
    assert u["naid"] == "999"
    assert u["title"] in (None, "")
    assert u["digital_objects"] == []
    assert u["digital_object_count"] == 0


def test_normalize_survives_total_missing():
    # API sometimes returns no hits at all.
    raw = {"body": {"hits": {"hits": []}}}
    assert normalize_response(raw) == []


def test_fetch_and_persist_leaf_record_becomes_single_file_unit(tmp_path):
    """parentNaId returns 0 hits but the record itself has digitalObjects → 1 unit."""
    leaf = {
        "naId": "42",
        "title": "Standalone Item with Scans",
        "levelOfDescription": "item",
        "digitalObjects": [
            {
                "objectFilename": "scan-1.jpg",
                "objectUrl": "https://example.test/42/scan-1.jpg",
                "objectType": "Image (JPG)",
                "objectFileSize": 12345,
                "sortNumber": 1,
            },
            {
                "objectFilename": "scan-2.jpg",
                "objectUrl": "https://example.test/42/scan-2.jpg",
                "objectType": "Image (JPG)",
                "objectFileSize": 23456,
                "sortNumber": 2,
            },
        ],
    }
    client = _FakeClient(children=_empty_children(), record=leaf)
    doc = fetch_and_persist("42", OutputPaths(root=tmp_path), client=client)
    assert len(doc["file_units"]) == 1
    unit = doc["file_units"][0]
    assert unit["naid"] == "42"
    assert unit["title"] == "Standalone Item with Scans"
    assert unit["digital_object_count"] == 2
    assert doc["source"]["parent_title"] == "Standalone Item with Scans"


def test_fetch_and_persist_empty_record_yields_no_units(tmp_path):
    """No children and no digitalObjects → empty file_units (JobManager will fail this)."""
    container = {
        "naId": "100",
        "title": "Empty Container",
        "levelOfDescription": "series",
        # No digitalObjects key at all.
    }
    client = _FakeClient(children=_empty_children(), record=container)
    doc = fetch_and_persist("100", OutputPaths(root=tmp_path), client=client)
    assert doc["file_units"] == []
    assert doc["source"]["parent_title"] == "Empty Container"


def test_fetch_and_persist_with_children_ignores_leaf_fallback(tmp_path):
    """If children exist, the leaf-record fallback must not run."""
    children_raw = _load()  # 4 file units
    leaf = {
        "naId": "999",
        "title": "Parent",
        "digitalObjects": [
            {
                "objectFilename": "should-be-ignored.jpg",
                "objectUrl": "https://example.test/999/x.jpg",
                "sortNumber": 1,
            }
        ],
    }
    client = _FakeClient(children=children_raw, record=leaf)
    doc = fetch_and_persist("999", OutputPaths(root=tmp_path), client=client)
    # 4 from children; parent's own digitalObjects must NOT be added.
    assert len(doc["file_units"]) == 4
    assert all(u["naid"] != "999" for u in doc["file_units"])
