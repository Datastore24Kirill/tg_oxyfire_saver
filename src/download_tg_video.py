#!/usr/bin/env python3
"""Скачивание медиа из Telegram, в т.ч. при «защите контента» (через MTProto / свой аккаунт)."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

from core.paths import dated_out_dir, rollover_day_folders

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

DEFAULT_OUT = Path.home() / "Desktop" / "TelegramCaptures"

# https://t.me/c/2361138505/8371  или  https://t.me/username/123
LINK_RE = re.compile(
    r"(?:https?://)?t\.me/(?:c/(\d+)/(\d+)|([A-Za-z0-9_]+)/(\d+))",
    re.IGNORECASE,
)


def parse_link(url: str) -> tuple[int | str, int]:
    m = LINK_RE.search(url.strip())
    if not m:
        raise ValueError(
            "Нужна ссылка вида https://t.me/c/123/456 или https://t.me/channel/456"
        )
    if m.group(1):
        # приватный канал/супергруппа: -100 + id из ссылки
        channel_id = int(f"-100{m.group(1)}")
        msg_id = int(m.group(2))
        return channel_id, msg_id
    return m.group(3), int(m.group(4))


def progress_callback(received: int, total: int) -> None:
    if not total:
        print(f"\r  {received / 1e6:.1f} MB...", end="", flush=True)
        return
    pct = 100.0 * received / total
    print(f"\r  {pct:5.1f}%  ({received / 1e6:.1f}/{total / 1e6:.1f} MB)", end="", flush=True)


async def download(url: str, out_dir: Path) -> Path:
    api_id = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()
    if not api_id.isdigit() or not api_hash or api_hash.startswith("your_"):
        print(
            "Сначала заполни .env:\n"
            "  1) https://my.telegram.org → войти номером Telegram\n"
            "  2) API development tools → Create application\n"
            "  3) Скопируй api_id и api_hash в файл .env\n"
            f"     (шаблон: {ROOT / '.env.example'})",
            file=sys.stderr,
        )
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    rollover_day_folders(out_dir)
    out_dir = dated_out_dir(out_dir)
    peer, msg_id = parse_link(url)

    session = ROOT / "tg_saver"
    client = TelegramClient(str(session), int(api_id), api_hash)

    async with client:
        me = await client.get_me()
        print(f"Аккаунт: {me.first_name} (@{me.username or '—'})")

        entity = await client.get_entity(peer)
        msg = await client.get_messages(entity, ids=msg_id)
        if not msg:
            raise RuntimeError(f"Сообщение {msg_id} не найдено (нет доступа или удалено).")
        if not msg.media:
            raise RuntimeError("В сообщении нет медиа.")

        kind = "media"
        if isinstance(msg.media, MessageMediaDocument):
            kind = "document"
        elif isinstance(msg.media, MessageMediaPhoto):
            kind = "photo"

        print(f"Скачиваю ({kind}) → {out_dir}")
        path = await client.download_media(
            msg,
            file=str(out_dir / f"tg_{peer}_{msg_id}"),
            progress_callback=progress_callback,
        )
        print()
        if not path:
            raise RuntimeError("Скачивание не удалось (пусто).")
        return Path(path)


def main() -> None:
    p = argparse.ArgumentParser(description="Скачать видео/медиа из Telegram по ссылке на пост")
    p.add_argument(
        "url",
        nargs="?",
        default="https://t.me/c/2361138505/8371",
        help="Ссылка на сообщение (по умолчанию — наш пост)",
    )
    p.add_argument(
        "-o",
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Папка сохранения (по умолчанию {DEFAULT_OUT})",
    )
    args = p.parse_args()

    try:
        path = asyncio.run(download(args.url, args.out))
    except ValueError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Готово: {path}")
    # открыть в Finder
    os.system(f'open -R "{path}"')


if __name__ == "__main__":
    main()
