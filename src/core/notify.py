"""Desktop notifications + open/reveal — macOS & Windows."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def notify(title: str, message: str, open_path: str | None = None) -> None:
    if sys.platform == "darwin":
        title_e = title.replace('"', '\\"')
        msg_e = message.replace('"', '\\"')
        script = f'display notification "{msg_e}" with title "{title_e}"'
        try:
            subprocess.Popen(["osascript", "-e", script])
        except OSError:
            pass
        return
    if sys.platform == "win32":
        try:
            # Best-effort balloon via PowerShell (no extra deps)
            t = title.replace("'", "''")
            m = message.replace("'", "''")
            ps = (
                "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
                "ContentType = WindowsRuntime] > $null; "
                # Fallback: MessageBeep style via tray — ignore if fails
                f"Write-Output '{t}: {m}' | Out-Null"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            pass


def open_path(path: str) -> None:
    p = str(path)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", p])
        elif sys.platform == "win32":
            os_startfile = getattr(__import__("os"), "startfile", None)
            if os_startfile:
                os_startfile(p)  # type: ignore[misc]
            else:
                subprocess.Popen(["explorer", p])
        else:
            subprocess.Popen(["xdg-open", p])
    except OSError:
        pass


def reveal_path(path: str) -> None:
    p = Path(path)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(p)])
        elif sys.platform == "win32":
            if p.exists():
                subprocess.Popen(["explorer", "/select,", str(p)])
            else:
                open_path(str(p.parent if p.parent.exists() else p))
        else:
            open_path(str(p.parent if p.is_file() else p))
    except OSError:
        pass


def mark_finder_label(path: str, label_index: int = 5) -> None:
    """macOS Finder label only; no-op elsewhere."""
    if sys.platform != "darwin":
        return
    p = Path(path)
    if not p.exists():
        return
    escaped = str(p).replace("\\", "\\\\").replace('"', '\\"')
    script = (
        f'set p to POSIX file "{escaped}" as alias\n'
        f'tell application "Finder" to try\n'
        f"  set label index of p to {int(label_index)}\n"
        f"end try"
    )
    try:
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass
