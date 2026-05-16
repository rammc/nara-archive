"""Typer CLI for nara-archive."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from .api import NaraApiError, NaraClient
from .downloader import download_all
from .filter import FilterError, apply_filter
from .manifest import verify_manifest, write_manifest
from .metadata import fetch_and_persist
from .pdfbuild import build_pdfs
from .utils import (
    OutputPaths,
    get_logger,
    manifest_path_for,
    setup_logging,
)

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)

DEFAULT_PARENT_NAID = "7840517"
DEFAULT_OUTPUT_DIR = Path("./output")

# Module-level flag set by the Typer callback before any subcommand runs.
# Per-command --verbose options OR the global --verbose flag both flip this on.
_state: dict[str, bool] = {"verbose": False}


@app.callback()
def _global_options(
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="DEBUG-level logging to console and file (applies to all subcommands).",
    ),
) -> None:
    """Global flags applied before any subcommand."""
    if verbose:
        _state["verbose"] = True


def _bootstrap(output_dir: Path, *, verbose: bool = False) -> OutputPaths:
    load_dotenv()
    paths = OutputPaths(root=output_dir.resolve())
    paths.ensure()
    setup_logging(paths.run_log, verbose=verbose or _state["verbose"])
    return paths


def _die_on_api_error(fn, *args, **kwargs):
    """Run a callable and translate NaraApiError into a clean Exit(2)."""
    try:
        return fn(*args, **kwargs)
    except NaraApiError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(2)


def _resolve_metadata_path(paths: OutputPaths, metadata_file: Optional[Path]) -> Path:
    """Pick the metadata file to operate on. Errors out if it doesn't exist."""
    target = metadata_file if metadata_file is not None else paths.metadata
    if not target.exists():
        typer.echo(
            f"error: {target} not found — run `nara metadata` (or `nara filter`) first.",
            err=True,
        )
        raise typer.Exit(2)
    return target


@app.command()
def metadata(
    parent_naid: str = typer.Option(DEFAULT_PARENT_NAID, "--parent-naid", help="NAID of the parent record."),
    limit: int = typer.Option(300, "--limit", help="Max children to request."),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir", help="Where to write artefacts."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="DEBUG logging."),
) -> None:
    """Phase 1: fetch + normalize child File Unit metadata."""
    paths = _bootstrap(output_dir, verbose=verbose)
    client = _die_on_api_error(NaraClient)
    _die_on_api_error(fetch_and_persist, parent_naid, paths, limit=limit, client=client)


@app.command()
def filter(  # noqa: A001 — shadowing builtin is fine for a subcommand name
    query: str = typer.Option(..., "--query", "-q", help="Regex (case-insensitive)."),
    name: str = typer.Option(..., "--name", "-n",
                             help="Subset name; produces metadata-{name}.json."),
    fields: str = typer.Option(
        "title,scope_and_content_note", "--field", "--fields",
        help="Comma-separated field names to match against.",
    ),
    metadata_file: Optional[Path] = typer.Option(
        None, "--metadata-file",
        help="Source metadata file. Defaults to output/metadata.json.",
    ),
    force: bool = typer.Option(False, "--force/--no-force",
                               help="Overwrite an existing metadata-{name}.json."),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Filter a metadata file by regex into a topic-scoped subset."""
    paths = _bootstrap(output_dir, verbose=verbose)
    field_list = [f.strip() for f in fields.split(",") if f.strip()]
    try:
        out_path, doc = apply_filter(
            paths,
            name=name,
            query=query,
            fields=field_list,
            metadata_file=metadata_file,
            force=force,
        )
    except (FilterError, ValueError) as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(2)

    matches = doc["file_units"]
    total = doc["filter"]["total_source_count"]
    if not matches:
        typer.echo(f"matched 0/{total} file units — nothing written")
        typer.echo("error: filter matched zero file units", err=True)
        raise typer.Exit(2)
    typer.echo(f"matched {len(matches)}/{total} file units → {out_path}")

    total_objs = sum(u.get("digital_object_count", 0) for u in matches)
    typer.echo(f"total digital_object_count across matches: {total_objs}")
    typer.echo("")
    typer.echo(f"{'naid':>12}  {'objs':>6}  title")
    for u in matches:
        title = u.get("title") or ""
        if len(title) > 80:
            title = title[:77] + "..."
        typer.echo(f"{str(u.get('naid') or ''):>12}  {u.get('digital_object_count', 0):>6}  {title}")


@app.command()
def download(
    rate: float = typer.Option(1.0, "--rate", help="Seconds between requests."),
    resume: bool = typer.Option(True, "--resume/--no-resume",
                                help="Skip files whose size matches metadata."),
    metadata_file: Optional[Path] = typer.Option(
        None, "--metadata-file",
        help="Alternative metadata file (e.g. a subset from `nara filter`).",
    ),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Phase 2: download every digital object into output/raw/."""
    paths = _bootstrap(output_dir, verbose=verbose)
    source = _resolve_metadata_path(paths, metadata_file)
    _ = resume  # current implementation always resumes; flag kept for clarity
    meta = json.loads(source.read_text(encoding="utf-8"))
    client = _die_on_api_error(NaraClient)
    counts = _die_on_api_error(download_all, paths, rate=rate, client=client, metadata=meta)
    typer.echo(
        f"downloaded={counts['downloaded']} skipped={counts['skipped']} "
        f"failed={counts['failed']}"
    )


@app.command("build-pdfs")
def build_pdfs_cmd(
    force: bool = typer.Option(False, "--force/--no-force",
                               help="Rebuild PDFs even if output already exists."),
    metadata_file: Optional[Path] = typer.Option(
        None, "--metadata-file",
        help="Alternative metadata file (e.g. a subset from `nara filter`).",
    ),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Phase 3: assemble one PDF per File Unit and write the manifest file."""
    paths = _bootstrap(output_dir, verbose=verbose)
    source = _resolve_metadata_path(paths, metadata_file)
    meta = json.loads(source.read_text(encoding="utf-8"))
    results = build_pdfs(paths, force=force, metadata=meta)
    write_manifest(paths, metadata=meta, build_results=results,
                   out_path=manifest_path_for(source))


@app.command()
def run(
    parent_naid: str = typer.Option(DEFAULT_PARENT_NAID, "--parent-naid"),
    rate: float = typer.Option(1.0, "--rate"),
    limit: int = typer.Option(300, "--limit"),
    metadata_file: Optional[Path] = typer.Option(
        None, "--metadata-file",
        help="If set, skip Phase 1 and run Phase 2+3 starting from this file.",
    ),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run all three phases sequentially (or only 2+3 if --metadata-file given)."""
    paths = _bootstrap(output_dir, verbose=verbose)
    client = _die_on_api_error(NaraClient)
    if metadata_file is not None:
        source = _resolve_metadata_path(paths, metadata_file)
        meta = json.loads(source.read_text(encoding="utf-8"))
    else:
        meta = _die_on_api_error(fetch_and_persist, parent_naid, paths, limit=limit, client=client)
        source = paths.metadata
    _die_on_api_error(download_all, paths, rate=rate, client=client, metadata=meta)
    results = build_pdfs(paths, metadata=meta)
    write_manifest(paths, metadata=meta, build_results=results,
                   out_path=manifest_path_for(source))


@app.command()
def stats(
    metadata_file: Optional[Path] = typer.Option(
        None, "--metadata-file",
        help="Alternative metadata file. Stats will prefer its sibling manifest.",
    ),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir"),
) -> None:
    """Print counts, sizes, and an error summary for the current output dir."""
    paths = _bootstrap(output_dir)
    log = get_logger()

    if metadata_file is not None:
        source_meta = metadata_file
        manifest = manifest_path_for(metadata_file)
    else:
        source_meta = paths.metadata
        manifest = paths.manifest

    if manifest.exists():
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        s = doc.get("stats", {})
        log.info("Manifest %s stats:", manifest.name)
        for k, v in s.items():
            log.info("  %-22s %s", k, v)
    elif source_meta.exists():
        doc = json.loads(source_meta.read_text(encoding="utf-8"))
        units = doc.get("file_units", [])
        objs = sum(u.get("digital_object_count", 0) for u in units)
        log.info("%s present, %s missing.", source_meta.name, manifest.name)
        log.info("file_units=%d digital_objects=%d", len(units), objs)
    else:
        log.info("No %s or %s yet — run `nara metadata` first.",
                 source_meta.name, manifest.name)

    if paths.errors_log.exists():
        n = sum(1 for _ in paths.errors_log.open("r", encoding="utf-8"))
        log.info("errors.log entries: %d (%s)", n, paths.errors_log)
    else:
        log.info("errors.log: no errors logged")

    if paths.state.exists():
        try:
            state = json.loads(paths.state.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
        total_files = sum(len(v) for v in state.values())
        downloaded = sum(1 for v in state.values() for s in v.values() if s == "downloaded")
        failed = sum(1 for v in state.values() for s in v.values() if s == "failed")
        log.info("state.json: tracked=%d downloaded=%d failed=%d",
                 total_files, downloaded, failed)


@app.command()
def verify(
    metadata_file: Optional[Path] = typer.Option(
        None, "--metadata-file",
        help="Verify the sibling manifest of this metadata file.",
    ),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir"),
) -> None:
    """Check every manifest entry resolves to a real PDF on disk."""
    paths = _bootstrap(output_dir)
    manifest = manifest_path_for(metadata_file) if metadata_file else None
    code, problems = verify_manifest(paths, manifest_path=manifest)
    if code == 0:
        typer.echo("manifest verified: all ok entries present and non-empty")
    else:
        for p in problems:
            typer.echo(p, err=True)
    raise typer.Exit(code)


def main() -> None:  # pragma: no cover
    """Allow `python -m nara` to work alongside the console_scripts entry."""
    try:
        app()
    except KeyboardInterrupt:
        typer.echo("interrupted", err=True)
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    main()
