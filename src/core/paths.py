"""Пути сохранения: дата скачивания + канал."""

from __future__ import annotations

import hashlib
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


def _day_marker_path(base: Path) -> Path:
    """Маркер дня — в Application Support / APPDATA, не в папке на Desktop.

    Запись скрытого файла на Desktop часто даёт macOS Errno 1 (Operation not permitted).
    """
    try:
        from core.runtime import support_dir

        root = support_dir() / "day_markers"
    except Exception:
        root = Path.home() / "Library" / "Application Support" / "TGVideoSaver" / "day_markers"
    root.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(str(base.resolve()).encode("utf-8")).hexdigest()[:16]
    return root / f"{key}.day"


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
    try:
        path.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        raise PermissionError(
            f"Нет доступа к папке сохранений «{base}». "
            "macOS → Системные настройки → Конфиденциальность и безопасность → "
            "Файлы и папки → разреши Desktop (или выбери другую папку в Настройках)."
        ) from e
    return path


def channel_out_dir(base: Path, channel_name: str, when: date | None = None) -> Path:
    day_dir = dated_out_dir(base, when)
    path = day_dir / safe_folder_name(channel_name)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        raise PermissionError(
            f"Нет доступа к папке сохранений «{base}». "
            "Разреши доступ к Desktop в настройках macOS или смени папку в приложении."
        ) from e
    return path


def rollover_day_folders(base: Path) -> None:
    try:
        base.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        raise PermissionError(
            f"Нет доступа к папке сохранений «{base}». "
            "macOS → Системные настройки → Конфиденциальность и безопасность → "
            "Файлы и папки → Desktop для TG Oxyfire Saver / TGSaverEngine. "
            "Или выбери другую папку в Настройках приложения."
        ) from e

    marker = _day_marker_path(base)
    today = date.today()
    yesterday = today - timedelta(days=1)

    prev: date | None = None
    if marker.exists():
        try:
            prev = date.fromisoformat(marker.read_text(encoding="utf-8").strip())
        except ValueError:
            prev = None

    # Миграция: старый маркер лежал прямо в out_dir
    legacy = base / ".download_day"
    if prev is None and legacy.exists():
        try:
            prev = date.fromisoformat(legacy.read_text(encoding="utf-8").strip())
        except Exception:
            prev = None

    if prev == today:
        return

    today_dir = base / FOLDER_TODAY
    yesterday_dir = base / FOLDER_YESTERDAY

    try:
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
    except PermissionError as e:
        raise PermissionError(
            f"Нет доступа к папке сохранений «{base}». "
            "Разреши Desktop в macOS или смени папку в Настройках."
        ) from e

    try:
        marker.write_text(today.isoformat() + "\n", encoding="utf-8")
    except OSError:
        pass
    # Убрать legacy-маркер с Desktop, если получится
    try:
        if legacy.exists():
            legacy.unlink()
    except OSError:
        pass
