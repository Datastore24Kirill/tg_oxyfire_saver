"""Парсинг ссылок Telegram и диапазонов."""

from __future__ import annotations

import re
from dataclasses import dataclass

LINK_RE = re.compile(
    r"(?:https?://)?t\.me/(?:c/(\d+)/(\d+)(?:-(\d+))?|([A-Za-z0-9_]+)/(\d+)(?:-(\d+))?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedTarget:
    peer: int | str
    msg_ids: tuple[int, ...]
    raw: str


def peer_from_private_id(channel_digits: str) -> int:
    return int(f"-100{channel_digits}")


def parse_targets(text: str) -> list[ParsedTarget]:
    """Из текста вытащить все ссылки/диапазоны."""
    found: list[ParsedTarget] = []
    for m in LINK_RE.finditer(text or ""):
        raw = m.group(0)
        if m.group(1):
            peer: int | str = peer_from_private_id(m.group(1))
            start = int(m.group(2))
            end = int(m.group(3)) if m.group(3) else start
        else:
            peer = m.group(4)
            start = int(m.group(5))
            end = int(m.group(6)) if m.group(6) else start
        if end < start:
            start, end = end, start
        # защита от огромных диапазонов
        if end - start > 5000:
            end = start + 5000
        ids = tuple(range(start, end + 1))
        found.append(ParsedTarget(peer=peer, msg_ids=ids, raw=raw))
    return found


def extract_tme_urls(text: str) -> list[str]:
    return [m.group(0) if m.group(0).startswith("http") else "https://" + m.group(0)
            for m in re.finditer(r"(?:https?://)?t\.me/\S+", text or "", re.I)]
