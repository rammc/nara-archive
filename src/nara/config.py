"""Resolve runtime config from env, project .env, and ~/.nara/config.toml.

Resolution order (first match wins) per source:
  api_key/base_url/rate:
    1. environment variable (NARA_API_KEY, NARA_API_BASE_URL, NARA_DEFAULT_RATE)
    2. .env in current working directory (loaded into env by dotenv)
    3. ~/.nara/config.toml
  output_dir:
    1. explicit ``--output-dir`` flag (handled by caller)
    2. ./output if it already exists (back-compat for project-local installs)
    3. ~/.nara/output

This module is the single source of truth — no other module should call
``os.getenv`` for NARA-related values.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONFIG_VERSION = 1
DEFAULT_API_BASE_URL = "https://catalog.archives.gov/api/v2/"
DEFAULT_RATE = 0.5
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 8765


def user_config_dir() -> Path:
    """Return ``~/.nara``. Honours ``NARA_HOME`` env var for testability."""
    override = os.environ.get("NARA_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".nara"


def user_config_path() -> Path:
    return user_config_dir() / "config.toml"


def user_jobs_path() -> Path:
    return user_config_dir() / "jobs.json"


@dataclass(frozen=True)
class Config:
    """All resolved runtime settings for one CLI/server invocation."""

    api_key: str | None
    api_base_url: str
    default_rate: float
    output_dir: Path
    server_host: str
    server_port: int
    auto_open_browser: bool
    config_path: Path | None
    terms_acknowledged: bool
    acknowledged_at: str | None
    raw_toml: dict[str, Any] = field(default_factory=dict)
    # GitHub release-check toggle. Default ON so first-run users learn about
    # patch releases without having to discover the setting. Anonymous —
    # one GET on startup, no telemetry beyond that.
    check_for_updates: bool = True

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    def with_output_dir(self, output_dir: Path) -> "Config":
        return replace(self, output_dir=Path(output_dir).expanduser().resolve())


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _maybe_load_dotenv() -> None:
    """Load a .env in CWD if one exists. Existing env vars are NOT overridden."""
    from dotenv import load_dotenv

    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        load_dotenv(cwd_env, override=False)


# --- macOS Keychain integration --------------------------------------------
#
# Used by the PyInstaller-bundled .app where storing the API key in plaintext
# TOML inside ``Contents/Resources/`` would be wrong. We use the system Keychain
# via the ``keyring`` library. On non-Darwin systems or when keyring isn't
# installed, all three helpers return ``None`` / no-op so calling code stays
# branch-free.

KEYCHAIN_SERVICE = "dev.cramm.nara-archive"
KEYCHAIN_ACCOUNT = "api_key"


def _keychain_available() -> bool:
    import platform
    import sys

    if platform.system() != "Darwin":
        return False
    # In a pip-installed CLI we honour TOML first to keep the existing workflow.
    # Only the bundled .app should prefer Keychain reads.
    if not getattr(sys, "frozen", False) and not os.environ.get("NARA_FORCE_KEYCHAIN"):
        return False
    try:
        import keyring  # noqa: F401 — probe
    except ImportError:
        return False
    return True


def _read_keychain_key() -> str | None:
    if not _keychain_available():
        return None
    try:
        import keyring

        return keyring.get_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
    except Exception:  # noqa: BLE001 — backends raise platform-specific errors
        return None


def delete_keychain_key() -> bool:
    """Remove the bundled-app API key from Keychain. Returns True if something was deleted."""
    if not _keychain_available():
        return False
    try:
        import keyring

        keyring.delete_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
        return True
    except keyring.errors.PasswordDeleteError:
        return False
    except Exception:  # noqa: BLE001
        return False


def _resolve_output_dir(toml_value: str | None) -> Path:
    if toml_value:
        return Path(toml_value).expanduser().resolve()
    cwd_output = Path.cwd() / "output"
    if cwd_output.exists():
        return cwd_output.resolve()
    return user_config_dir() / "output"


def resolve_config(*, load_dotenv: bool = True) -> Config:
    """Build a Config from all sources in precedence order."""
    if load_dotenv:
        _maybe_load_dotenv()

    toml_path = user_config_path()
    toml = _load_toml(toml_path)
    api_section = toml.get("api", {}) if isinstance(toml.get("api"), dict) else {}
    storage_section = toml.get("storage", {}) if isinstance(toml.get("storage"), dict) else {}
    ui_section = toml.get("ui", {}) if isinstance(toml.get("ui"), dict) else {}
    meta_section = toml.get("meta", {}) if isinstance(toml.get("meta"), dict) else {}
    updates_section = toml.get("updates", {}) if isinstance(toml.get("updates"), dict) else {}

    # Precedence: NARA_API_KEY env > macOS Keychain (only meaningful in the
    # PyInstaller-bundled .app) > TOML. Env stays the override of last resort
    # so power users can swap keys ad-hoc without touching Keychain.
    api_key = os.environ.get("NARA_API_KEY") or _read_keychain_key() or api_section.get("key")
    api_base_url = (
        os.environ.get("NARA_API_BASE_URL") or api_section.get("base_url") or DEFAULT_API_BASE_URL
    )
    try:
        default_rate = float(
            os.environ.get("NARA_DEFAULT_RATE") or api_section.get("default_rate") or DEFAULT_RATE
        )
    except (TypeError, ValueError):
        default_rate = DEFAULT_RATE

    output_dir = _resolve_output_dir(storage_section.get("output_dir"))

    server_host = ui_section.get("server_host", DEFAULT_SERVER_HOST)
    try:
        server_port = int(ui_section.get("server_port", DEFAULT_SERVER_PORT))
    except (TypeError, ValueError):
        server_port = DEFAULT_SERVER_PORT
    auto_open_browser = bool(ui_section.get("auto_open_browser", True))

    return Config(
        api_key=api_key,
        api_base_url=api_base_url if api_base_url.endswith("/") else api_base_url + "/",
        default_rate=default_rate,
        output_dir=output_dir,
        server_host=server_host,
        server_port=server_port,
        auto_open_browser=auto_open_browser,
        config_path=toml_path if toml_path.exists() else None,
        terms_acknowledged=bool(meta_section.get("nara_terms_acknowledged")),
        acknowledged_at=meta_section.get("acknowledged_at"),
        check_for_updates=bool(updates_section.get("check_on_startup", True)),
        raw_toml=toml,
    )


def write_config(
    *,
    api_key: str,
    output_dir: Path,
    default_rate: float = DEFAULT_RATE,
    server_host: str = DEFAULT_SERVER_HOST,
    server_port: int = DEFAULT_SERVER_PORT,
    auto_open_browser: bool = True,
    api_base_url: str = DEFAULT_API_BASE_URL,
    terms_acknowledged: bool = True,
    target: Path | None = None,
) -> Path:
    """Serialize a fresh config.toml. Returns the path written.

    Refuses to clobber by default? Caller decides — this writes unconditionally
    via an atomic temp+rename. ``nara init`` is the only caller and prompts
    before invoking us when a config already exists.
    """
    target = target or user_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    ack = (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if terms_acknowledged
        else None
    )

    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    lines = [
        "# nara-archive config — generated by `nara init`.",
        "# Edit by hand at your own risk; `nara init --reset` to start over.",
        "",
        "[api]",
        f'key = "{_esc(api_key)}"',
        f'base_url = "{_esc(api_base_url)}"',
        f"default_rate = {default_rate}",
        "",
        "[storage]",
        f'output_dir = "{_esc(str(output_dir))}"',
        "",
        "[ui]",
        f'server_host = "{_esc(server_host)}"',
        f"server_port = {server_port}",
        f"auto_open_browser = {'true' if auto_open_browser else 'false'}",
        "",
        "[meta]",
        f"config_version = {CONFIG_VERSION}",
        f"nara_terms_acknowledged = {'true' if terms_acknowledged else 'false'}",
    ]
    if ack:
        lines.append(f'acknowledged_at = "{ack}"')
    lines.append("")

    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(target)
    return target


def detect_legacy_env() -> Path | None:
    """If a project-local .env exists and ~/.nara/config.toml doesn't, return its path."""
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists() and not user_config_path().exists():
        return cwd_env
    return None
