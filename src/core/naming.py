"""Имена файлов и определение типа медиа."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto


MEDIA_VIDEO = "video"
MEDIA_PHOTO = "photo"
MEDIA_DOCUMENT = "document"
MEDIA_OTHER = "other"


def detect_media_type(msg: Any) -> str | None:
    if not msg or not msg.media:
        return None
    if isinstance(msg.media, MessageMediaPhoto):
        return MEDIA_PHOTO
    if isinstance(msg.media, MessageMediaDocument):
        doc = msg.media.document
        if not doc:
            return MEDIA_DOCUMENT
        mime = (getattr(doc, "mime_type", None) or "").lower()
        if mime.startswith("video/") or any(
            getattr(a, "id", None) == "documentAttributeVideo" or a.__class__.__name__ == "DocumentAttributeVideo"
            for a in (getattr(doc, "attributes", None) or [])
        ):
            return MEDIA_VIDEO
        if mime.startswith("image/"):
            return MEDIA_PHOTO
        return MEDIA_DOCUMENT
    return MEDIA_OTHER


def matches_filter(media_type: str | None, filter_name: str) -> bool:
    if filter_name in ("all", "", None):
        return media_type is not None
    if media_type is None:
        return False
    return media_type == filter_name


def sanitize_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r'[\\/:*?"<>|\n\r\t]+', "_", name or "")
    name = re.sub(r"\s+", " ", name).strip(" ._")
    return (name[:max_len] or "file")


def original_name(msg: Any) -> str | None:
    if not msg or not getattr(msg, "media", None):
        return None
    if isinstance(msg.media, MessageMediaDocument):
        doc = msg.media.document
        for a in getattr(doc, "attributes", None) or []:
            fn = getattr(a, "file_name", None)
            if fn:
                return fn
    return None


def build_filename(
    *,
    template: str,
    channel: str,
    msg_id: int,
    caption: str,
    original: str | None,
    media_type: str,
    ext: str,
) -> str:
    """
    Плейсхолдеры: {channel} {id} {date} {caption} {original} {type}
    """
    from datetime import date

    caps = sanitize_filename((caption or "").replace("\n", " ")[:60]) or "no-caption"
    orig_stem = sanitize_filename(Path(original).stem) if original else f"tg_{msg_id}"
    values = {
        "channel": sanitize_filename(channel),
        "id": str(msg_id),
        "date": date.today().isoformat(),
        "caption": caps,
        "original": orig_stem,
        "type": media_type,
    }
    try:
        name = template.format(**values)
    except Exception:
        name = "{channel}_{id}_{type}".format(**values)
    name = sanitize_filename(name)
    if ext and not name.lower().endswith("." + ext.lower().lstrip(".")):
        name = f"{name}.{ext.lstrip('.')}"
    return name
