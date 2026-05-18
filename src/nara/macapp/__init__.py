"""macOS-only menubar app wrapper around `nara serve`.

Imported only when the program runs inside the PyInstaller-bundled ``.app``
(or when a developer explicitly invokes ``python -m nara.macapp.main``).
The submodule ``main`` pulls in ``rumps`` and ``PyObjC``, which are only
installed on Darwin via the ``sys_platform == 'darwin'`` markers in
pyproject — keep all rumps imports inside ``main``, never at package load.
"""

from __future__ import annotations
