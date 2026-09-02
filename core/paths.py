"""Filesystem roots that work both from source and from a frozen build.

PyInstaller ``--onefile`` unpacks bundled files into a temporary
``sys._MEIPASS`` directory that is read-only and disappears on exit, while
the working data (config, logs, profiles, captured templates) must live
next to the executable. These helpers give every module one place to ask.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Read-only bundled assets (icons, fonts, shipped default config)."""
    if is_frozen():
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base)
        return Path(sys.executable).resolve().parent
    return _SOURCE_ROOT


def data_root() -> Path:
    """Writable app data (config, logs, profiles, user templates)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return _SOURCE_ROOT


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def data_path(*parts: str) -> Path:
    return data_root().joinpath(*parts)
