#!/usr/bin/env python3
"""Точка входа: сервис + API + menu bar."""

from __future__ import annotations

import fcntl
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from api_server import create_app
from core.app_paths import helper_app
from core.clipboard_watch import ClipboardWatcher
from core.service import DownloadService

_LOCK_FH = None
PORT_FILE = ROOT / ".api_port"
WINDOW_APP = helper_app("TGSaverWindow.app") or Path(
    "/Applications/TG Oxyfire Saver.app/Contents/Helpers/TGSaverWindow.app"
)
MENU_APP = helper_app("TGOxyfireMenu.app") or Path(
    "/Applications/TG Oxyfire Saver.app/Contents/Helpers/TGOxyfireMenu.app"
)
LOG = ROOT / "app.log"


def _log(msg: str) -> None:
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def acquire_single_instance() -> bool:
    global _LOCK_FH
    path = ROOT / ".instance.lock"
    _LOCK_FH = open(path, "w", encoding="utf-8")
    try:
        fcntl.flock(_LOCK_FH.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _LOCK_FH.write(str(os.getpid()))
        _LOCK_FH.flush()
        return True
    except BlockingIOError:
        return False


def read_port() -> int | None:
    try:
        return int(PORT_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def write_port(port: int) -> None:
    PORT_FILE.write_text(str(port) + "\n", encoding="utf-8")


def api_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def open_window(port: int) -> None:
    # Без -n — не плодим окна и иконки в Dock
    subprocess.Popen(
        ["/usr/bin/open", str(WINDOW_APP), "--args", str(port)],
    )


def menu_host_alive(port: int) -> bool:
    """Уже есть menu_host на этом порту? Повторный open убивает иконку на Tahoe."""
    try:
        out = subprocess.check_output(["/bin/ps", "-axo", "args"], text=True, errors="replace")
    except Exception:
        return False
    needle = f"menu_host.py {port}"
    return any(needle in line for line in out.splitlines())


def open_menubar(port: int) -> None:
    """Отдельный LSUIElement helper — только menu bar (без webview)."""
    if not MENU_APP.exists():
        _log(f"menu app missing: {MENU_APP}")
        return
    if menu_host_alive(port):
        _log(f"menu_host already running port={port} — skip relaunch")
        return
    subprocess.Popen(
        ["/usr/bin/open", str(MENU_APP), "--args", str(port)],
    )


def handoff_to_running() -> bool:
    """Уже запущено: открыть окно существующего процесса (иначе клик по .app «молчит»)."""
    port = read_port()
    if port and api_alive(port):
        _log(f"handoff open window port={port}")
        open_window(port)
        # НЕ трогаем menu bar — повторный launch уводит иконку в StatusKit
        return True
    # fallback: известные порты
    for p in (8765, port or 0):
        if p and api_alive(p):
            _log(f"handoff fallback port={p}")
            open_window(p)
            return True
    return False


def free_port() -> int:
    preferred = 8765
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])


def main() -> None:
    if not acquire_single_instance():
        if not handoff_to_running():
            _log("lock held but API dead — kill stale and tell user to retry")
            # Снять мёртвый lock: старый процесс жив без API
            try:
                PORT_FILE.unlink(missing_ok=True)
            except Exception:
                pass
        return

    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except Exception:
        pass

    _log(f"\n=== start {datetime.now().isoformat(timespec='seconds')} ===")

    import logging

    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    logging.getLogger("flask").setLevel(logging.ERROR)
    cli = sys.modules.get("flask.cli")
    if cli is not None:
        cli.show_server_banner = lambda *args, **kwargs: None  # type: ignore[attr-defined]

    service = DownloadService()
    service.start()

    clip = ClipboardWatcher(service)
    service.clipboard = clip
    clip.start()

    port = free_port()
    write_port(port)
    app = create_app(service)

    def run_api() -> None:
        app.run(
            host="127.0.0.1",
            port=port,
            threaded=True,
            use_reloader=False,
        )

    threading.Thread(target=run_api, name="api", daemon=True).start()
    _log(f"api http://127.0.0.1:{port}")

    open_window(port)
    open_menubar(port)
    _log("engine alive; window + dedicated menubar helper")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
