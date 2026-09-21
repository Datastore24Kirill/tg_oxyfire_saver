"""Пути сохранения: дата скачивания + канал."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from pathlib import Path

FOLDER_TODAY = "Сегодня"
FOLDER_YESTERDAY = "Вчера"

DEFAULT_OUT = Path.home() / "Downloads" / "TelegramCaptures"


def probe_writable(folder: Path) -> bool:
    """True, если можно создать папку и записать тестовый файл."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".tg_oxyfire_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def ensure_writable_out_dir(preferred: Path | str | None = None) -> Path:
    """Вернуть доступную папку сохранений.

    Desktop на новых macOS часто закрыт для helper-процессов (TCC).
    Fallback: ~/Downloads/TelegramCaptures.
    """
    candidates: list[Path] = []
    if preferred:
        candidates.append(Path(preferred).expanduser())
    candidates.append(DEFAULT_OUT)
    # unique preserve order
    seen: set[str] = set()
    for c in candidates:
        key = str(c)
        if key in seen:
            continue
        seen.add(key)
        if probe_writable(c):
            return c
    # last resort: Application Support captures
    try:
        from core.runtime import support_dir

        fallback = support_dir() / "Captures"
    except Exception:
        fallback = Path.home() / "Library" / "Application Support" / "TGVideoSaver" / "Captures"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


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


def _content_date(folder: Path) -> date | None:
    """Дата большинства файлов в папке (по времени записи)."""
    counts: dict[date, int] = {}
    if not folder.is_dir():
        return None
    for path in folder.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        day = datetime.fromtimestamp(path.stat().st_mtime).date()
        counts[day] = counts.get(day, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda day: (counts[day], day.toordinal()))


def _name_for_date(day: date, today: date, yesterday: date) -> str:
    if day == today:
        return FOLDER_TODAY
    if day == yesterday:
        return FOLDER_YESTERDAY
    return day.isoformat()


def _merge_into(src: Path, dest: Path) -> None:
    """Перенести src в dest. Если dest уже есть — сложить содержимое внутрь."""
    if not src.exists():
        return
    if dest.exists() and src.resolve() == dest.resolve():
        return
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dest)
        return
    dest.mkdir(parents=True, exist_ok=True)
    for item in list(src.iterdir()):
        target = dest / item.name
        if item.is_dir():
            if target.exists() and target.is_dir():
                _merge_into(item, target)
                try:
                    item.rmdir()
                except OSError:
                    pass
            elif not target.exists():
                item.rename(target)
        elif not target.exists():
            item.rename(target)
    try:
        src.rmdir()
    except OSError:
        pass


def rollover_day_folders(base: Path) -> None:
    """«Сегодня» / «Вчера» должны совпадать с датой файлов внутри.

    Если папка не пустая, а файлы от другого дня — переименовать:
    вчерашний день остаётся «Вчера», более старый становится YYYY-MM-DD.
    """
    try:
        base.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        raise PermissionError(
            f"Нет доступа к папке сохранений «{base}». "
            "macOS → Системные настройки → Конфиденциальность и безопасность → "
            "Файлы и папки → Desktop для TG Oxyfire Saver / TGSaverEngine. "
            "Или выбери другую папку в Настройках приложения."
        ) from e

    today = date.today()
    yesterday = today - timedelta(days=1)
    # Сначала «Вчера», чтобы имя освободилось для настоящей вчерашней папки.
    for name, expected in (
        (FOLDER_YESTERDAY, yesterday),
        (FOLDER_TODAY, today),
    ):
        folder = base / name
        if not folder.is_dir():
            continue
        content = _content_date(folder)
        if content is None or content == expected:
            continue
        dest = base / _name_for_date(content, today, yesterday)
        try:
            _merge_into(folder, dest)
        except PermissionError as e:
            raise PermissionError(
                f"Нет доступа к папке сохранений «{base}». "
                "Разреши Desktop в macOS или смени папку в Настройках."
            ) from e

    marker = _day_marker_path(base)
    try:
        marker.write_text(today.isoformat() + "\n", encoding="utf-8")
    except OSError:
        pass
    legacy = base / ".download_day"
    try:
        if legacy.exists():
            legacy.unlink()
    except OSError:
        pass
