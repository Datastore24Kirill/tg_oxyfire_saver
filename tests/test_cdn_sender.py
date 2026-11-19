import asyncio
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

spec = importlib.util.spec_from_file_location('cdn_fix', Path(__file__).resolve().parents[1] / 'src/core/telethon_cdn.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module._log = lambda message: None

try:
    from telethon.crypto import AESModeCTR
    from telethon.errors import CdnFileTamperedError
    from telethon.tl import types
except ImportError:
    AESModeCTR = None


@unittest.skipIf(AESModeCTR is None, 'Telethon not installed')
class CDNTests(unittest.IsolatedAsyncioTestCase):
    def reader(self, data, offset=0, bad_hash=False):
        key, iv = bytes(range(32)), bytes(range(16))
        digest = bytes(32) if bad_hash else hashlib.sha256(data).digest()
        h = SimpleNamespace(offset=offset, limit=len(data), hash=digest)
        redirect = SimpleNamespace(file_hashes=[h], file_token=b'token', encryption_key=key, encryption_iv=iv)
        client = SimpleNamespace(_call=AsyncMock())
        reader = module.CDNReader(client, object(), redirect)
        ciphertext = AESModeCTR(key, iv[:12] + (offset // 16).to_bytes(4, 'big')).encrypt(data)
        reader.sender = SimpleNamespace(send=AsyncMock(return_value=types.upload.CdnFile(ciphertext)), disconnect=AsyncMock())
        return reader

    async def test_decrypt_verify_cache_and_eof(self):
        data = b'a' * 4096 + b'b' * 4096
        reader = self.reader(data)
        self.assertEqual(await reader.read(0, 4096, len(data)), data[:4096])
        self.assertEqual(await reader.read(4096, 4096, len(data)), data[4096:])
        self.assertEqual(reader.sender.send.await_count, 1)
        self.assertEqual(await reader.read(8192, 4096, len(data)), b'')

    async def test_nonzero_ctr_offset_and_short_final_block(self):
        data = b'z' * 1234
        reader = self.reader(data, 4096)
        self.assertEqual(await reader.read(4096, 4096, 5330), data)

    async def test_corruption_never_returned(self):
        reader = self.reader(b'a' * 4096, bad_hash=True)
        with self.assertRaises(CdnFileTamperedError):
            await reader.read(0, 4096, 4096)
        self.assertEqual(reader.cache, b'')

    async def test_missing_hash_is_error(self):
        reader = self.reader(b'a' * 4096)
        reader.hashes.clear()
        reader.client._call.return_value = []
        with self.assertRaises(RuntimeError):
            await reader.read(0, 4096, 4096)
        reader.sender.send.assert_not_awaited()

    async def test_reupload_uses_origin(self):
        reader = self.reader(b'a' * 4096)
        result = reader.sender.send.return_value
        reader.sender.send.side_effect = [types.upload.CdnFileReuploadNeeded(b'request'), result]
        reader.client._call.return_value = []
        self.assertEqual(await reader.read(0, 4096, 4096), b'a' * 4096)
        self.assertIs(reader.client._call.call_args.args[0], reader.origin)

    async def test_install_idempotent(self):
        from telethon.client.downloads import _DirectDownloadIter
        module.install_cdn_sender_fix()
        first = _DirectDownloadIter._request
        module.install_cdn_sender_fix()
        self.assertIs(first, _DirectDownloadIter._request)

    async def test_final_hash_limit_can_exceed_actual_file(self):
        reader = self.reader(b'last' * 300, 4096)
        reader.hashes[4096].limit = 128 * 1024
        self.assertEqual(await reader.read(4096, 4096, 5296), b'last' * 300)
        self.assertEqual(await reader.read(5296, 4096, 5296), b'')
        self.assertEqual(reader.sender.send.await_count, 1)

    async def test_truncated_file_not_accepted(self):
        reader = self.reader(b'a' * 1200)
        reader.hashes[0].limit = 128 * 1024
        with self.assertRaises(RuntimeError):
            await reader.read(0, 4096, 5000)

    async def test_rsa_pad_envelope(self):
        import rsa as library
        from telethon.crypto import rsa, AES
        pub, private = library.newkeys(2048)
        fingerprint = rsa._compute_fingerprint(pub)
        rsa._server_keys[fingerprint] = (pub, False)
        try:
            data = b'handshake payload'
            encoded = module._rsa_pad(fingerprint, data)
            raw = pow(int.from_bytes(encoded, 'big'), private.d, private.n).to_bytes(256, 'big')
            key = bytes(a ^ b for a, b in zip(raw[:32], hashlib.sha256(raw[32:]).digest()))
            plain = AES.decrypt_ige(raw[32:], key, bytes(32))
            padded = plain[:192][::-1]
            self.assertEqual(padded[:len(data)], data)
            self.assertEqual(plain[192:], hashlib.sha256(key + padded).digest())
        finally:
            del rsa._server_keys[fingerprint]

    async def test_cancelled_download_closes_cdn_connection(self):
        from telethon.client.downloads import _DirectDownloadIter, _CdnRedirect, DownloadMethods
        from unittest.mock import patch
        redirect = SimpleNamespace(file_hashes=[])
        fake_reader = SimpleNamespace(connect=AsyncMock(), read=AsyncMock(return_value=b'data'), close=AsyncMock())
        iterator = SimpleNamespace(client=object(), _sender=object(), request=SimpleNamespace(offset=0, limit=4096), total=4096)
        async def download(client):
            await _DirectDownloadIter._request(iterator)
            # A cancel/progress callback can fail outside the iterator itself.
            raise asyncio.CancelledError()
        original_request = AsyncMock(side_effect=_CdnRedirect(redirect))
        original_request._oxy_cdn_sender_fix = False
        with patch.object(_DirectDownloadIter, '_request', original_request), \
             patch.object(_DirectDownloadIter, 'close', AsyncMock()), \
             patch.object(DownloadMethods, '_download_file', download), \
             patch.object(module, 'CDNReader', return_value=fake_reader):
            module.install_cdn_sender_fix()
            with self.assertRaises(asyncio.CancelledError):
                await DownloadMethods._download_file(object())
            fake_reader.close.assert_awaited_once()
            self.assertIsNone(module._active_readers.get())
