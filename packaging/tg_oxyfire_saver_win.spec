# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Windows — run from repo root:
   pyinstaller packaging/tg_oxyfire_saver_win.spec
"""

from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH).resolve().parent.parent
SRC = ROOT / "src"

datas = [
    (str(SRC / "gui"), "gui"),
    (str(SRC / "assets"), "assets"),
    (str(ROOT / ".env.example"), "."),
]

hiddenimports = [
    "webview",
    "webview.platforms.edgechromium",
    "bottle",
    "clr",
    "pythonnet",
    "pystray",
    "PIL",
    "PIL.Image",
    "flask",
    "telethon",
    "qrcode",
    "dotenv",
    "core",
    "core.service",
    "core.store",
    "core.runtime",
    "core.notify",
    "core.clipboard_watch",
    "core.links",
    "core.naming",
    "core.paths",
    "core.downloader",
    "windows",
    "windows.tray",
    "windows.window",
    "windows.main",
    "api_server",
]

a = Analysis(
    [str(SRC / "windows" / "main.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["rumps", "AppKit", "Foundation", "Cocoa"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TGOxyfireSaver",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TGOxyfireSaver",
)
