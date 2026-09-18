"""Windows entry: API + system tray + pywebview in one process."""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
from datetime import datetime
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _log(msg: str) -> None:
    try:
        from core.logutil import append_log
        from core.runtime import support_dir

        append_log(support_dir() / "app.log", msg)
    except OSError:
        pass


def free_port(preferred: int = 8765) -> int:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])


def acquire_single_instance() -> bool:
    from core.runtime import support_dir

    support_dir().mkdir(parents=True, exist_ok=True)
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.CreateMutexW(None, False, "Global\\TGOxyfireSaverSingleInstance")
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return False
        acquire_single_instance._handle = handle  # type: ignore[attr-defined]
        return True
    except Exception:
        path = support_dir() / ".instance.lock"
        try:
            import msvcrt

            fh = open(path, "a+b")
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            acquire_single_instance._fh = fh  # type: ignore[attr-defined]
            return True
        except Exception:
            return False


def main() -> None:
    from core.runtime import ensure_support_layout, support_dir

    root = ensure_support_layout()
    os.chdir(root)

    if not acquire_single_instance():
        _log("another instance running — exit")
        return

    _log(f"\n=== win start {datetime.now().isoformat(timespec='seconds')} ===")

    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    logging.getLogger("flask").setLevel(logging.ERROR)
    cli = sys.modules.get("flask.cli")
    if cli is not None:
        cli.show_server_banner = lambda *args, **kwargs: None  # type: ignore[attr-defined]

    from api_server import create_app
    from core.clipboard_watch import ClipboardWatcher
    from core.service import DownloadService
    from windows.tray import TrayController
    from windows.window import run_window

    service = DownloadService()
    service.start()
    clip = ClipboardWatcher(service)
    service.clipboard = clip
    clip.start()

    port = free_port()
    (support_dir() / ".api_port").write_text(str(port) + "\n", encoding="utf-8")
    app = create_app(service)

    def run_api() -> None:
        app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)

    threading.Thread(target=run_api, name="api", daemon=True).start()
    _log(f"api http://127.0.0.1:{port}")

    tray = TrayController(port=port)
    tray.start()
    run_window(port, on_quit=tray.quit_app)


if __name__ == "__main__":
    main()
