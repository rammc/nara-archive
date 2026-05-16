"""Tests for the metadata normalizer."""
from __future__ import annotations

import json
from pathlib import Path

from nara.metadata import normalize_response

FIXTURE = Path(__file__).parent / "fixtures" / "sample_response.json"


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_normalize_yields_all_file_units():
    raw = _load()
    units = normalize_response(raw)
    assert len(units) == 4
    assert {u["naid"] for u in units} == {
        "10000001", "10000002", "10000003", "10000004",
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
