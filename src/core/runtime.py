"""Runtime paths: Application Support (macOS) / APPDATA (Windows)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


def support_dir() -> Path:
    env = os.environ.get("TG_OXYFIRE_SUPPORT")
    if env:
        return Path(env).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return base / "TGVideoSaver"
    return Path.home() / "Library" / "Application Support" / "TGVideoSaver"


def resource_dir() -> Path:
    """Bundled read-only assets (gui, icons) when frozen; else source tree."""
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # src/ when running from repo
    return Path(__file__).resolve().parent.parent


def ensure_support_layout() -> Path:
    """Create support dir and seed gui/assets/.env from the bundle if missing."""
    root = support_dir()
    root.mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    (root / "core" / "thumbs").mkdir(parents=True, exist_ok=True)

    res = resource_dir()
    for name in ("gui", "assets"):
        src = res / name
        dst = root / name
        if src.is_dir() and not dst.exists():
            shutil.copytree(src, dst)
        elif src.is_dir() and name == "gui":
            # Keep gui files updated from bundle on Windows builds
            if is_frozen():
                for f in src.rglob("*"):
                    if f.is_file():
                        rel = f.relative_to(src)
                        target = dst / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, target)

    env_dst = root / ".env"
    if not env_dst.exists():
        for candidate in (res / ".env.example", res.parent / ".env.example"):
            if candidate.is_file():
                shutil.copy2(candidate, env_dst)
                break
        else:
            env_dst.write_text(
                "API_ID=2040\nAPI_HASH=b18441a1ff607e10a989891a5462e627\n",
                encoding="utf-8",
            )
    return root


def system_name() -> str:
    if sys.platform == "win32":
        return "Windows"
    if sys.platform == "darwin":
        return "macOS"
    return sys.platform
