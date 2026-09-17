"""Слежение за буфером обмена (только при включённом режиме)."""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from core.links import LINK_RE

if TYPE_CHECKING:
    from core.service import DownloadService


def _clipboard_text() -> str:
    try:
        r = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=2
        )
        return r.stdout or ""
    except Exception:
        return ""


class ClipboardWatcher:
    def __init__(self, service: DownloadService) -> None:
        self.service = service
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last = ""

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._last = _clipboard_text().strip()
        self._thread = threading.Thread(target=self._loop, name="clip", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self.service.store.get_setting("clipboard_mode", False):
                    text = _clipboard_text().strip()
                    if text and text != self._last and LINK_RE.search(text):
                        self._last = text
                        self.service.add_text(text, source="clipboard")
                    elif text:
                        self._last = text
                else:
                    self._last = _clipboard_text().strip()
            except Exception:
                pass
            time.sleep(0.8)
