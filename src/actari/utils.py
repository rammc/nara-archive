"""Shared helpers: paths, slugging, logging."""

from __future__ import annotations

import logging
import logging.handlers
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from slugify import slugify as _slugify

SLUG_MAX_LEN = 80
RUN_LOG_MAX_BYTES = 10_000_000
RUN_LOG_BACKUP_COUNT = 5


@dataclass(frozen=True)
class OutputPaths:
    """Canonical layout for all run artefacts under a single output dir."""

    root: Path

    @property
    def metadata_raw(self) -> Path:
        return self.root / "metadata-raw.json"

    @property
    def metadata(self) -> Path:
        return self.root / "metadata.json"

    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    @property
    def state(self) -> Path:
        return self.root / "state.json"

    @property
    def errors_log(self) -> Path:
        return self.root / "errors.log"

    @property
    def run_log(self) -> Path:
        return self.root / "run.log"

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def pdfs_dir(self) -> Path:
        return self.root / "pdfs"

    def raw_dir_for(self, naid: str) -> Path:
        return self.raw_dir / naid

    def ensure(self) -> None:
        """Create all output subdirectories that the pipeline writes into."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.pdfs_dir.mkdir(parents=True, exist_ok=True)


def make_slug(title: str | None) -> str:
    """Kebab-case slug bounded to ``SLUG_MAX_LEN``."""
    if not title:
        return "untitled"
    return (
        _slugify(title, max_length=SLUG_MAX_LEN, word_boundary=True, save_order=True) or "untitled"
    )


def utc_now_iso() -> str:
    """ISO-8601 timestamp in UTC, second precision, 'Z' suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


_LOGGER_NAME = "actari"


def setup_logging(run_log: Path, *, verbose: bool = False) -> logging.Logger:
    """Configure the package logger.

    Console: INFO (or DEBUG with --verbose). File: rotating, INFO by default,
    DEBUG with --verbose. File rotation caps run.log at 10 MB with 5 backups
    so a long Phase 2 run cannot fill the disk.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    # Idempotent: clear handlers so repeated CLI invocations don't duplicate output.
    for h in list(logger.handlers):
        logger.removeHandler(h)

    level = logging.DEBUG if verbose else logging.INFO

    console = logging.StreamHandler(stream=sys.stderr)
    console.setLevel(level)
    console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(console)

    run_log.parent.mkdir(parents=True, exist_ok=True)
    file = logging.handlers.RotatingFileHandler(
        run_log,
        maxBytes=RUN_LOG_MAX_BYTES,
        backupCount=RUN_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file.setLevel(level)
    file.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(file)
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)


def atomic_write_text(path: Path, content: str) -> None:
    """Write text atomically by going through a sibling .tmp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def safe_get(d, *path, default=None):
    """Walk a nested dict/list path, returning ``default`` on any miss."""
    cur = d
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur


_FILTER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def validate_filter_name(name: str) -> str:
    """Reject names that would escape the output dir or break filenames."""
    if not name or not _FILTER_NAME_RE.fullmatch(name):
        raise ValueError(
            f"invalid --name {name!r}: must match [A-Za-z0-9][A-Za-z0-9_-]* "
            f"(no whitespace, no path separators)"
        )
    return name


def manifest_path_for(metadata_path: Path) -> Path:
    """Derive the manifest path that sits next to a given metadata file.

    ``metadata.json`` → ``manifest.json``
    ``metadata-igfarben.json`` → ``manifest-igfarben.json``
    Anything else → ``manifest-{stem}.json`` in the same directory.
    """
    name = metadata_path.name
    if name == "metadata.json":
        return metadata_path.with_name("manifest.json")
    if name.startswith("metadata-") and name.endswith(".json"):
        return metadata_path.with_name("manifest-" + name[len("metadata-") :])
    return metadata_path.with_name(f"manifest-{metadata_path.stem}.json")


def manifest_name_from_path(path: Path) -> str:
    """Inverse: extract the subset name from a manifest filename.

    ``manifest.json`` → ``"default"``
    ``manifest-igfarben.json`` → ``"igfarben"``
    Anything else → ``path.stem`` (best-effort).
    """
    name = path.name
    if name == "manifest.json":
        return "default"
    if name.startswith("manifest-") and name.endswith(".json"):
        return name[len("manifest-") : -len(".json")]
    return path.stem


def manifest_path_for_name(output_dir: Path, name: str) -> Path:
    """Resolve a manifest filename from its slug name."""
    if name == "default":
        return output_dir / "manifest.json"
    validate_filter_name(name)  # reject path-traversal attempts in URL slugs
    return output_dir / f"manifest-{name}.json"
