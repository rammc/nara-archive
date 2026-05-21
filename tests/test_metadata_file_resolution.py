"""End-to-end tests that the CLI resolves --metadata-file correctly."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from actari.cli import app
from actari.metadata import SCHEMA_VERSION, normalize_response

FIXTURE = Path(__file__).parent / "fixtures" / "sample_response.json"


def _doc_from_fixture(extra_filter: dict | None = None) -> dict:
    units = normalize_response(json.loads(FIXTURE.read_text(encoding="utf-8")))
    doc = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "parent_naid": "test",
            "parent_title": None,
            "fetched_at": "2026-05-16T00:00:00Z",
            "api_base": "https://example.test/",
        },
        "file_units": units,
    }
    if extra_filter is not None:
        doc["filter"] = extra_filter
        doc["file_units"] = [u for u in units if u["naid"] == "10000004"]
    return doc


def test_stats_default_reads_metadata_json(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "metadata.json").write_text(json.dumps(_doc_from_fixture()), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["stats", "--output-dir", str(output_dir)])

    assert result.exit_code == 0
    assert "metadata.json present" in result.stderr
    assert "file_units=4" in result.stderr


def test_stats_with_metadata_file_reads_alternative(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    # Write the full file too so the default would point somewhere valid;
    # we explicitly request the subset and expect the count to be 1.
    (output_dir / "metadata.json").write_text(json.dumps(_doc_from_fixture()), encoding="utf-8")
    subset_path = output_dir / "metadata-igfarben.json"
    subset_path.write_text(
        json.dumps(
            _doc_from_fixture(
                extra_filter={
                    "name": "igfarben",
                    "query": "farben",
                    "fields": ["title"],
                    "source_file": "metadata.json",
                    "matched_count": 1,
                    "total_source_count": 4,
                    "applied_at": "2026-05-16T00:00:00Z",
                }
            )
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "stats",
            "--metadata-file",
            str(subset_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert "metadata-igfarben.json present" in result.stderr
    assert "file_units=1" in result.stderr


def test_filter_command_writes_subset(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "metadata.json").write_text(json.dumps(_doc_from_fixture()), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "filter",
            "--query",
            r"I\.?G\.?\s*Farben",
            "--name",
            "igfarben",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0, result.output + (result.stderr or "")
    out_path = output_dir / "metadata-igfarben.json"
    assert out_path.exists()
    doc = json.loads(out_path.read_text(encoding="utf-8"))
    assert doc["filter"]["matched_count"] == 1
    assert [u["naid"] for u in doc["file_units"]] == ["10000004"]
    assert "matched 1/4" in result.stdout


def test_filter_command_zero_matches_exit_2(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "metadata.json").write_text(json.dumps(_doc_from_fixture()), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "filter",
            "--query",
            "nope-no-match",
            "--name",
            "nada",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 2


def test_filter_command_rejects_invalid_name(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "metadata.json").write_text(json.dumps(_doc_from_fixture()), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "filter",
            "--query",
            "farben",
            "--name",
            "../boom",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 2
    assert "invalid --name" in (result.stderr or result.output)
