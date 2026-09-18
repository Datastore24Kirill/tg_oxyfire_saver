"""Ротация app.log: ~5 МБ × 3 бэкапа."""

from __future__ import annotations

from pathlib import Path

MAX_BYTES = 5 * 1024 * 1024
BACKUPS = 3


def rotate_log(path: Path, max_bytes: int = MAX_BYTES, backups: int = BACKUPS) -> None:
    try:
        if not path.is_file() or path.stat().st_size < max_bytes:
            return
        oldest = path.with_name(f"{path.name}.{backups}")
        if oldest.exists():
            oldest.unlink()
        for i in range(backups - 1, 0, -1):
            src = path.with_name(f"{path.name}.{i}")
            dst = path.with_name(f"{path.name}.{i + 1}")
            if src.exists():
                src.rename(dst)
        path.rename(path.with_name(f"{path.name}.1"))
    except OSError:
        pass


def append_log(path: Path, line: str) -> None:
    try:
        rotate_log(path)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line if line.endswith("\n") else line + "\n")
    except OSError:
        pass
