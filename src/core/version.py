"""Единый номер версии: файл VERSION в корне репозитория или рядом с установкой."""

from __future__ import annotations

from pathlib import Path

_FALLBACK = "2.6.0"


def read_app_version() -> str:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "VERSION",
        here.parents[1] / "VERSION",
        here.parent / "VERSION",
    ]
    for path in candidates:
        try:
            if not path.is_file():
                continue
            line = path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
            line = line.lstrip("vV")
            if line:
                return line
        except OSError:
            continue
    return _FALLBACK


def version_tuple(value: str) -> tuple[int, int, int]:
    parts: list[int] = []
    for piece in (value or "").lstrip("vV").split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits or "0"))
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def is_newer(latest: str, current: str) -> bool:
    return version_tuple(latest) > version_tuple(current)


APP_VERSION = read_app_version()
