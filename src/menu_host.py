"""Menu bar: создать ОДИН раз и не трогать (recreate на Tahoe убивает иконку)."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.request
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

SUPPORT = Path.home() / "Library" / "Application Support" / "TGVideoSaver"
LOG = SUPPORT / "app.log"
# Цветная иконка заметнее template (на тёмной полосе template иногда «исчезает»)
ICON_COLOR = SUPPORT / "assets" / "menubarColor@2x.png"
ICON_COLOR1 = SUPPORT / "assets" / "menubarColor.png"
ICON2 = SUPPORT / "assets" / "menubarTemplate@2x.png"
ICON1 = SUPPORT / "assets" / "menubarTemplate.png"
APP = "TG Video Saver"
AUTOSAVE = "TGVideoSaver"


def _force_visible_prefs() -> None:
    """Tahoe: Visible + VisibleCC под тем же bid, что в System Settings."""
    import subprocess

    bid = "com.oxyfire.tgvideosaver"
    for domain in (bid, "com.apple.controlcenter"):
        for key in (
            f"NSStatusItem Visible {AUTOSAVE}",
            f"NSStatusItem VisibleCC {AUTOSAVE}",
            "NSStatusItem Visible Item-0",
            "NSStatusItem VisibleCC Item-0",
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
                "480",
            ],
            check=False,
            capture_output=True,
        )


def _repair_statuskit() -> bool:
    """Control Center периодически ставит menuItemLocations=org.python.python — чиним."""
    try:
        import plistlib
        import shutil

        cc = (
            Path.home()
            / "Library/Group Containers/group.com.apple.controlcenter"
            / "Library/Preferences/group.com.apple.controlcenter.plist"
        )
        if not cc.is_file():
            return False
        pl = plistlib.loads(cc.read_bytes())
        nested = list(plistlib.loads(pl["trackedApplications"]))
        bid = "com.oxyfire.tgvideosaver"
        py = "org.python.python"
        adhoc = (
            "file:///Users/oxyfire/Desktop/TG%20Video%20Saver.app/Contents/Helpers/"
            "TGOxyfireMenu.app/Contents/MacOS/python3"
        )
        changed = False

        def loc_bundle(entry):
            loc = entry.get("location") or {}
            return (loc.get("bundle") or {}).get("_0")

        for e in nested:
            if not isinstance(e, dict) or "isAllowed" not in e:
                continue
            b = loc_bundle(e)
            if b == bid:
                want = [
                    {"bundle": {"_0": bid}},
                    {"adhocBinary": {"_0": {"relative": adhoc}}},
                    {"bundle": {"_0": py}},
                ]
                if e.get("menuItemLocations") != want or not e.get("isAllowed"):
                    e["isAllowed"] = True
                    e["menuItemLocations"] = want
                    changed = True
            elif b == py:
                want = [
                    {"bundle": {"_0": py}},
                    {"bundle": {"_0": bid}},
                    {"adhocBinary": {"_0": {"relative": adhoc}}},
                ]
                if e.get("menuItemLocations") != want or not e.get("isAllowed"):
                    e["isAllowed"] = True
                    e["menuItemLocations"] = want
                    changed = True
            else:
                loc = e.get("location") or {}
                ad = loc.get("adhocBinary") or {}
                rel = (ad.get("_0") or {}) if isinstance(ad.get("_0"), dict) else {}
                if rel.get("relative") == adhoc:
                    want = [
                        {"adhocBinary": {"_0": {"relative": adhoc}}},
                        {"bundle": {"_0": bid}},
                    ]
                    if e.get("menuItemLocations") != want or not e.get("isAllowed"):
                        e["isAllowed"] = True
                        e["menuItemLocations"] = want
                        changed = True

        if not changed:
            return False
        pl["trackedApplications"] = plistlib.dumps(nested, fmt=plistlib.FMT_BINARY)
        bak = cc.with_suffix(".plist.bak-autorepair")
        if not bak.exists():
            shutil.copy2(cc, bak)
        tmp = cc.with_suffix(".plist.repair")
        tmp.write_bytes(plistlib.dumps(pl, fmt=plistlib.FMT_BINARY))
        tmp.replace(cc)
        _log("statuskit repaired menuItemLocations")
        return True
    except Exception as e:
        _log(f"statuskit repair fail: {e}")
        return False


_LOCK_FH = None
_HOST = None


def _log(msg: str) -> None:
    from core.logutil import append_log

    append_log(LOG, msg)


def acquire_menu_lock() -> bool:
    """Один menu_host на машину — второй процесс сразу выходит."""
    global _LOCK_FH
    path = SUPPORT / ".menu.lock"
    _LOCK_FH = open(path, "w", encoding="utf-8")
    try:
        fcntl.flock(_LOCK_FH.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _LOCK_FH.write(str(os.getpid()))
        _LOCK_FH.flush()
        return True
    except BlockingIOError:
        return False


def api(base: str, path: str, method: str = "GET", body: dict | None = None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_api(port: int, timeout: float = 45) -> str:
    base = f"http://127.0.0.1:{port}"
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=1) as r:
                if r.status == 200:
                    return base
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("API timeout")


class MenuTarget(NSObject):
    bridge = None

    def openWindow_(self, _s):
        self.bridge.open_window()

    def togglePause_(self, _s):
        self.bridge.toggle_pause()

    def openFolder_(self, _s):
        self.bridge.open_folder()

    def openSettings_(self, _s):
        self.bridge.open_settings()

    def quitApp_(self, _s):
        self.bridge.quit_all()

    def tick_(self, _t):
        self.bridge.tick()

    def verifyVisible_(self, _t):
        self.bridge.verify_visible()


class MenuHost:
    def __init__(self, port: int) -> None:
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self._title = "TG"
        self._blocked_alerted = False

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        try:
            app.finishLaunching()
        except Exception:
            pass

        _force_visible_prefs()

        self.target = MenuTarget.alloc().init()
        self.target.bridge = self

        # ВАЖНО: один status item навсегда. Без remove / recreate.
        # autosaveName связывает с Visible-prefs (Item-N все скрыты на Tahoe).
        self.status = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        try:
            self.status.setAutosaveName_(AUTOSAVE)
        except Exception as e:
            _log(f"autosaveName fail: {e}")
        try:
            self.status.setVisible_(True)
        except Exception:
            pass

        btn = self.status.button()
        if btn is not None:
            img = self._icon()
            if img is not None:
                btn.setImage_(img)
                try:
                    btn.setImagePosition_(NSImageLeft)
                except Exception:
                    pass
            # Крупный якорь: на Tahoe ищут именно текст в menu bar
            btn.setTitle_("TG")
            btn.setToolTip_(APP)
            try:
                # диагностика: на Tahoe blocked item часто width≈0 / screen=None
                fr = btn.frame()
                _log(
                    f"menu_host button frame=({fr.origin.x:.0f},{fr.origin.y:.0f},"
                    f"{fr.size.width:.0f}x{fr.size.height:.0f}) "
                    f"visible={bool(self.status.isVisible())}"
                )
            except Exception as e:
                _log(f"menu_host button diag fail: {e}")

        # Через 2с проверяем, хостит ли Control Center реальный window
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            2.0, self.target, "verifyVisible:", None, False
        )

        menu = NSMenu.alloc().init()
        self._item_pause = self._add(menu, "Пауза очереди", "togglePause:")
        self._add(menu, "Открыть окно", "openWindow:")
        self._add(menu, "Открыть папку", "openFolder:")
        self._add(menu, "Настройки Menu Bar…", "openSettings:")
        menu.addItem_(NSMenuItem.separatorItem())
        self._add(menu, "Выход", "quitApp:")
        self.status.setMenu_(menu)

        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            2.0, self.target, "tick:", None, True
        )

        try:
            rumps.notification(
                title=APP,
                subtitle="",
                message="Ищите «TG» в menu bar (пламя рядом)",
            )
        except Exception:
            pass
        _log("menu_host ONCE status item created (no recreate)")

    def _icon(self):
        # Сначала цветная — заметнее; template как fallback
        for p, template in (
            (ICON_COLOR, False),
            (ICON_COLOR1, False),
            (ICON2, True),
            (ICON1, True),
        ):
            if not p.exists():
                continue
            img = NSImage.alloc().initWithContentsOfFile_(str(p))
            if img is None:
                continue
            img.setTemplate_(template)
            img.setSize_((18.0, 18.0))
            return img
        try:
            img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "flame.fill", None
            )
            if img is not None:
                img.setTemplate_(True)
                img.setSize_((16.0, 16.0))
                return img
        except Exception:
            pass
        return None

    def _add(self, menu, title, action):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
        item.setTarget_(self.target)
        menu.addItem_(item)
        return item

    def tick(self) -> None:
        try:
            st = api(self.base, "/api/state")
            paused = bool(st.get("paused"))
            self._item_pause.setTitle_(
                "Продолжить очередь" if paused else "Пауза очереди"
            )
            stats = st.get("stats") or {}
            active = int(stats.get("active") or 0)
            queued = int(stats.get("queued") or 0)
            if not st.get("ready"):
                self._title = "TG…"
            elif active:
                self._title = f"TG↓{active}"
            elif queued:
                self._title = f"TG·{queued}"
            else:
                self._title = "TG"
            btn = self.status.button()
            if btn is not None:
                btn.setTitle_(self._title)
                try:
                    self.status.setVisible_(True)
                except Exception:
                    pass
        except Exception:
            pass

    def verify_visible(self) -> None:
        """Tahoe StatusKit: AppKit говорит visible, а CC не рисует → height=0."""
        try:
            btn = self.status.button()
            win = btn.window() if btn is not None else None
            screen = win.screen() if win is not None else None
            wf = win.frame() if win is not None else None
            h = float(wf.size.height) if wf is not None else 0.0
            y = float(wf.origin.y) if wf is not None else -1.0
            if wf is not None:
                _log(
                    f"menu_host verify screen={bool(screen)} "
                    f"win=({wf.origin.x:.0f},{y:.0f},{wf.size.width:.0f}x{h})"
                )
            else:
                _log(f"menu_host verify screen={bool(screen)} win=None")
            ok = bool(screen) and h >= 20 and y > 200
            if ok:
                _log("menu_host verify OK — иконка в menu bar")
                return

            repaired = _repair_statuskit()
            _force_visible_prefs()
            try:
                self.status.setVisible_(True)
            except Exception:
                pass
            if repaired:
                _log("menu_host verify: repaired StatusKit, bounce ControlCenter")
                subprocess.run(["killall", "ControlCenter"], check=False)
                # повторная проверка через 3с
                NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    3.0, self.target, "verifyVisible:", None, False
                )
                return

            _log("menu_host verify BLOCKED")
            if not self._blocked_alerted:
                self._blocked_alerted = True
                try:
                    rumps.notification(
                        title=APP,
                        subtitle="Иконка скрыта macOS",
                        message="System Settings → Menu Bar → выключите и снова включите TG Video Saver",
                    )
                except Exception:
                    pass
                self.open_settings()
        except Exception as e:
            _log(f"menu_host verify fail: {e}")

    def open_window(self) -> None:
        try:
            from core.app_paths import helper_app

            win = helper_app("TGSaverWindow.app")
        except Exception:
            win = None
        if win is None:
            win = Path(
                "/Applications/TG Oxyfire Saver.app/Contents/Helpers/TGSaverWindow.app"
            )
        subprocess.Popen(["/usr/bin/open", str(win), "--args", str(self.port)])

    def toggle_pause(self) -> None:
        try:
            st = api(self.base, "/api/state")
            api(
                self.base,
                "/api/pause",
                method="POST",
                body={"paused": not bool(st.get("paused"))},
            )
        except Exception as e:
            _log(f"pause fail: {e}")

    def open_folder(self) -> None:
        try:
            api(self.base, "/api/open_folder", method="POST", body={})
        except Exception as e:
            _log(f"folder fail: {e}")

    def open_settings(self) -> None:
        for url in (
            "x-apple.systempreferences:com.apple.MenuBarSettings",
            "x-apple.systempreferences:com.apple.ControlCenter-Settings.extension",
        ):
            try:
                subprocess.Popen(["/usr/bin/open", url])
                return
            except Exception:
                continue

    def quit_all(self) -> None:
        subprocess.run(
            ["pkill", "-f", "Application Support/TGVideoSaver/app_main.py"], check=False
        )
        subprocess.run(["pkill", "-f", "gui_window.py"], check=False)
        subprocess.run(["pkill", "-f", "menu_host.py"], check=False)
        AppHelper.stopEventLoop()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    if not acquire_menu_lock():
        _log(f"menu_host already locked — exit (port arg={port})")
        return
    wait_api(port)
    try:
        from Foundation import NSBundle

        b = NSBundle.mainBundle()
        _log(
            f"menu_host path={b.bundlePath() if b else None} "
            f"id={b.bundleIdentifier() if b else None}"
        )
    except Exception as e:
        _log(f"menu_host bundle fail: {e}")

    global _HOST  # noqa: PLW0603
    _HOST = MenuHost(port)
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
