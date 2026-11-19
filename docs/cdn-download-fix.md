# Telegram CDN download compatibility

19 November 2026. Local installation based on 2.6.13.

## Failure

Downloads redirected to Telegram CDN failed with `MethodInvalidError` from
`GetCdnFileRequest`. Telethon 1.45.0 selected the account sender for CDN requests.
Changing only that sender was insufficient: account key reuse, legacy key
exchange, IGE decryption and missing block verification made that path unusable.

## Fix

`core/telethon_cdn.py` intercepts CDN redirects at the download iterator, leaving
normal download processing intact. CDN connections use an independent ephemeral
key, current RSA_PAD / PQInnerDataDc negotiation, and keys obtained from the
account server's CDN configuration. Existing Telethon DH/nonce checks remain in
place; no account authentication is exported to CDN servers.

Each block is decrypted with AES-256-CTR using its offset, then checked against
SHA-256 received from the origin server before bytes reach the output file.
Missing hashes, failed verification and truncated files fail closed. Final short
blocks can be smaller than the hash descriptor limit. Reupload requests use the
original file sender, with bounded attempts and delay. Network waits have limits.
The final helper closes its CDN connection even if a progress callback cancels
the download. Logs contain stages, offsets and exception classes, not tokens,
keys, channel contents or credentials.

Telethon is pinned to 1.45.0 because the adapter uses private iterator and
handshake interfaces. Compatibility tests must run before upgrading Telethon.
Mac and Windows CI now include these tests.

## Validation

- Python suite: 23 tests, 22 passed, one existing platform-dependent skip.
- JavaScript queue ordering and interface language tests passed.
- Live Mac queue: all four affected jobs completed. The larger file reached
  100%, exists on disk, and contains 26,083,270 bytes. Additional user downloads
  progressed beyond 23 MB without the previous CDN error.
- No Telegram session or queued jobs were deleted. Several backend restarts were
  used during diagnosis. New user downloads were left running after recovery.
- The correction is installed locally; no new public release was published in
  this task. Windows runtime has not been exercised locally.

Protocol references:
- https://core.telegram.org/cdn
- https://core.telegram.org/mtproto/auth_key
