from __future__ import annotations

import os
import sys
from pathlib import Path


def get_base_dir() -> Path:
    override = os.environ.get("STEAMTOOLS_MANAGER_BASE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_assets_dir() -> Path:
    override = os.environ.get("STEAMTOOLS_MANAGER_ASSETS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return get_base_dir()
