"""Уведомления macOS."""

from __future__ import annotations

import subprocess
from pathlib import Path


def notify(title: str, message: str, open_path: str | None = None) -> None:
    """Простое уведомление через osascript (без отдельного permission dance)."""
    title_e = title.replace('"', '\\"')
    msg_e = message.replace('"', '\\"')
    script = f'display notification "{msg_e}" with title "{title_e}"'
    try:
        subprocess.Popen(["osascript", "-e", script])
    except OSError:
        pass
    if open_path and Path(open_path).exists():
        # не открываем автоматически — только notify; open по клику из UI
        pass


def open_path(path: str) -> None:
    try:
        subprocess.Popen(["open", path])
    except OSError:
        pass


def reveal_path(path: str) -> None:
    try:
        subprocess.Popen(["open", "-R", path])
    except OSError:
        pass


def mark_finder_label(path: str, label_index: int = 5) -> None:
    """Цветная метка Finder (5=purple) — легче найти скачанное."""
    p = Path(path)
    if not p.exists():
        return
    # Finder label via AppleScript; ignore failures (iCloud/permissions)
    escaped = str(p).replace("\\", "\\\\").replace('"', '\\"')
    script = (
        f'set p to POSIX file "{escaped}" as alias\n'
        f'tell application "Finder" to try\n'
        f'  set label index of p to {int(label_index)}\n'
        f'end try'
    )
    try:
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass
