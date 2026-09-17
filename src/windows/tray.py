"""System tray for Windows (pystray)."""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path
from typing import Callable


class TrayController:
    def __init__(self, port: int) -> None:
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self._icon = None
        self._thread: threading.Thread | None = None
        self._quit_cb: Callable[[], None] | None = None

    def _api(self, path: str, method: str = "GET", body: dict | None = None) -> dict:
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self.base + path, data=data, headers=headers, method=method
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read().decode())

    def _icon_path(self) -> Path:
        from core.runtime import resource_dir, support_dir

        for p in (
            support_dir() / "assets" / "icon.png",
            resource_dir() / "assets" / "icon.png",
            support_dir() / "gui" / "icon.png",
            resource_dir() / "gui" / "icon.png",
        ):
            if p.is_file():
                return p
        return support_dir() / "assets" / "icon.png"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="tray", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            import pystray
            from PIL import Image
        except Exception:
            return

        path = self._icon_path()
        try:
            image = Image.open(path)
        except Exception:
            image = Image.new("RGB", (64, 64), color=(42, 171, 238))

        menu = pystray.Menu(
            pystray.MenuItem("Open / Открыть", self._show_window, default=True),
            pystray.MenuItem("Pause queue / Пауза", self._toggle_pause),
            pystray.MenuItem("Open folder / Папка", self._open_folder),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit / Выход", self._quit),
        )
        self._icon = pystray.Icon("TG Oxyfire Saver", image, "TG Oxyfire Saver", menu)
        self._icon.run()

    def _show_window(self, _icon=None, _item=None) -> None:
        try:
            import webview

            if webview.windows:
                webview.windows[0].show()
                webview.windows[0].restore()
        except Exception:
            pass

    def _toggle_pause(self, _icon=None, _item=None) -> None:
        try:
            st = self._api("/api/state")
            self._api("/api/pause", "POST", {"paused": not bool(st.get("paused"))})
        except Exception:
            pass

    def _open_folder(self, _icon=None, _item=None) -> None:
        try:
            self._api("/api/open_folder", "POST", {})
        except Exception:
            pass

    def _quit(self, _icon=None, _item=None) -> None:
        self.quit_app()

    def quit_app(self) -> None:
        try:
            if self._icon is not None:
                self._icon.stop()
        except Exception:
            pass
        try:
            import webview

            for w in list(webview.windows):
                try:
                    w.destroy()
                except Exception:
                    pass
        except Exception:
            pass
        # Hard exit — download threads are daemon-ish via process kill
        import os

        os._exit(0)
