"""Параметры прокси для TelegramClient: SOCKS5, HTTP, MTProto."""

from __future__ import annotations

from typing import Any


def telethon_proxy_kwargs(settings: dict[str, Any]) -> dict[str, Any]:
    if not settings.get("proxy_enabled"):
        return {}
    host = str(settings.get("proxy_host") or "").strip()
    try:
        port = int(settings.get("proxy_port") or 0)
    except (TypeError, ValueError):
        port = 0
    if not host or port <= 0:
        return {}

    kind = str(settings.get("proxy_type") or "socks5").lower()
    if kind == "mtproto":
        from telethon.network.connection.tcpmtproxy import (
            ConnectionTcpMTProxyRandomizedIntermediate,
        )

        secret = str(settings.get("proxy_secret") or "").strip()
        if not secret:
            return {}
        return {
            "connection": ConnectionTcpMTProxyRandomizedIntermediate,
            "proxy": (host, port, secret),
        }

    import socks

    sock_type = socks.SOCKS5 if kind != "http" else socks.HTTP
    user = str(settings.get("proxy_username") or "").strip() or None
    password = str(settings.get("proxy_password") or "") or None
    return {"proxy": (sock_type, host, port, True, user, password)}
