"""Resolve installed .app bundle paths (no hardcoded user Desktop)."""

from __future__ import annotations

import os
from pathlib import Path

_APP_NAMES = (
    "TG Oxyfire Saver.app",
    "TG Video Saver.app",
)


def find_app_bundle() -> Path | None:
    env = os.environ.get("TG_OXYFIRE_APP")
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return p

    home = Path.home()
    candidates: list[Path] = []
    for name in _APP_NAMES:
        candidates.extend(
            [
                Path("/Applications") / name,
                home / "Applications" / name,
                home / "Desktop" / name,
            ]
        )
    for c in candidates:
        if c.is_dir():
            return c
    return None


def helper_app(name: str) -> Path | None:
    """name: TGSaverWindow.app | TGOxyfireMenu.app | TGSaverEngine.app"""
    root = find_app_bundle()
    if not root:
        return None
    p = root / "Contents" / "Helpers" / name
    return p if p.exists() else None
