"""Tests for the filter subcommand and its pure helpers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nara.filter import (
    FilterError,
    apply_filter,
    compile_pattern,
    filter_file_units,
    make_filter_doc,
)
from nara.metadata import SCHEMA_VERSION, normalize_response
from nara.utils import OutputPaths

FIXTURE = Path(__file__).parent / "fixtures" / "sample_response.json"


def _load_units() -> list[dict]:
    return normalize_response(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _write_metadata_file(tmp_path: Path, units: list[dict]) -> Path:
    doc = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "parent_naid": "test",
            "parent_title": "fixture",
            "fetched_at": "2026-05-16T00:00:00Z",
            "api_base": "https://example.test/",
        },
        "file_units": units,
    }
    p = tmp_path / "metadata.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_filter_by_title_only():
    units = _load_units()
    pat = compile_pattern(r"I\.?G\.?\s*Farben")
    out = filter_file_units(units, pat, fields=["title"])
    assert len(out) == 1
    assert out[0]["naid"] == "10000004"


def test_filter_by_scope_only():
    units = _load_units()
    pat = compile_pattern(r"dye works")
    out = filter_file_units(units, pat, fields=["scope_and_content_note"])
    assert [u["naid"] for u in out] == ["10000004"]
    # Same query against title only should yield nothing.
    out2 = filter_file_units(units, pat, fields=["title"])
    assert out2 == []


def test_filter_default_fields_match_either():
    units = _load_units()
    pat = compile_pattern(r"farben")  # case-insensitive
    out = filter_file_units(units, pat)
    assert [u["naid"] for u in out] == ["10000004"]


def test_filter_empty_matches_returns_empty_list():
    units = _load_units()
    pat = compile_pattern(r"this-will-not-match-anything")
    assert filter_file_units(units, pat) == []


def test_invalid_regex_raises_filter_error():
    with pytest.raises(FilterError) as exc:
        compile_pattern(r"(")  # unbalanced
    assert "invalid regex" in str(exc.value).lower()


def test_apply_filter_writes_augmented_schema(tmp_path):
    units = _load_units()
    src = _write_metadata_file(tmp_path, units)
    paths = OutputPaths(root=tmp_path)
    paths.ensure()

    out_path, doc = apply_filter(
        paths,
        name="igfarben",
        query=r"I\.?G\.?\s*Farben",
        metadata_file=src,
    )

    assert out_path == tmp_path / "metadata-igfarben.json"
    assert out_path.exists()
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))

    # Source block preserved exactly.
    assert on_disk["source"] == doc["source"]
    # Filter block well-formed.
    f = on_disk["filter"]
    assert f["name"] == "igfarben"
    assert f["query"] == r"I\.?G\.?\s*Farben"
    assert f["fields"] == ["title", "scope_and_content_note"]
    assert f["matched_count"] == 1
    assert f["total_source_count"] == 4
    assert f["applied_at"].endswith("Z")
    assert str(src) in f["source_file"]

    # Only the matches end up in file_units.
    assert [u["naid"] for u in on_disk["file_units"]] == ["10000004"]


def test_apply_filter_refuses_overwrite_without_force(tmp_path):
    units = _load_units()
    src = _write_metadata_file(tmp_path, units)
    paths = OutputPaths(root=tmp_path)
    paths.ensure()

    apply_filter(paths, name="igfarben", query=r"farben", metadata_file=src)
    with pytest.raises(FilterError) as exc:
        apply_filter(paths, name="igfarben", query=r"farben", metadata_file=src)
    assert "already exists" in str(exc.value)

    # force=True succeeds.
    apply_filter(paths, name="igfarben", query=r"farben",
                 metadata_file=src, force=True)


def test_apply_filter_rejects_invalid_name(tmp_path):
    units = _load_units()
    src = _write_metadata_file(tmp_path, units)
    paths = OutputPaths(root=tmp_path)
    paths.ensure()
    with pytest.raises(ValueError) as exc:
        apply_filter(paths, name="../etc/passwd", query="farben",
                     metadata_file=src)
    assert "invalid --name" in str(exc.value)


def test_make_filter_doc_does_not_mutate_source():
    units = _load_units()
    source_doc = {
        "schema_version": "1.0",
        "source": {"parent_naid": "x"},
        "file_units": units,
    }
    snapshot = json.dumps(source_doc, sort_keys=True)
    make_filter_doc(source_doc, units[:1], name="x", query="q",
                    fields=["title"], source_file=Path("a.json"))
    assert json.dumps(source_doc, sort_keys=True) == snapshot
