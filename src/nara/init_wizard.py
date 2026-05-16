"""Interactive setup wizard for ``nara init``."""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.text import Text

from .config import (
    DEFAULT_API_BASE_URL,
    DEFAULT_RATE,
    user_config_dir,
    user_config_path,
    write_config,
)

NARA_TERMS_BLURB = (
    "NARA's Catalog API is offered free of charge for research and educational use. "
    "Their published terms ask consumers to keep usage reasonable (default rate "
    "limit: 10,000 requests per key per month) and to avoid bulk scraping. They "
    "explicitly recommend the AWS Open Data mirror for full-archive transfers. "
    "This tool defaults to 1 request/second to stay polite.\n\n"
    "This project is not affiliated with or endorsed by NARA."
)

KEY_FREE_BLURB = (
    "Don't have a key? Get one for free in ~2 minutes:\n"
    "  1. Visit https://www.archives.gov/research/catalog/help/api\n"
    "  2. Email Catalog_API@nara.gov from your research-affiliated address\n"
    "  3. They reply with a 40-character key — paste it here."
)


class WizardAborted(RuntimeError):
    pass


def _validate_api_key(key: str, base_url: str = DEFAULT_API_BASE_URL) -> tuple[bool, str]:
    """Make one live call to confirm the key is accepted. Returns (ok, message)."""
    if not key or len(key.strip()) < 10:
        return False, "key looks too short (NARA keys are typically 40 chars)"
    url = base_url.rstrip("/") + "/records/search"
    try:
        resp = requests.get(
            url,
            params={"q": "test", "limit": 1},
            headers={"x-api-key": key, "Accept": "application/json"},
            timeout=15,
        )
    except requests.exceptions.RequestException as e:
        return False, f"network error: {e}"
    ctype = (resp.headers.get("content-type") or "").lower()
    if resp.status_code == 401 or resp.status_code == 403:
        return False, f"HTTP {resp.status_code} — key rejected by NARA"
    if "json" not in ctype:
        return False, (
            "got HTML instead of JSON — NARA's CloudFront couldn't reach the API "
            "origin from your current network. The key may still be valid; you "
            "can save it anyway and retry connectivity later."
        )
    if resp.status_code >= 400:
        return False, f"HTTP {resp.status_code}: {resp.text[:120]}"
    return True, "key validated against /records/search"


def run_wizard(
    *,
    target: Path | None = None,
    reset: bool = False,
    console: Console | None = None,
    validator: Callable[[str], tuple[bool, str]] = _validate_api_key,
) -> Path:
    """Run the interactive wizard and write a config file.

    Returns the path of the written config. Raises ``WizardAborted`` if the
    user explicitly cancels.

    ``validator`` is injectable to keep tests fast and offline.
    """
    console = console or Console()
    target = target or user_config_path()

    if target.exists() and not reset:
        if not Confirm.ask(
            f"[yellow]{target} already exists — overwrite?[/]", default=False
        ):
            raise WizardAborted("user declined overwrite")
    if target.exists() and reset:
        backup = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, backup)
        console.print(f"[dim]Backed up existing config to {backup}[/]")

    console.print(Panel.fit(
        Text.from_markup(
            "[bold]nara-archive[/] · setup wizard\n"
            "Bulk-download NARA Catalog digital objects and assemble PDFs.\n\n"
            "This wizard writes [cyan]" + str(target) + "[/].",
        ),
        border_style="amber" if False else "yellow",  # rich has no 'amber' style key
    ))

    # Step 1: API key
    console.print()
    console.print(Text.from_markup("[bold]Step 1 / 3:[/] NARA Catalog API key"))
    console.print(KEY_FREE_BLURB, style="dim")

    api_key = ""
    while True:
        api_key = Prompt.ask("API key", password=True).strip()
        if not api_key:
            console.print("[red]no input — try again[/]")
            continue
        console.print("[dim]validating against /records/search?q=test ...[/]")
        ok, msg = validator(api_key)
        if ok:
            console.print(f"[green]✓ {msg}[/]")
            break
        console.print(f"[yellow]✗ {msg}[/]")
        choice = Prompt.ask(
            "  [r]etry / [s]ave anyway / [a]bort",
            choices=["r", "s", "a"],
            default="r",
        )
        if choice == "s":
            console.print("[dim]saving unvalidated key — `nara serve` health-check will tell you[/]")
            break
        if choice == "a":
            raise WizardAborted("user aborted at API key step")

    # Step 2: output dir
    console.print()
    console.print(Text.from_markup("[bold]Step 2 / 3:[/] Where should downloads live?"))
    default_out = user_config_dir() / "output"
    output_dir_str = Prompt.ask("Output directory", default=str(default_out))
    output_dir = Path(output_dir_str).expanduser().resolve()
    console.print(f"[dim]→ {output_dir}[/]")

    # Step 3: terms
    console.print()
    console.print(Text.from_markup("[bold]Step 3 / 3:[/] NARA terms of use"))
    console.print(Panel(NARA_TERMS_BLURB, border_style="dim"))
    if not Confirm.ask("Acknowledge NARA's terms?", default=True):
        raise WizardAborted("terms not acknowledged")

    target = write_config(
        api_key=api_key,
        output_dir=output_dir,
        default_rate=DEFAULT_RATE,
        terms_acknowledged=True,
        target=target,
    )
    console.print()
    console.print(Panel.fit(
        Text.from_markup(
            f"[green]✓ Setup complete.[/] Config written to [cyan]{target}[/]\n\n"
            "Next steps:\n"
            "  [bold]nara serve[/]                       launch the web UI\n"
            "  [bold]nara metadata --parent-naid …[/]    use the CLI directly"
        ),
        border_style="green",
    ))
    _ = datetime.now(timezone.utc)  # ack timestamp written inside write_config
    return target
