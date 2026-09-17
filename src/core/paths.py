"""Пути сохранения: дата скачивания + канал."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

FOLDER_TODAY = "Сегодня"
FOLDER_YESTERDAY = "Вчера"

DEFAULT_OUT = Path.home() / "Desktop" / "TelegramCaptures"


def safe_folder_name(name: str, fallback: str = "unknown") -> str:
    name = (name or "").strip() or fallback
    name = re.sub(r'[\\/:*?"<>|\n\r\t]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" ._")
    return (name[:80] or fallback)


def dated_out_dir(base: Path, when: date | None = None) -> Path:
    day = when or date.today()
    today = date.today()
    yesterday = today - timedelta(days=1)
    if day == today:
        name = FOLDER_TODAY
    elif day == yesterday:
        name = FOLDER_YESTERDAY
    else:
        name = day.isoformat()
    path = base / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def channel_out_dir(base: Path, channel_name: str, when: date | None = None) -> Path:
    day_dir = dated_out_dir(base, when)
    path = day_dir / safe_folder_name(channel_name)
    path.mkdir(parents=True, exist_ok=True)
    return path


def rollover_day_folders(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    marker = base / ".download_day"
    today = date.today()
    yesterday = today - timedelta(days=1)

    prev: date | None = None
    if marker.exists():
        try:
            prev = date.fromisoformat(marker.read_text(encoding="utf-8").strip())
        except ValueError:
            prev = None

    if prev == today:
        return

    today_dir = base / FOLDER_TODAY
    yesterday_dir = base / FOLDER_YESTERDAY

    if yesterday_dir.exists() and yesterday_dir.is_dir():
        if prev is not None:
            old_day = prev - timedelta(days=1)
        else:
            old_day = datetime.fromtimestamp(yesterday_dir.stat().st_mtime).date()
            if old_day >= yesterday:
                old_day = yesterday - timedelta(days=1)
        target = base / old_day.isoformat()
        if target.exists():
            for item in yesterday_dir.iterdir():
                dest = target / item.name
                if not dest.exists():
                    item.rename(dest)
            try:
                yesterday_dir.rmdir()
            except OSError:
                pass
        else:
            yesterday_dir.rename(target)

    if today_dir.exists() and today_dir.is_dir():
        if yesterday_dir.exists():
            stamp = (prev or today - timedelta(days=1)).isoformat()
            spill = base / stamp
            spill.mkdir(exist_ok=True)
            for item in today_dir.iterdir():
                dest = spill / item.name
                if not dest.exists():
                    item.rename(dest)
            try:
                today_dir.rmdir()
            except OSError:
                pass
        else:
            today_dir.rename(yesterday_dir)

    marker.write_text(today.isoformat() + "\n", encoding="utf-8")
