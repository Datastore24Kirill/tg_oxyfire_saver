"""Verified Telegram CDN downloads for Telethon 1.x.

CDN connections have their own ephemeral authorization key. They must never
reuse the account key. Decrypt and verify each hash block before returning bytes.
See https://core.telegram.org/cdn.
"""
import asyncio
import hashlib
from functools import wraps
from contextvars import ContextVar

_active_readers = ContextVar("tg_cdn_readers", default=None)
from pathlib import Path


def _log(message):
    from core.logutil import append_log
    append_log(Path(__file__).resolve().parents[1] / "app.log", "CDN: " + message)


def _rsa_pad(fingerprint, data, *, use_old=False):
    """Telegram RSA_PAD, https://core.telegram.org/mtproto/auth_key#4-1 ."""
    import os
    from telethon.crypto import AES, rsa
    key, old = rsa._server_keys.get(fingerprint, (None, None))
    if key is None or (old and not use_old):
        return None
    if len(data) > 144:
        raise ValueError('CDN handshake payload exceeds RSA_PAD limit')
    padded = data + os.urandom(192 - len(data))
    while True:
        temp_key = os.urandom(32)
        encrypted = AES.encrypt_ige(padded[::-1] + hashlib.sha256(temp_key + padded).digest(),
                                    temp_key, bytes(32))
        mixed = bytes(a ^ b for a, b in zip(temp_key, hashlib.sha256(encrypted).digest()))
        number = int.from_bytes(mixed + encrypted, 'big')
        if number < key.n:
            return pow(number, key.e, key.n).to_bytes(256, 'big')


class CDNReader:
    def __init__(self, client, origin_sender, redirect):
        self.client = client
        self.origin = origin_sender
        self.redirect = redirect
        self.sender = None
        self.hashes = {h.offset: h for h in redirect.file_hashes}
        self.cache_offset = 0
        self.cache = b''
        self.eof = None

    async def connect(self):
        from telethon.network.mtprotosender import MTProtoSender
        _log("connecting")
        dc = await asyncio.wait_for(self.client._get_dc(self.redirect.dc_id, cdn=True), 45)
        _log("resolved CDN DC " + str(dc.id))
        from telethon.crypto import rsa
        import rsa as public_rsa
        allowed = set()
        for entry in self.client._cdn_config.public_keys:
            if entry.dc_id == dc.id:
                rsa.add_key(entry.public_key, old=False)
                allowed.add(rsa._compute_fingerprint(public_rsa.PublicKey.load_pkcs1(entry.public_key)))
        def encrypt(fingerprint, data, *, use_old=False):
            if fingerprint not in allowed:
                return None
            return _rsa_pad(fingerprint, data, use_old=use_old)
        class CDNSender(MTProtoSender):
            async def _try_gen_auth_key(sender, attempt):
                from telethon.network import authenticator
                from telethon.network.mtprotoplainsender import MTProtoPlainSender
                from telethon.tl.types import PQInnerDataDc
                from telethon.crypto import rsa
                from types import FunctionType, SimpleNamespace
                # Retain Telethon's nonce/DH validation, but use the current
                # documented RSA_PAD envelope and include the CDN DC identity.
                namespace = dict(authenticator.do_authentication.__globals__)
                namespace['PQInnerData'] = lambda **kw: PQInnerDataDc(dc=dc.id, **kw)
                namespace['rsa'] = SimpleNamespace(get_byte_array=rsa.get_byte_array,
                                                   encrypt=encrypt)
                authenticate = FunctionType(authenticator.do_authentication.__code__, namespace)
                plain = MTProtoPlainSender(sender._connection, loggers=sender._loggers)
                sender.auth_key.key, sender._state.time_offset = await authenticate(plain)
                return True
        self.sender = CDNSender(None, loggers=self.client._log,
                                    retries=2, connect_timeout=20)
        from telethon.network.connection.tcpobfuscated import ConnectionTcpObfuscated
        connection = ConnectionTcpObfuscated if self.client._proxy is None else self.client._connection
        await asyncio.wait_for(self.sender.connect(connection(
            dc.ip_address, dc.port, dc.id, loggers=self.client._log,
            proxy=self.client._proxy, local_addr=self.client._local_addr)), 45)
        _log("connected with independent key")

    async def origin_call(self, request):
        return await asyncio.wait_for(self.client._call(self.origin, request), 45)

    async def block(self, offset):
        from telethon.tl import functions, types
        from telethon.crypto import AESModeCTR
        from telethon.errors import CdnFileTamperedError
        candidates = [h for h in self.hashes.values()
                      if h.offset <= offset < h.offset + h.limit]
        if not candidates:
            hashes = await self.origin_call(functions.upload.GetCdnFileHashesRequest(
                self.redirect.file_token, offset))
            self.hashes.update((h.offset, h) for h in hashes)
            candidates = [h for h in hashes if h.offset <= offset < h.offset + h.limit]
        if not candidates:
            # No hashes is not proof of EOF; never accept unchecked content.
            raise RuntimeError('Telegram CDN: отсутствует контрольная сумма блока')
        h = candidates[0]
        if h.limit <= 0 or h.limit > 1024 * 1024 or h.offset % 4096:
            raise RuntimeError('Telegram CDN: неподдерживаемый размер блока проверки')
        encrypted = bytearray()
        while len(encrypted) < h.limit:
            pos = h.offset + len(encrypted)
            # Telegram permits power-of-two request sizes inside a 1 MB window.
            limit = 4096
            while limit < h.limit - len(encrypted) and limit < 1024 * 1024:
                limit *= 2
            while pos // (1024 * 1024) != (pos + limit - 1) // (1024 * 1024):
                limit //= 2
            request = functions.upload.GetCdnFileRequest(self.redirect.file_token, pos, limit)
            for attempt in range(4):
                result = await asyncio.wait_for(self.sender.send(request), 45)
                if isinstance(result, types.upload.CdnFileReuploadNeeded):
                    hashes = await self.origin_call(functions.upload.ReuploadCdnFileRequest(
                        self.redirect.file_token, result.request_token))
                    self.hashes.update((item.offset, item) for item in hashes)
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    break
            if not isinstance(result, types.upload.CdnFile) or not result.bytes:
                _log('incomplete block offset=' + str(pos) + ' limit=' + str(limit) + ' response=' + type(result).__name__ + ' size=' + str(len(getattr(result, 'bytes', b''))))
                raise RuntimeError('Telegram CDN: не удалось получить полный блок файла')
            encrypted.extend(result.bytes[:h.limit - len(encrypted)])
            if len(result.bytes) < limit:
                break
        iv = self.redirect.encryption_iv[:12] + (h.offset // 16).to_bytes(4, 'big')
        data = AESModeCTR(self.redirect.encryption_key, iv).encrypt(bytes(encrypted))
        if hashlib.sha256(data).digest() != h.hash:
            raise CdnFileTamperedError()
        if h.offset == 0:
            _log("first block verified")
        self.cache_offset, self.cache = h.offset, data
        self.eof = h.offset + len(data) if len(data) < h.limit else None
        # Keep memory bounded even on very large videos.
        self.hashes = {pos: item for pos, item in self.hashes.items() if pos >= h.offset}

    async def read(self, offset, limit, total):
        if self.eof is not None and offset >= self.eof:
            return b''
        if total is not None and offset >= total:
            return b''
        end = min(offset + limit, total) if total is not None else offset + limit
        output = bytearray()
        while offset < end:
            if not self.cache_offset <= offset < self.cache_offset + len(self.cache):
                await self.block(offset)
            part = self.cache[offset - self.cache_offset: end - self.cache_offset]
            output.extend(part)
            offset += len(part)
            if self.eof is not None and offset >= self.eof:
                if total is not None and self.eof < total:
                    raise RuntimeError("Telegram CDN: файл короче ожидаемого размера")
                break
        return bytes(output)

    async def close(self):
        if self.sender is not None:
            await self.sender.disconnect()
            self.sender = None


def install_cdn_sender_fix():
    from telethon.client.downloads import _DirectDownloadIter, _CdnRedirect, DownloadMethods
    original = _DirectDownloadIter._request
    original_close = _DirectDownloadIter.close
    original_download = DownloadMethods._download_file
    if getattr(original, '_oxy_cdn_sender_fix', False):
        return

    @wraps(original)
    async def request(self):
        reader = getattr(self, '_oxy_cdn_reader', None)
        try:
            if reader is None:
                try:
                    return await original(self)
                except _CdnRedirect as redirect:
                    _log("redirect received")
                    reader = CDNReader(self.client, self._sender, redirect.cdn_redirect)
                    self._oxy_cdn_reader = reader
                    active = _active_readers.get()
                    if active is not None:
                        active.append(reader)
                    await reader.connect()
            return await reader.read(self.request.offset, self.request.limit, self.total)
        except BaseException as exc:
            _log("request failed: " + type(exc).__name__)
            if reader is not None:
                await reader.close()
            if isinstance(exc, asyncio.TimeoutError):
                raise RuntimeError("Telegram не ответил вовремя. Повторите загрузку.") from exc
            raise

    @wraps(original_close)
    async def close(self):
        try:
            reader = getattr(self, '_oxy_cdn_reader', None)
            if reader is not None:
                await reader.close()
        finally:
            await original_close(self)

    @wraps(original_download)
    async def download(self, *args, **kwargs):
        readers = []
        token = _active_readers.set(readers)
        try:
            return await original_download(self, *args, **kwargs)
        finally:
            try:
                for reader in readers:
                    await reader.close()
            finally:
                _active_readers.reset(token)

    DownloadMethods._download_file = download
    request._oxy_cdn_sender_fix = True
    _DirectDownloadIter._request = request
    _DirectDownloadIter.close = close
