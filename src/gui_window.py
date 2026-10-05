"""Окно приложения (pywebview) + запасной status item в том же процессе."""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request

LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
from pathlib import Path

import webview
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSImage,
    NSImageLeft,
    NSMenu,
    NSMenuItem,
    NSObject,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSTimer

SUPPORT = Path.home() / "Library" / "Application Support" / "TGVideoSaver"
ICON_COLOR = SUPPORT / "assets" / "menubarColor@2x.png"
ICON_APP = SUPPORT / "assets" / "icon.png"
AUTOSAVE = "TGSaverWindowIcon"
APP = "TG Oxyfire Saver"
AUTHOR = "Ковыршин Кирилл"
COPYRIGHT = "© 2016 Ковыршин Кирилл"
LINKS = (
    "https://3dwolf.ru",
    "https://datastore24.ru",
    "https://myfabric.ru",
)


def _app_version() -> str:
    try:
        from core.version import APP_VERSION

        return APP_VERSION
    except Exception:
        pass
    for path in (SUPPORT / "VERSION", Path(__file__).resolve().parents[1] / "VERSION"):
        try:
            if path.is_file():
                line = path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
                if line:
                    return line.lstrip("vV")
        except OSError:
            continue
    return "2.6.2"


_APP_VERSION = _app_version()


def _log_window(msg: str) -> None:
    try:
        from core.logutil import append_log

        append_log(SUPPORT / "app.log", f"window: {msg}")
    except Exception:
        pass


def reveal_window(window) -> None:
    """Показать окно и вывести приложение на передний план."""
    try:
        window.show()
    except Exception as e:
        _log_window(f"show failed: {e}")
    try:
        from AppKit import NSApp, NSApplicationActivationPolicyRegular

        NSApp.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        NSApp.unhide_(None)
        NSApp.activateIgnoringOtherApps_(True)
        for w in list(NSApp.windows()):
            try:
                if w.canBecomeKeyWindow():
                    w.makeKeyAndOrderFront_(None)
            except Exception:
                pass
    except Exception as e:
        _log_window(f"activate failed: {e}")


def show_about_panel() -> None:
    """Стандартное macOS-окно «О программе» с автором и ссылками."""
    try:
        from AppKit import (  # noqa: WPS433
            NSApp,
            NSAttributedString,
            NSColor,
            NSFont,
            NSFontAttributeName,
            NSForegroundColorAttributeName,
            NSImage,
            NSLinkAttributeName,
            NSMutableParagraphStyle,
            NSParagraphStyleAttributeName,
            NSTextAlignmentCenter,
        )
        from Foundation import NSMutableAttributedString

        style = NSMutableParagraphStyle.alloc().init()
        style.setAlignment_(NSTextAlignmentCenter)
        base = {
            NSFontAttributeName: NSFont.systemFontOfSize_(11),
            NSForegroundColorAttributeName: NSColor.labelColor(),
            NSParagraphStyleAttributeName: style,
        }
        credits = NSMutableAttributedString.alloc().initWithString_attributes_(
            f"Автор: {AUTHOR}\n{COPYRIGHT}\n\n", base
        )
        for i, url in enumerate(LINKS):
            label = url.replace("https://", "") + ("\n" if i < len(LINKS) - 1 else "")
            link_attrs = dict(base)
            link_attrs[NSLinkAttributeName] = url
            link_attrs[NSForegroundColorAttributeName] = NSColor.linkColor()
            piece = NSAttributedString.alloc().initWithString_attributes_(
                label, link_attrs
            )
            credits.appendAttributedString_(piece)

        opts = {
            "ApplicationName": APP,
            "ApplicationVersion": _APP_VERSION,
            "Version": _APP_VERSION,
            "Credits": credits,
            "Copyright": COPYRIGHT,
        }
        if ICON_APP.is_file():
            img = NSImage.alloc().initWithContentsOfFile_(str(ICON_APP))
            if img is not None:
                opts["ApplicationIcon"] = img
        NSApp.orderFrontStandardAboutPanelWithOptions_(opts)
        NSApp.activateIgnoringOtherApps_(True)
    except Exception:
        pass


class JsApi:
    window = None

    def show_about(self) -> None:
        show_about_panel()

    def open_url(self, url: str) -> None:
        try:
            subprocess.Popen(["/usr/bin/open", url])
        except Exception:
            pass

    def pick_folder(self) -> str | None:
        """Системный диалог выбора папки сохранений."""
        try:
            import webview

            win = self.window
            if win is None and webview.windows:
                win = webview.windows[0]
            if win is None:
                return None
            result = win.create_file_dialog(webview.FOLDER_DIALOG)
            if result and len(result) > 0:
                return str(result[0])
        except Exception:
            pass
        # Fallback NSOpenPanel on main thread
        try:
            from AppKit import NSOpenPanel, NSApp
            from Foundation import NSRunLoop, NSDate

            panel = NSOpenPanel.openPanel()
            panel.setCanChooseFiles_(False)
            panel.setCanChooseDirectories_(True)
            panel.setAllowsMultipleSelection_(False)
            panel.setCanCreateDirectories_(True)
            panel.setMessage_("Папка для сохранения видео и фото")
            # Ensure app can show modal
            NSApp.activateIgnoringOtherApps_(True)
            if panel.runModal() == 1:  # NSModalResponseOK
                urls = panel.URLs()
                if urls and len(urls) > 0:
                    return str(urls[0].path())
        except Exception:
            pass
        return None


def wait_server(url: str, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with LOCAL_HTTP.open(url + "/api/health", timeout=1) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("API не поднялся")


def _force_prefs() -> None:
    bid = "com.oxyfire.tgoxysaver.window"
    for domain in (bid, "com.apple.controlcenter"):
        for key in (
            f"NSStatusItem Visible {AUTOSAVE}",
            f"NSStatusItem VisibleCC {AUTOSAVE}",
        ):
            subprocess.run(
                ["defaults", "write", domain, key, "-bool", "true"],
                check=False,
                capture_output=True,
            )
        subprocess.run(
            [
                "defaults",
                "write",
                domain,
                f"NSStatusItem Preferred Position {AUTOSAVE}",
                "-float",
                "470",
            ],
            check=False,
            capture_output=True,
        )


class ReopenDelegate(NSObject):
    window = None

    def applicationShouldHandleReopen_hasVisibleWindows_(self, _app, _flag):
        if self.window is not None:
            reveal_window(self.window)
        return True

    def applicationShouldTerminate_(self, _app):
        return True

    def showAbout_(self, _sender):
        show_about_panel()


class StatusBridge(NSObject):
    port = 8765
    status = None
    item_pause = None

    def openWindow_(self, _s):
        # no-op: окно уже здесь; show via reopen
        pass

    def togglePause_(self, _s):
        try:
            import json

            base = f"http://127.0.0.1:{self.port}"
            with LOCAL_HTTP.open(base + "/api/state", timeout=2) as r:
                st = json.loads(r.read().decode())
            data = json.dumps({"paused": not bool(st.get("paused"))}).encode()
            req = urllib.request.Request(
                base + "/api/pause",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            LOCAL_HTTP.open(req, timeout=2)
        except Exception:
            pass

    def openFolder_(self, _s):
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/open_folder",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            LOCAL_HTTP.open(req, timeout=2)
        except Exception:
            pass

    def openSettings_(self, _s):
        for url in (
            "x-apple.systempreferences:com.apple.MenuBarSettings",
            "x-apple.systempreferences:com.apple.ControlCenter-Settings.extension",
        ):
            try:
                subprocess.Popen(["/usr/bin/open", url])
                return
            except Exception:
                continue

    def tick_(self, _t):
        try:
            import json

            with LOCAL_HTTP.open(
                f"http://127.0.0.1:{self.port}/api/state", timeout=2
            ) as r:
                st = json.loads(r.read().decode())
            paused = bool(st.get("paused"))
            if self.item_pause is not None:
                self.item_pause.setTitle_(
                    "Продолжить очередь" if paused else "Пауза очереди"
                )
            stats = st.get("stats") or {}
            active = int(stats.get("active") or 0)
            queued = int(stats.get("queued") or 0)
            title = "TG"
            if not st.get("ready"):
                title = "TG…"
            elif active:
                title = f"TG↓{active}"
            elif queued:
                title = f"TG·{queued}"
            btn = self.status.button() if self.status else None
            if btn is not None:
                btn.setTitle_(title)
                try:
                    self.status.setVisible_(True)
                except Exception:
                    pass
        except Exception:
            pass


def install_status_item(port: int) -> StatusBridge | None:
    """Отключено: второй status item путает StatusKit. Иконка — только menu helper."""
    return None


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    base = f"http://127.0.0.1:{port}"
    wait_server(base)

    js_api = JsApi()
    _log_window(f"creating window port={port}")
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
    _log_window("window created")

    def on_closing() -> bool:
        # Закрытие завершает процесс окна. Следующий клик по иконке
        # запускает его заново и показывает экран. Прятать окно нельзя:
        # Dock-иконка остаётся, а macOS не вызывает show() сама.
        return True

    window.events.closing += on_closing

    def on_started() -> None:
        def _on_main() -> None:
            reveal_window(window)
            _log_window("revealed")

        try:
            from PyObjCTools import AppHelper

            AppHelper.callAfter(_on_main)
        except Exception as e:
            _log_window(f"callAfter: {e}")
            _on_main()

    webview.start(func=on_started)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log_window(f"fatal: {e}")
        raise
