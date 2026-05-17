"""Curated starter searches shipped with the package.

The presets file (``src/nara/data/presets.json``) is a fixed bundle of
hand-curated entry points into NARA's catalog — currently weighted toward
IG-Farben / WWII war-crimes research. Adding entries requires editing the
JSON; users don't override it from disk in this release.

Each preset combines an optional ``search`` block (query + filters that the
Discovery UI applies one-click) with an optional ``direct_naid`` shortcut for
records where the canonical container's NAID is known.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).parent / "data" / "presets.json"

# Fields a search block may carry. Anything else in the JSON is dropped.
_ALLOWED_SEARCH_KEYS = {"q", "record_group", "level", "year_from", "year_to", "has_digital_objects"}
_REQUIRED_PRESET_KEYS = {"id", "title", "description", "category"}


class PresetError(ValueError):
    """The shipped preset bundle is malformed."""


def _validate_search(block: Any, where: str) -> dict[str, Any]:
    if not isinstance(block, dict):
        raise PresetError(f"{where}: search block must be an object")
    out: dict[str, Any] = {}
    for k, v in block.items():
        if k not in _ALLOWED_SEARCH_KEYS:
            raise PresetError(f"{where}: unknown search key {k!r}")
        out[k] = v
    if "q" not in out or not isinstance(out["q"], str) or not out["q"].strip():
        raise PresetError(f"{where}: search.q is required and must be a non-empty string")
    for list_key in ("record_group", "level"):
        if list_key in out and not (
            isinstance(out[list_key], list) and all(isinstance(x, str) for x in out[list_key])
        ):
            raise PresetError(f"{where}: search.{list_key} must be a list of strings")
    return out


def _validate_preset(p: Any, idx: int) -> dict[str, Any]:
    where = f"preset[{idx}]"
    if not isinstance(p, dict):
        raise PresetError(f"{where}: must be an object")
    missing = _REQUIRED_PRESET_KEYS - set(p)
    if missing:
        raise PresetError(f"{where}: missing fields {sorted(missing)!r}")
    pid = p["id"]
    if not isinstance(pid, str) or not pid:
        raise PresetError(f"{where}: id must be a non-empty string")
    search = _validate_search(p.get("search"), f"{where} ({pid})") if p.get("search") else None
    direct = p.get("direct_naid")
    if direct is not None and (not isinstance(direct, str) or not direct.strip()):
        raise PresetError(f"{where} ({pid}): direct_naid must be a non-empty string or null")
    if search is None and direct is None:
        raise PresetError(f"{where} ({pid}): must have either search or direct_naid")
    tags = p.get("tags") or []
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise PresetError(f"{where} ({pid}): tags must be a list of strings")
    return {
        "id": pid,
        "title": str(p["title"]),
        "description": str(p["description"]),
        "category": str(p["category"]),
        "search": search,
        "direct_naid": direct,
        "filter_regex_hint": p.get("filter_regex_hint"),
        "tags": tags,
    }


def load_presets(*, path: Path | None = None) -> list[dict[str, Any]]:
    """Return the validated preset list. Read on every call — file is tiny."""
    target = path or DATA_FILE
    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise PresetError(f"could not read {target}: {e}") from e
    if not isinstance(doc, dict) or not isinstance(doc.get("presets"), list):
        raise PresetError(f"{target}: top level must be {{'presets': [...]}}")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for i, p in enumerate(doc["presets"]):
        validated = _validate_preset(p, i)
        if validated["id"] in seen:
            raise PresetError(f"preset[{i}]: duplicate id {validated['id']!r}")
        seen.add(validated["id"])
        out.append(validated)
    return out
