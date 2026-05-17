"""Typer CLI for nara-archive."""

from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from .api import NaraApiError, NaraClient
from .config import detect_legacy_env, resolve_config, user_config_path
from .downloader import download_all
from .filter import FilterError, apply_filter
from .init_wizard import WizardAborted, run_wizard
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
# When unset, ``_bootstrap`` derives the output dir from ``resolve_config()``:
# back-compat first (./output if it exists), then ~/.nara/output.
OUTPUT_DIR_HELP = "Where to write artefacts. Defaults to ./output if present, else ~/.nara/output."

# Module-level flag set by the Typer callback before any subcommand runs.
# Per-command --verbose options OR the global --verbose flag both flip this on.
_state: dict[str, bool] = {"verbose": False}


@app.callback()
def _global_options(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="DEBUG-level logging to console and file (applies to all subcommands).",
    ),
) -> None:
    """Global flags applied before any subcommand."""
    if verbose:
        _state["verbose"] = True


def _bootstrap(output_dir: Path | None = None, *, verbose: bool = False) -> OutputPaths:
    load_dotenv()
    cfg = resolve_config()
    root = output_dir if output_dir is not None else cfg.output_dir
    paths = OutputPaths(root=Path(root).expanduser().resolve())
    paths.ensure()
    setup_logging(paths.run_log, verbose=verbose or _state["verbose"])
    legacy = detect_legacy_env()
    if legacy is not None and not cfg.config_path:
        get_logger().info(
            "found legacy .env at %s — consider running `nara init` to migrate to %s",
            legacy,
            user_config_path(),
        )
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
    parent_naid: str = typer.Option(
        DEFAULT_PARENT_NAID, "--parent-naid", help="NAID of the parent record."
    ),
    limit: int = typer.Option(300, "--limit", help="Max children to request."),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help=OUTPUT_DIR_HELP),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="DEBUG logging."),
) -> None:
    """Phase 1: fetch + normalize child File Unit metadata."""
    paths = _bootstrap(output_dir, verbose=verbose)
    client = _die_on_api_error(NaraClient)
    _die_on_api_error(fetch_and_persist, parent_naid, paths, limit=limit, client=client)


@app.command()
def filter(  # noqa: A001 — shadowing builtin is fine for a subcommand name
    query: str = typer.Option(..., "--query", "-q", help="Regex (case-insensitive)."),
    name: str = typer.Option(
        ..., "--name", "-n", help="Subset name; produces metadata-{name}.json."
    ),
    fields: str = typer.Option(
        "title,scope_and_content_note",
        "--field",
        "--fields",
        help="Comma-separated field names to match against.",
    ),
    metadata_file: Optional[Path] = typer.Option(
        None,
        "--metadata-file",
        help="Source metadata file. Defaults to output/metadata.json.",
    ),
    force: bool = typer.Option(
        False, "--force/--no-force", help="Overwrite an existing metadata-{name}.json."
    ),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help=OUTPUT_DIR_HELP),
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
        typer.echo(
            f"{str(u.get('naid') or ''):>12}  {u.get('digital_object_count', 0):>6}  {title}"
        )


@app.command()
def download(
    rate: float = typer.Option(1.0, "--rate", help="Seconds between requests."),
    resume: bool = typer.Option(
        True, "--resume/--no-resume", help="Skip files whose size matches metadata."
    ),
    metadata_file: Optional[Path] = typer.Option(
        None,
        "--metadata-file",
        help="Alternative metadata file (e.g. a subset from `nara filter`).",
    ),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help=OUTPUT_DIR_HELP),
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
        f"downloaded={counts['downloaded']} skipped={counts['skipped']} failed={counts['failed']}"
    )


@app.command("build-pdfs")
def build_pdfs_cmd(
    force: bool = typer.Option(
        False, "--force/--no-force", help="Rebuild PDFs even if output already exists."
    ),
    recompress: bool = typer.Option(
        False,
        "--recompress",
        help="Re-encode large source images (JPEG Q82, max 2400px) before PDF "
        "assembly. Typically shrinks output 5-10x. Pair with --force to rebuild "
        "existing PDFs.",
    ),
    metadata_file: Optional[Path] = typer.Option(
        None,
        "--metadata-file",
        help="Alternative metadata file (e.g. a subset from `nara filter`).",
    ),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help=OUTPUT_DIR_HELP),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Phase 3: assemble one PDF per File Unit and write the manifest file."""
    paths = _bootstrap(output_dir, verbose=verbose)
    source = _resolve_metadata_path(paths, metadata_file)
    meta = json.loads(source.read_text(encoding="utf-8"))
    results = build_pdfs(paths, force=force, recompress=recompress, metadata=meta)
    write_manifest(paths, metadata=meta, build_results=results, out_path=manifest_path_for(source))


@app.command()
def run(
    parent_naid: str = typer.Option(DEFAULT_PARENT_NAID, "--parent-naid"),
    rate: float = typer.Option(1.0, "--rate"),
    limit: int = typer.Option(300, "--limit"),
    recompress: bool = typer.Option(
        False,
        "--recompress",
        help="Recompress source images during Phase 3 (see `build-pdfs --help`).",
    ),
    metadata_file: Optional[Path] = typer.Option(
        None,
        "--metadata-file",
        help="If set, skip Phase 1 and run Phase 2+3 starting from this file.",
    ),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help=OUTPUT_DIR_HELP),
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
    results = build_pdfs(paths, recompress=recompress, metadata=meta)
    write_manifest(paths, metadata=meta, build_results=results, out_path=manifest_path_for(source))


@app.command()
def stats(
    metadata_file: Optional[Path] = typer.Option(
        None,
        "--metadata-file",
        help="Alternative metadata file. Stats will prefer its sibling manifest.",
    ),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help=OUTPUT_DIR_HELP),
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
        log.info("No %s or %s yet — run `nara metadata` first.", source_meta.name, manifest.name)

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
        log.info("state.json: tracked=%d downloaded=%d failed=%d", total_files, downloaded, failed)


@app.command()
def verify(
    metadata_file: Optional[Path] = typer.Option(
        None,
        "--metadata-file",
        help="Verify the sibling manifest of this metadata file.",
    ),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help=OUTPUT_DIR_HELP),
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


@app.command()
def init(
    here: bool = typer.Option(
        False,
        "--here",
        help="Write a project-local .env instead of ~/.nara/config.toml.",
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        help="Back up existing config and re-run the wizard.",
    ),
) -> None:
    """Run the interactive setup wizard."""
    if here:
        # Minimal --here flow: write a .env stub the user fills in manually.
        # We deliberately don't make this interactive — the wizard's whole
        # point is the validation loop, and validation needs to know which
        # base URL to hit. `.env` is for shells, not for first-time setup.
        target = Path.cwd() / ".env"
        if target.exists() and not reset:
            typer.echo(
                f"error: {target} already exists — pass --reset to overwrite.",
                err=True,
            )
            raise typer.Exit(2)
        target.write_text(
            "# nara-archive config — fill in the key, then run any command.\n"
            "NARA_API_KEY=replace-me\n",
            encoding="utf-8",
        )
        typer.echo(f"wrote {target} — set NARA_API_KEY there or run plain `nara init`")
        return

    try:
        path = run_wizard(reset=reset)
    except WizardAborted as e:
        typer.echo(f"aborted: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(f"config: {path}")


@app.command()
def presets(
    output_format: str = typer.Option(
        "table",
        "--format",
        help="Output format: 'table' (rich) or 'json'.",
        case_sensitive=False,
    ),
    show_path: bool = typer.Option(
        False,
        "--path",
        help="Print the user presets file path (~/.nara/presets.json) and exit.",
    ),
    bundled_only: bool = typer.Option(
        False,
        "--bundled-only",
        help="Ignore the user presets file; show only the shipped bundle.",
    ),
) -> None:
    """List curated starter searches (bundled + optional user extensions)."""
    from .presets import PresetError, load_all_presets, load_presets, user_presets_path

    if show_path:
        typer.echo(str(user_presets_path()))
        return

    try:
        data = (
            [{**p, "source": "bundled"} for p in load_presets()]
            if bundled_only
            else load_all_presets()
        )
    except PresetError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1)

    fmt = (output_format or "table").lower()
    if fmt == "json":
        typer.echo(json.dumps({"presets": data}, indent=2, ensure_ascii=False))
        return
    if fmt != "table":
        typer.echo(f"error: unknown --format {output_format!r}; use 'table' or 'json'", err=True)
        raise typer.Exit(2)

    # Lazy-import Rich so plain `--help` / `--format json` stays cheap.
    from rich.console import Console
    from rich.table import Table

    n_user = sum(1 for p in data if p.get("source") == "user")
    title = f"{len(data)} NARA presets"
    if n_user:
        title += f" ({n_user} from your ~/.nara/presets.json)"
    table = Table(title=title, show_lines=True)
    table.add_column("id", style="bold")
    table.add_column("src", style="dim")
    table.add_column("category", style="cyan")
    table.add_column("title")
    table.add_column("direct NAID", style="green")
    table.add_column("RG", style="yellow")
    for p in data:
        rgs = ",".join((p.get("search") or {}).get("record_group") or [])
        src = "user" if p.get("source") == "user" else "bundled"
        table.add_row(
            p["id"],
            src,
            p["category"],
            p["title"],
            p.get("direct_naid") or "—",
            rgs or "—",
        )
    Console().print(table)


@app.command()
def serve(
    host: Optional[str] = typer.Option(
        None,
        "--host",
        help="Bind host. Default 127.0.0.1 (local only). Use 0.0.0.0 to expose on LAN.",
    ),
    port: Optional[int] = typer.Option(None, "--port", help="Bind port. Default 8765."),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Don't auto-open the browser.",
    ),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help=OUTPUT_DIR_HELP),
) -> None:
    """Launch the local web UI."""
    _bootstrap(output_dir)
    cfg = resolve_config()

    if not cfg.has_api_key:
        typer.echo(
            "error: no NARA API key found. Run `nara init` first (or set NARA_API_KEY).",
            err=True,
        )
        raise typer.Exit(2)

    bind_host = host or cfg.server_host
    bind_port = port or cfg.server_port
    if bind_host not in ("127.0.0.1", "localhost", "::1"):
        typer.echo(
            f"WARNING: binding to {bind_host} exposes your API key over the "
            "network to anyone who can reach this port.",
            err=True,
        )

    # Imported lazily so the rest of the CLI doesn't pay the FastAPI import cost.
    import uvicorn

    from .server import create_app

    app_ = create_app(cfg)
    url = f"http://{bind_host}:{bind_port}/"
    typer.echo(f"nara web UI → {url}")

    open_browser = (
        cfg.auto_open_browser and not no_browser and bind_host in ("127.0.0.1", "localhost", "::1")
    )
    if open_browser:
        try:
            webbrowser.open(url, new=2)
        except Exception:  # noqa: BLE001
            pass

    uvicorn.run(app_, host=bind_host, port=bind_port, log_level="info")


def main() -> None:  # pragma: no cover
    """Allow `python -m nara` to work alongside the console_scripts entry."""
    try:
        app()
    except KeyboardInterrupt:
        typer.echo("interrupted", err=True)
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    main()
