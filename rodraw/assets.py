"""Locating bundled resource files.

Works both from a source checkout and from a PyInstaller build, where the
package directory is unpacked under sys._MEIPASS rather than next to the exe.
"""
from __future__ import annotations

import sys
from pathlib import Path


def resource_path(name: str) -> Path | None:
    """Absolute path to a file in rodraw/resources, or None if missing."""
    here = Path(__file__).resolve().parent
    candidates = [here / "resources" / name]
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidates.append(Path(bundle) / "rodraw" / "resources" / name)
        candidates.append(Path(bundle) / "resources" / name)
    for path in candidates:
        if path.exists():
            return path
    return None
