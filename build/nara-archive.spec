# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the nara-archive macOS .app bundle.

Hand-written (not auto-generated) so the BUNDLE step's Info.plist stays
under version control. Universal2 output only happens when the host
Python interpreter is itself universal2-built — use the python.org
installer in CI, NOT homebrew Python.

Local build (after `pip install -e ".[mac]"`):

    pyinstaller build/nara-archive.spec

Output: dist/NARA Archive.app
"""

from pathlib import Path

# Resolve relative to the project root regardless of where PyInstaller is
# invoked from. SPECPATH is set by PyInstaller to the directory containing
# this spec file.
ROOT = Path(SPECPATH).parent.resolve()  # noqa: F821 — SPECPATH is injected by PyInstaller

# --- version + build number ----------------------------------------------

# Read the package version straight out of src/ to keep CFBundle* in sync.
ABOUT: dict[str, str] = {}
exec((ROOT / "src" / "nara" / "__init__.py").read_text(), ABOUT)
VERSION = ABOUT.get("__version__", "0.0.0")
BUILD_NUMBER = ABOUT.get("__version__", "0.0.0").replace(".", "")

# --- inputs --------------------------------------------------------------

# Entry script: the menubar wrapper, NOT cli.py. cli.py stays the pip-install
# entry point and is unbundled.
ENTRY = str(ROOT / "src" / "nara" / "macapp" / "main.py")

# Bundle every static asset under src/nara/server/static and src/nara/data
# verbatim — PyInstaller's auto-discovery only catches importable Python.
datas = []
for sub in ("server/static", "data"):
    src_root = ROOT / "src" / "nara" / sub
    for path in src_root.rglob("*"):
        if path.is_file():
            datas.append((str(path), f"nara/{sub}/{path.relative_to(src_root).parent}"))

# --- hidden imports ------------------------------------------------------
# PyInstaller's stdlib + entry-point traversal catches most things, but
# uvicorn ships a few worker / protocol modules that aren't imported until
# runtime via string names. Listing them defensively avoids ModuleNotFound
# at first launch on a clean machine.

hiddenimports = [
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.loops.uvloop",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.logging",
    # FastAPI / pydantic dynamic imports
    "fastapi",
    "fastapi.encoders",
    "pydantic_core._pydantic_core",
    # Our routes are imported through string paths in the FastAPI factory;
    # explicit listing here is belt-and-braces.
    "nara.server.routes.search",
    "nara.server.routes.jobs",
    "nara.server.routes.library",
    "nara.server.routes.config",
    "nara.server.routes.setup",
    "nara.server.routes.presets",
    # macOS-only deps
    "rumps",
    "keyring",
    "keyring.backends.macOS",
]

# --- PyInstaller graph ---------------------------------------------------

block_cipher = None  # noqa: F841 — required name in PyInstaller specs

a = Analysis(  # noqa: F821 — PyInstaller-injected name
    [ENTRY],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Reduce bundle size — these aren't needed at runtime.
        "tkinter",
        "matplotlib",
        "pytest",
        "ruff",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="nara-archive",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # no Terminal window
    disable_windowed_traceback=False,
    target_arch="universal2",  # requires a universal2 Python interpreter
    codesign_identity=None,    # signing handled by build/sign-and-notarize.sh
    entitlements_file=None,
    icon=str(ROOT / "build" / "nara-archive.icns") if (ROOT / "build" / "nara-archive.icns").exists() else None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="nara-archive",
)

# --- BUNDLE: produce the .app ---

info_plist = {
    "LSUIElement": True,            # menubar app, no Dock icon
    "CFBundleShortVersionString": VERSION,
    "CFBundleVersion": BUILD_NUMBER,
    "CFBundleIdentifier": "dev.cramm.nara-archive",
    "CFBundleName": "NARA Archive",
    "CFBundleDisplayName": "NARA Archive",
    "NSHumanReadableCopyright": "Copyright © 2026 Christopher Ramm. MIT License.",
    "LSMinimumSystemVersion": "11.0",
    "NSHighResolutionCapable": True,
    "NSAppTransportSecurity": {
        # FastAPI server lives on 127.0.0.1 — required for the browser to
        # talk to it from the same machine.
        "NSAllowsLocalNetworking": True,
    },
}

app = BUNDLE(  # noqa: F821
    coll,
    name="NARA Archive.app",
    icon=str(ROOT / "build" / "nara-archive.icns") if (ROOT / "build" / "nara-archive.icns").exists() else None,
    bundle_identifier="dev.cramm.nara-archive",
    info_plist=info_plist,
)
