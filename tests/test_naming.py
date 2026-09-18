"""Имена файлов и фильтр медиа."""

from __future__ import annotations

import importlib.util
import sys
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


naming = _load("naming_under_test", "core/naming.py")
build_filename = naming.build_filename
matches_filter = naming.matches_filter
sanitize_filename = naming.sanitize_filename


def test_sanitize_strips_bad_chars():
    assert "/" not in sanitize_filename('a/b:c*?"')
    assert sanitize_filename("   ") == "file"


def test_matches_filter():
    assert matches_filter("video", "video")
    assert not matches_filter("photo", "video")
    assert matches_filter("document", "all")
    assert not matches_filter(None, "video")


def test_build_filename_template():
    name = build_filename(
        template="{channel}_{id}_{type}",
        channel="News/Channel",
        msg_id=42,
        caption="hello",
        original="clip.mp4",
        media_type="video",
        ext="mp4",
    )
    assert name.startswith("News_Channel_42_video")
    assert name.endswith(".mp4")


def test_build_filename_bad_template_falls_back():
    name = build_filename(
        template="{missing}",
        channel="Ch",
        msg_id=1,
        caption="",
        original=None,
        media_type="photo",
        ext="jpg",
    )
    assert "Ch_1_photo" in name
    assert name.endswith(".jpg")
