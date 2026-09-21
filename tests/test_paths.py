"""Папки Сегодня / Вчера следуют дате файлов внутри."""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"


def _load(name: str, rel: str):
    path = _SRC / rel
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


paths = _load("paths_under_test", "core/paths.py")
paths._day_marker_path = lambda base: base / ".daymarker"


def _touch(folder: Path, name: str, day: date) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / name
    file.write_bytes(b"x")
    ts = datetime(day.year, day.month, day.day, 12, 0).timestamp()
    os.utime(file, (ts, ts))


def test_stale_today_becomes_yesterday(tmp_path: Path):
    today = date.today()
    yesterday = today - timedelta(days=1)
    _touch(tmp_path / "Сегодня" / "Channel", "a.mp4", yesterday)
    paths.rollover_day_folders(tmp_path)
    assert (tmp_path / "Вчера" / "Channel" / "a.mp4").is_file()
    assert not (tmp_path / "Сегодня").exists()


def test_older_yesterday_becomes_iso_date(tmp_path: Path):
    old = date.today() - timedelta(days=3)
    _touch(tmp_path / "Вчера" / "Channel", "a.mp4", old)
    paths.rollover_day_folders(tmp_path)
    assert (tmp_path / old.isoformat() / "Channel" / "a.mp4").is_file()
    assert not (tmp_path / "Вчера").exists()


def test_today_folder_stays(tmp_path: Path):
    _touch(tmp_path / "Сегодня" / "Channel", "a.mp4", date.today())
    paths.rollover_day_folders(tmp_path)
    assert (tmp_path / "Сегодня" / "Channel" / "a.mp4").is_file()
