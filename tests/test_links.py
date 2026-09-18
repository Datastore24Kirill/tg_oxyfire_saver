"""Парсер ссылок t.me."""

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


links = _load("links_under_test", "core/links.py")
parse_targets = links.parse_targets
peer_from_private_id = links.peer_from_private_id


def test_private_link():
    found = parse_targets("https://t.me/c/123456/10")
    assert len(found) == 1
    assert found[0].peer == peer_from_private_id("123456")
    assert found[0].msg_ids == (10,)


def test_range_and_swap():
    found = parse_targets("t.me/c/9/15-12")
    assert found[0].msg_ids == (12, 13, 14, 15)


def test_public_username():
    found = parse_targets("https://t.me/durov/3")
    assert found[0].peer == "durov"
    assert found[0].msg_ids == (3,)


def test_range_cap():
    found = parse_targets("https://t.me/c/1/1-9000")
    assert found[0].msg_ids[-1] - found[0].msg_ids[0] == 5000


def test_empty():
    assert parse_targets("no links here") == []
