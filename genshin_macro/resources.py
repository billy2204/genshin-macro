"""Locate bundled data files (icon) both from source and inside a PyInstaller build."""
from __future__ import annotations

import sys
from pathlib import Path


def resource_path(rel: str) -> Path:
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parents[1]
    return root / Path(rel)
