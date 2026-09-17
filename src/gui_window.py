"""Окно приложения (pywebview) + запасной status item в том же процессе."""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
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
            "ApplicationVersion": "2.2.0",
            "Version": "2.2.0",
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
            with urllib.request.urlopen(url + "/api/health", timeout=1) as r:
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
    bridge = None

    def applicationShouldHandleReopen_hasVisibleWindows_(self, _app, _flag):
        if self.window is not None:
            try:
                self.window.show()
            except Exception:
                pass
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
            with urllib.request.urlopen(base + "/api/state", timeout=2) as r:
                st = json.loads(r.read().decode())
            data = json.dumps({"paused": not bool(st.get("paused"))}).encode()
            req = urllib.request.Request(
                base + "/api/pause",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=2)
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
            urllib.request.urlopen(req, timeout=2)
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

            with urllib.request.urlopen(
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

    try:
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        reopen = ReopenDelegate.alloc().init()
        app.setDelegate_(reopen)
        # Меню приложения: О программе
        main_menu = NSMenu.alloc().init()
        app_menu_item = NSMenuItem.alloc().init()
        main_menu.addItem_(app_menu_item)
        app.setMainMenu_(main_menu)
        app_menu = NSMenu.alloc().init()
        about = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"О программе {APP}", "showAbout:", ""
        )
        about.setTarget_(reopen)
        app_menu.addItem_(about)
        app_menu_item.setSubmenu_(app_menu)
    except Exception:
        reopen = None

    # Status item здесь — если helper заблокирован StatusKit
    status_bridge = install_status_item(port)

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
    if reopen is not None:
        reopen.window = window
        reopen.bridge = status_bridge

    def on_closing() -> bool:
        # Прячем, не убиваем — status item / helper остаются
        try:
            window.hide()
        except Exception:
            pass
        return False

    window.events.closing += on_closing
    webview.start()


if __name__ == "__main__":
    main()
