"""File locations that work both from source and from a PyInstaller bundle."""
from __future__ import annotations

import os
import sys

APP_NAME = "Lectern"
ORG_NAME = "Lectern"


def resource_dir() -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "lectern", "resources")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")


def resource(*parts: str) -> str:
    return os.path.join(resource_dir(), *parts)


def data_dir() -> str:
    """Per-user writable directory for the imported Bible and bookmarks."""
    from PySide6.QtCore import QStandardPaths

    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    d = os.path.join(base, APP_NAME) if base else os.path.join(os.path.expanduser("~"), ".lectern")
    os.makedirs(d, exist_ok=True)
    return d


def bible_db_path() -> str:
    return os.path.join(data_dir(), "rsv2ce.sqlite")
