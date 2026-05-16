"""Phase 2: download every digital object referenced in metadata.json."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests
from tqdm import tqdm

from .api import NaraClient
from .utils import OutputPaths, atomic_write_text, get_logger


def _load_state(state_path: Path) -> dict[str, dict[str, str]]:
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        get_logger().warning("state.json is corrupt — starting fresh")
        return {}


def _write_state(state_path: Path, state: dict[str, dict[str, str]]) -> None:
    atomic_write_text(state_path, json.dumps(state, indent=2, ensure_ascii=False))


def _append_error(errors_log: Path, naid: str, filename: str, reason: str) -> None:
    errors_log.parent.mkdir(parents=True, exist_ok=True)
    line = f"naid={naid}\tfile={filename}\treason={reason}\n"
    with errors_log.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _file_complete(path: Path, expected: int | None) -> bool:
    """Treat a file as complete if it exists and (when known) matches expected size."""
    if not path.exists():
        return False
    if expected is None:
        return path.stat().st_size > 0
    return path.stat().st_size == expected


def download_all(
    paths: OutputPaths,
    *,
    rate: float = 1.0,
    client: NaraClient | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Download all digital objects from ``metadata.json`` into ``output/raw/``.

    Single-threaded. Sleeps ``rate`` seconds between every HTTP request to
    stay polite. Errors per file are logged and never abort the run.

    Returns a small counter dict for the CLI summary.
    """
    log = get_logger()
    paths.ensure()

    if metadata is None:
        if not paths.metadata.exists():
            raise FileNotFoundError(
                f"{paths.metadata} not found — run `nara metadata` first."
            )
        metadata = json.loads(paths.metadata.read_text(encoding="utf-8"))

    units = metadata.get("file_units", [])
    state = _load_state(paths.state)
    client = client or NaraClient()

    total_objects = sum(u.get("digital_object_count", 0) for u in units)
    counts = {"downloaded": 0, "skipped": 0, "failed": 0}

    with tqdm(total=total_objects, desc="files", unit="file") as pbar_files, \
         tqdm(total=_known_bytes(units), desc="bytes", unit="B", unit_scale=True) as pbar_bytes:
        for unit in units:
            naid = str(unit.get("naid") or "").strip()
            if not naid:
                log.warning("skipping unit with empty NAID")
                continue
            target_dir = paths.raw_dir_for(naid)
            target_dir.mkdir(parents=True, exist_ok=True)
            unit_state = state.setdefault(naid, {})

            for obj in unit.get("digital_objects", []):
                filename = obj["filename"]
                url = obj["url"]
                expected = obj.get("size_bytes")
                dest = target_dir / filename

                if _file_complete(dest, expected):
                    unit_state[filename] = "downloaded"
                    counts["skipped"] += 1
                    log.debug("naid=%s skip %s (already complete)", naid, filename)
                    pbar_files.update(1)
                    if expected:
                        pbar_bytes.update(expected)
                    continue

                ok, bytes_written, reason = _download_one(client, url, dest)
                if ok:
                    unit_state[filename] = "downloaded"
                    counts["downloaded"] += 1
                    log.info("naid=%s downloaded %s (%d bytes)", naid, filename, bytes_written)
                    pbar_bytes.update(bytes_written)
                else:
                    unit_state[filename] = "failed"
                    counts["failed"] += 1
                    log.error("naid=%s FAILED %s: %s", naid, filename, reason)
                    _append_error(paths.errors_log, naid, filename, reason)
                    # Best-effort cleanup of partial file.
                    if dest.exists():
                        try:
                            dest.unlink()
                        except OSError:
                            pass

                _write_state(paths.state, state)
                pbar_files.update(1)
                time.sleep(rate)

    log.info("Download summary: downloaded=%d skipped=%d failed=%d",
             counts["downloaded"], counts["skipped"], counts["failed"])
    return counts


def _known_bytes(units: list[dict]) -> int:
    total = 0
    for u in units:
        for o in u.get("digital_objects", []):
            size = o.get("size_bytes")
            if isinstance(size, int):
                total += size
    return total


def _download_one(client: NaraClient, url: str, dest: Path) -> tuple[bool, int, str]:
    """Stream URL to ``dest`` via a ``.part`` tempfile. Renames on success."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with tmp.open("wb") as fh:
            written = client.stream_download(url, fh)
        tmp.replace(dest)
        return True, written, ""
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return False, 0, f"HTTP {status}"
    except requests.exceptions.RequestException as e:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return False, 0, f"network: {e.__class__.__name__}: {e}"
    except OSError as e:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return False, 0, f"io: {e}"
