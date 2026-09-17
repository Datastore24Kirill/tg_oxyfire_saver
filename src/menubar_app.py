"""Menu bar: NSStatusBar + киберпанк глиф + всегда видимый текст TG."""

from __future__ import annotations

import subprocess
import traceback
from pathlib import Path

import rumps
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSImage,
    NSImageLeft,
    NSMenu,
    NSMenuItem,
    NSObject,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSTimer
from PyObjCTools import AppHelper

ROOT = Path(__file__).resolve().parent
# Цветной глиф заметнее template-силуэта (не теряется в переполнении menu bar)
MENU_COLOR = ROOT / "assets" / "menubarColor@2x.png"
MENU_COLOR_1X = ROOT / "assets" / "menubarColor.png"
MENU_TEMPLATE_2X = ROOT / "assets" / "menubarTemplate@2x.png"
MENU_TEMPLATE = ROOT / "assets" / "menubarTemplate.png"
LOG = ROOT / "app.log"
try:
    from core.app_paths import helper_app

    WINDOW_APP = helper_app("TGSaverWindow.app") or Path(
        "/Applications/TG Oxyfire Saver.app/Contents/Helpers/TGSaverWindow.app"
    )
except Exception:
    WINDOW_APP = Path(
        "/Applications/TG Oxyfire Saver.app/Contents/Helpers/TGSaverWindow.app"
    )


def _log(msg: str) -> None:
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


class MenuTarget(NSObject):
    bridge = None

    def openWindow_(self, _sender):
        self.bridge.open_window()

    def togglePause_(self, _sender):
        self.bridge.toggle_pause()

    def toggleClipboard_(self, _sender):
        self.bridge.toggle_clipboard()

    def stopWatchers_(self, _sender):
        self.bridge.stop_watchers()

    def openFolder_(self, _sender):
        self.bridge.open_folder()

    def quitApp_(self, _sender):
        self.bridge.quit_app()

    def tick_(self, _timer):
        self.bridge.tick()


class MenuBarController:
    def __init__(self, service, port: int, open_window_on_start: bool = False) -> None:
        self.service = service
        self.port = port
        self._opened_once = not open_window_on_start

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        try:
            app.finishLaunching()
        except Exception:
            pass

        self.status = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        # behavior=0: нельзя выкинуть item в «›» / удалить с menu bar
        try:
            self.status.setBehavior_(0)
        except Exception:
            pass
        try:
            self.status.setVisible_(True)
        except Exception:
            pass

        button = self.status.button()
        img = self._load_icon()
        if button is not None:
            if img is not None:
                button.setImage_(img)
                try:
                    button.setImagePosition_(NSImageLeft)
                except Exception:
                    pass
            button.setTitle_(" TG")
            button.setToolTip_("TG Video Saver")
            try:
                button.setAppearsDisabled_(False)
            except Exception:
                pass
            _log(f"menubar status item created icon={img is not None}")
        else:
            _log("menubar ERROR: status.button() is None")

        self.target = MenuTarget.alloc().init()
        self.target.bridge = self

        self.menu = NSMenu.alloc().init()
        self._item_open = self._add("Открыть окно", "openWindow:")
        self._item_pause = self._add("Пауза очереди", "togglePause:")
        self._item_clip = self._add("Буфер: выкл", "toggleClipboard:")
        self._item_watch = self._add("Сторожа: стоп все", "stopWatchers:")
        self._item_folder = self._add("Открыть папку", "openFolder:")
        self.menu.addItem_(NSMenuItem.separatorItem())
        self._add("Выход", "quitApp:")
        self.status.setMenu_(self.menu)

        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            2.0, self.target, "tick:", None, True
        )

        try:
            rumps.notification(
                title="TG Video Saver",
                subtitle="",
                message="Menu bar: стрелка + TG",
            )
        except Exception as e:
            _log(f"menubar notify fail: {e}")

        self.tick()
        if open_window_on_start:
            self.open_window()

    def _load_icon(self):
        # 1) цветной киберпанк (не template) — всегда читается глазом
        for path, is_template in (
            (MENU_COLOR, False),
            (MENU_COLOR_1X, False),
            (MENU_TEMPLATE_2X, True),
            (MENU_TEMPLATE, True),
        ):
            if not path.exists():
                continue
            img = NSImage.alloc().initWithContentsOfFile_(str(path))
            if img is None:
                _log(f"menubar icon load fail: {path}")
                continue
            img.setTemplate_(is_template)
            img.setSize_((18.0, 18.0))
            _log(f"menubar icon loaded: {path.name} template={is_template}")
            return img
        _log("menubar icon missing: no assets")
        return None

    def _add(self, title: str, action: str):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            title, action, ""
        )
        item.setTarget_(self.target)
        self.menu.addItem_(item)
        return item

    def tick(self) -> None:
        try:
            st = self.service.snapshot()
            button = self.status.button()
            if button is not None:
                stats = st.get("stats") or {}
                active = stats.get("active", 0)
                queued = stats.get("queued", 0)
                if not st.get("ready"):
                    label = " TG…"
                elif active:
                    label = f" ↓{active}"
                elif queued:
                    label = f" ·{queued}"
                elif st.get("clipboard_mode"):
                    label = " B"
                else:
                    label = " TG"
                button.setTitle_(label)
                try:
                    self.status.setVisible_(True)
                except Exception:
                    pass
            self._item_clip.setTitle_(
                "Буфер: вкл" if st.get("clipboard_mode") else "Буфер: выкл"
            )
            self._item_pause.setTitle_(
                "Продолжить очередь" if st.get("paused") else "Пауза очереди"
            )
        except Exception:
            pass

        if not self._opened_once:
            self._opened_once = True

    def open_window(self) -> None:
        # Без -n: один экземпляр окна / одна иконка в Dock
        subprocess.Popen(
            ["/usr/bin/open", str(WINDOW_APP), "--args", str(self.port)],
        )

    def toggle_pause(self) -> None:
        st = self.service.snapshot()
        self.service.set_paused(not st.get("paused"))

    def toggle_clipboard(self) -> None:
        cur = bool(self.service.store.get_setting("clipboard_mode", False))
        self.service.update_settings({"clipboard_mode": not cur})

    def stop_watchers(self) -> None:
        self.service.stop_all_watchers()
        try:
            rumps.notification(
                title="TG Video Saver",
                subtitle="",
                message="Сторожа остановлены",
            )
        except Exception:
            pass

    def open_folder(self) -> None:
        self.service.open_folder()

    def quit_app(self) -> None:
        subprocess.run(["pkill", "-f", "gui_window.py"], check=False)
        AppHelper.stopEventLoop()


def run_menubar(service, port: int) -> None:
    global _CONTROLLER  # noqa: PLW0603
    try:
        try:
            from Foundation import NSBundle

            b = NSBundle.mainBundle()
            _log(
                f"menubar bundle path={b.bundlePath() if b else None} "
                f"id={b.bundleIdentifier() if b else None}"
            )
        except Exception as e:
            _log(f"menubar bundle probe fail: {e}")
        # Окно уже открывает app_main — не дублируем (иначе 2–3 иконки в Dock)
        _CONTROLLER = MenuBarController(service, port, open_window_on_start=False)
        AppHelper.runEventLoop()
    except Exception:
        _log("menubar CRASH:\n" + traceback.format_exc())
        raise


_CONTROLLER = None
