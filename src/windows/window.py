"""pywebview window for Windows (no AppKit)."""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
import webbrowser
from typing import Callable


def wait_server(url: str, timeout: float = 45) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=1) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("API did not start")


class JsApi:
    window = None

    def show_about(self) -> None:
        webbrowser.open("https://3dwolf.ru")

    def open_url(self, url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def pick_folder(self) -> str | None:
        try:
            import webview

            win = self.window
            if win is None and webview.windows:
                win = webview.windows[0]
            if win is None:
                return None
            dialog = getattr(webview, "FOLDER_DIALOG", None)
            if dialog is None:
                try:
                    from webview import FileDialog

                    dialog = FileDialog.FOLDER
                except Exception:
                    return None
            result = win.create_file_dialog(dialog)
            if result and len(result) > 0:
                return str(result[0])
        except Exception:
            pass
        return None


def run_window(port: int, on_quit: Callable[[], None] | None = None) -> None:
    import webview

    base = f"http://127.0.0.1:{port}"
    wait_server(base)

    js_api = JsApi()
    window = webview.create_window(
        "TG Oxyfire Saver",
        url=base + "/",
        width=1180,
        height=780,
        min_size=(900, 640),
        background_color="#0e1621",
        text_select=True,
        js_api=js_api,
    )
    js_api.window = window

    def on_closing() -> bool:
        # Hide to tray instead of quitting
        try:
            window.hide()
        except Exception:
            pass
        return False

    window.events.closing += on_closing

    # Edge WebView2 is default on modern Windows
    webview.start(gui="edgechromium" if sys.platform == "win32" else None)
