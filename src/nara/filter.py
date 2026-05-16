"""Topic-scoped subset selection from a metadata.json file."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from .utils import OutputPaths, atomic_write_text, get_logger, utc_now_iso, validate_filter_name

DEFAULT_FIELDS: tuple[str, ...] = ("title", "scope_and_content_note")


class FilterError(ValueError):
    """Any user-facing problem with a filter invocation."""


def compile_pattern(query: str) -> re.Pattern[str]:
    """Compile ``query`` as a case-insensitive regex or raise FilterError."""
    try:
        return re.compile(query, re.IGNORECASE)
    except re.error as e:
        raise FilterError(f"invalid regex {query!r}: {e}") from e


def filter_file_units(
    file_units: Iterable[dict],
    pattern: re.Pattern[str],
    fields: Iterable[str] = DEFAULT_FIELDS,
) -> list[dict]:
    """Return file units where any of ``fields`` matches ``pattern``."""
    field_list = list(fields)
    out: list[dict] = []
    for unit in file_units:
        for f in field_list:
            value = unit.get(f)
            if isinstance(value, str) and pattern.search(value):
                out.append(unit)
                break
    return out


def make_filter_doc(
    source_doc: dict,
    matches: list[dict],
    *,
    name: str,
    query: str,
    fields: list[str],
    source_file: Path,
) -> dict:
    """Build the augmented metadata document for a filter result."""
    return {
        "schema_version": source_doc.get("schema_version", "1.0"),
        "source": source_doc.get("source", {}),
        "filter": {
            "name": name,
            "query": query,
            "fields": fields,
            "source_file": str(source_file),
            "matched_count": len(matches),
            "total_source_count": len(source_doc.get("file_units", [])),
            "applied_at": utc_now_iso(),
        },
        "file_units": matches,
    }


def output_path_for(paths: OutputPaths, name: str) -> Path:
    return paths.root / f"metadata-{name}.json"


def apply_filter(
    paths: OutputPaths,
    *,
    name: str,
    query: str,
    fields: list[str] | None = None,
    metadata_file: Path | None = None,
    force: bool = False,
) -> tuple[Path, dict]:
    """Run a filter against a metadata file and write the subset to disk.

    Returns ``(output_path, doc)``. Raises ``FilterError`` for bad input or
    refusal to overwrite. Returning the doc lets callers print a summary
    without re-reading the file.
    """
    log = get_logger()
    validate_filter_name(name)
    pattern = compile_pattern(query)
    field_list = list(fields) if fields else list(DEFAULT_FIELDS)

    source_path = metadata_file if metadata_file is not None else paths.metadata
    if not source_path.exists():
        raise FilterError(f"source metadata file not found: {source_path}")
    source_doc = json.loads(source_path.read_text(encoding="utf-8"))

    matches = filter_file_units(source_doc.get("file_units", []), pattern, field_list)

    out_path = output_path_for(paths, name)
    doc = make_filter_doc(
        source_doc,
        matches,
        name=name,
        query=query,
        fields=field_list,
        source_file=source_path,
    )

    if not matches:
        log.info("filter %s: 0/%d matched — nothing written",
                 name, len(source_doc.get("file_units", [])))
        return out_path, doc

    if out_path.exists() and not force:
        raise FilterError(
            f"{out_path} already exists — re-run with --force to overwrite."
        )
    atomic_write_text(out_path, json.dumps(doc, indent=2, ensure_ascii=False))
    log.info(
        "filter %s: %d/%d matched, written to %s",
        name, len(matches), len(source_doc.get("file_units", [])), out_path,
    )
    return out_path, doc
