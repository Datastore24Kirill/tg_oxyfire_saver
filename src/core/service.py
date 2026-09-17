"""Главный сервис: авторизация, очередь, архив, сторожи."""

from __future__ import annotations

import asyncio
import base64
import io
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import qrcode
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    SessionPasswordNeededError,
    UsernameNotOccupiedError,
)
from telethon.tl.custom.qrlogin import QRLogin

from core.links import ParsedTarget, parse_targets
from core.naming import (
    build_filename,
    detect_media_type,
    matches_filter,
    original_name,
)
from core.notify import mark_finder_label, notify, open_path, reveal_path
from core.paths import DEFAULT_OUT, channel_out_dir, rollover_day_folders, safe_folder_name
from core.store import Store

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
SESSION = ROOT / "tg_saver"
THUMBS = ROOT / "core" / "thumbs"
THUMBS.mkdir(parents=True, exist_ok=True)
APP_VERSION = "2.3.0"
APP_NAME = "TG Oxyfire Saver"


def qr_data_url(url: str) -> str:
    img = qrcode.make(url, border=2, box_size=8)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def peer_key(peer: int | str) -> str:
    return str(peer)


def thumb_data_url(peer: int | str, msg_id: int) -> str | None:
    """JPEG превью с диска → data-URL для UI."""
    try:
        thumb_path = THUMBS / f"{peer_key(peer)}_{int(msg_id)}.jpg"
        if thumb_path.is_file() and thumb_path.stat().st_size >= 1500:
            b64 = base64.b64encode(thumb_path.read_bytes()).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"
    except OSError:
        pass
    return None


def thumb_from_video(path: str | Path, dest: Path, *, partial: bool = False) -> bool:
    """Кадр из локального видео через ffmpeg, если нет telegram-thumb.

    Для частично скачанного файла seek на 1с часто ломается — берём кадр с начала.
    """
    try:
        src = Path(path)
        if not src.is_file():
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        import subprocess

        # partial / маленький файл: только ss=0; готовый файл: сначала 1с, потом 0
        seeks = ("0",) if partial or src.stat().st_size < 4_000_000 else ("1", "0")
        for ss in seeks:
            r = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    ss,
                    "-i",
                    str(src),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "5",
                    str(dest),
                ],
                capture_output=True,
                timeout=20,
            )
            if dest.is_file() and dest.stat().st_size >= 1500 and r.returncode == 0:
                return True
            if dest.exists():
                try:
                    dest.unlink()
                except OSError:
                    pass
        return False
    except Exception:
        return False


@dataclass
class Job:
    id: str
    url: str
    peer: int | str
    msg_id: int
    status: str = "queued"  # queued|downloading|paused|done|error|cancelled|skipped
    progress: float = 0.0
    received_mb: float = 0.0
    total_mb: float = 0.0
    path: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    peer_label: str = ""
    channel: str = ""
    media_type: str | None = None
    thumb: str | None = None
    source: str = "manual"
    cancel_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("cancel_requested", None)
        return d


class DownloadService:
    def __init__(self) -> None:
        self.store = Store()
        out = Path(self.store.get_setting("out_dir", str(DEFAULT_OUT)))
        self.out_dir = out
        # Desktop/iCloud может надолго блокировать mkdir — не тормозим старт menu bar
        threading.Thread(target=self._ensure_out_dir, name="out-dir", daemon=True).start()

        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client: TelegramClient | None = None
        self._bootstrapped = threading.Event()
        self._start_error: str | None = None
        self._account: str | None = None
        self._auth_state = "connecting"
        self._phone: str | None = None
        self._phone_code_hash: str | None = None
        self._login_error: str | None = None
        self._login_busy = False
        self._log_path = ROOT / "app.log"
        self._qr: QRLogin | None = None
        self._qr_png: str | None = None
        self._qr_url: str | None = None
        self._qr_task: asyncio.Task | None = None
        self._qr_expires_at: float | None = None
        self._q: asyncio.Queue[str] | None = None
        self._worker_started = False
        self._paused = False
        self._pause_event: asyncio.Event | None = None
        self._active_job_id: str | None = None
        self._watch_handlers: list[Any] = []
        self._status_listeners: list[Any] = []
        self.clipboard = None  # set from outside
        self._restore_active_queue()
        self._restore_jobs_from_history()

    def _ensure_out_dir(self) -> None:
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            rollover_day_folders(self.out_dir)
        except Exception:
            pass

    def _persist_job(self, job: Job) -> None:
        """Активные + ошибки живут в queue; done/skipped — только history."""
        try:
            if job.status in ("queued", "downloading", "paused", "error", "cancelled"):
                self.store.upsert_queue_job(
                    {
                        "id": job.id,
                        "url": job.url,
                        "peer": job.peer,
                        "msg_id": job.msg_id,
                        "status": job.status,
                        "channel": job.channel,
                        "media_type": job.media_type,
                        "source": job.source,
                        "created_at": job.created_at,
                        "progress": job.progress,
                        "received_mb": job.received_mb,
                        "total_mb": job.total_mb,
                        "path": job.path,
                        "error": job.error,
                    }
                )
            else:
                # done / skipped — убрать из queue-таблицы
                self.store.delete_queue_job(job.id)
        except Exception:  # noqa: BLE001
            pass

    def _restore_active_queue(self) -> None:
        """Поднять незавершённые и ошибки после рестарта."""
        try:
            rows = self.store.list_queue_jobs()
        except Exception:
            return
        with self._lock:
            for row in rows:
                status = row.get("status") or "queued"
                if status not in ("queued", "downloading", "paused", "error", "cancelled"):
                    try:
                        self.store.delete_queue_job(row["id"])
                    except Exception:
                        pass
                    continue
                # downloading прервали — снова в очередь
                if status == "downloading":
                    status = "queued"
                jid = str(row["id"])
                if jid in self._jobs:
                    continue
                peer_raw = row.get("peer") or ""
                peer: int | str
                if str(peer_raw).lstrip("-").isdigit():
                    peer = int(peer_raw)
                else:
                    peer = peer_raw
                mid = int(row.get("msg_id") or 0)
                job = Job(
                    id=jid,
                    url=row.get("url") or "",
                    peer=peer,
                    msg_id=mid,
                    status=status,
                    progress=float(row.get("progress") or 0),
                    received_mb=float(row.get("received_mb") or 0),
                    total_mb=float(row.get("total_mb") or 0),
                    path=row.get("path"),
                    error=row.get("error"),
                    channel=row.get("channel") or "",
                    peer_label=row.get("channel") or f"{peer}/{mid}",
                    media_type=row.get("media_type"),
                    source=row.get("source") or "restored",
                    created_at=float(row.get("created_at") or time.time()),
                    thumb=thumb_data_url(peer, mid),
                )
                self._jobs[jid] = job
                self._order.append(jid)
                self._persist_job(job)

    def _restore_jobs_from_history(self) -> None:
        """Недавние done в очередь, кроме явно очищенных (queue_dismissed)."""
        try:
            rows = self.store.history("", limit=80)
        except Exception:
            return
        with self._lock:
            for row in reversed(rows):
                if row.get("status") != "done":
                    continue
                pk = row.get("peer_key") or ""
                mid = int(row.get("msg_id") or 0)
                if self.store.is_queue_dismissed(pk, mid):
                    continue
                jid = f"hist-{pk}-{mid}"
                if jid in self._jobs:
                    continue
                # превью: файл thumbs или кадр из видео
                thumb = thumb_data_url(pk, mid)
                if not thumb and row.get("path"):
                    tpath = THUMBS / f"{pk}_{mid}.jpg"
                    if thumb_from_video(row["path"], tpath):
                        thumb = thumb_data_url(pk, mid)
                job = Job(
                    id=jid,
                    url=row.get("url") or "",
                    peer=pk,
                    msg_id=mid,
                    status="done",
                    progress=100.0,
                    path=row.get("path"),
                    channel=row.get("channel") or "",
                    peer_label=row.get("channel") or "",
                    media_type=row.get("media_type"),
                    source="history",
                    created_at=float(row.get("created_at") or time.time()),
                    thumb=thumb,
                )
                try:
                    if job.path and Path(job.path).is_file():
                        mb = Path(job.path).stat().st_size / (1024 * 1024)
                        job.received_mb = mb
                        job.total_mb = mb
                except OSError:
                    pass
                self._jobs[jid] = job
                self._order.append(jid)
        threading.Thread(target=self._tag_history_files, name="finder-tags", daemon=True).start()
        threading.Thread(target=self._backfill_thumbs, name="thumbs-bf", daemon=True).start()

    def _backfill_thumbs(self) -> None:
        """Добить превью для done без JPEG."""
        try:
            with self._lock:
                jobs = [self._jobs[i] for i in self._order]
            for job in jobs:
                if job.thumb or job.status != "done" or not job.path:
                    continue
                tpath = THUMBS / f"{peer_key(job.peer)}_{job.msg_id}.jpg"
                if tpath.exists() or thumb_from_video(job.path, tpath):
                    job.thumb = thumb_data_url(job.peer, job.msg_id)
        except Exception:
            pass

    def _tag_history_files(self) -> None:
        try:
            for row in self.store.history("", limit=500):
                p = row.get("path")
                if p and Path(p).is_file():
                    mark_finder_label(p)
        except Exception:
            pass

    # ----- lifecycle -----
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, name="tg-svc", daemon=True)
        self._thread.start()
        self._bootstrapped.wait(timeout=60)

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._bootstrap())
            self._bootstrapped.set()
            self._loop.run_forever()
        except Exception as e:  # noqa: BLE001
            self._start_error = str(e)
            self._auth_state = "error"
            self._bootstrapped.set()

    def _log(self, msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}\n"
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    async def _bootstrap(self) -> None:
        # Default: public Telegram Desktop OSS credentials (no my.telegram.org needed).
        api_id = os.getenv("API_ID", "2040").strip() or "2040"
        api_hash = (
            os.getenv("API_HASH", "b18441a1ff607e10a989891a5462e627").strip()
            or "b18441a1ff607e10a989891a5462e627"
        )
        if not api_id.isdigit() or not api_hash:
            raise RuntimeError("Нет API_ID/API_HASH в .env")
        self._client = TelegramClient(
            str(SESSION),
            int(api_id),
            api_hash,
            device_model="TG Oxyfire Saver",
            system_version="macOS",
            app_version=APP_VERSION,
            lang_code="ru",
            system_lang_code="ru-RU",
        )
        await self._client.connect()
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        if await self._client.is_user_authorized():
            await self._mark_ready()
        else:
            await self._start_qr_login()

    async def _mark_ready(self) -> None:
        assert self._client is not None
        await self._stop_qr_wait()
        me = await self._client.get_me()
        self._account = f"{me.first_name} (@{me.username or '—'})"
        self._auth_state = "ready"
        self._qr_png = None
        if not self._worker_started:
            self._q = asyncio.Queue()
            asyncio.create_task(self._worker())
            self._worker_started = True
        # Продолжить сохранённую очередь
        with self._lock:
            to_run = [
                j.id
                for j in self._jobs.values()
                if j.status == "queued"
            ]
        for jid in to_run:
            await self._enqueue(jid)
        await self._setup_watchers()
        if not getattr(self, "_keepalive_started", False):
            self._keepalive_started = True
            asyncio.create_task(self._keepalive())

    async def _keepalive(self) -> None:
        while True:
            try:
                await asyncio.sleep(120)
                if self._auth_state != "ready" or not self._client:
                    continue
                if not self._client.is_connected():
                    await self._ensure_connected()
                else:
                    # лёгкий ping
                    await self._client.get_me()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self._log(f"keepalive: {e}")

    # ----- auth (QR / phone) -----
    async def _stop_qr_wait(self) -> None:
        task = self._qr_task
        self._qr_task = None
        self._qr = None
        if task and not task.done() and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    async def _start_qr_login(self) -> None:
        assert self._client is not None
        await self._stop_qr_wait()
        self._login_error = None
        self._login_busy = True
        self._auth_state = "qr"
        try:
            self._qr = await self._client.qr_login()
            self._qr_url = self._qr.url
            self._qr_png = qr_data_url(self._qr.url)
            expires = getattr(self._qr, "expires", None)
            try:
                self._qr_expires_at = expires.timestamp() if expires else time.time() + 30
            except Exception:  # noqa: BLE001
                self._qr_expires_at = time.time() + 30
            self._qr_task = asyncio.create_task(self._wait_qr())
            self._log("qr ready")
        except Exception as e:  # noqa: BLE001
            self._login_error = f"Не удалось создать QR: {e}"
            self._auth_state = "login"
            self._log(f"qr fail: {e}")
        finally:
            self._login_busy = False

    async def _wait_qr(self) -> None:
        assert self._qr is not None
        try:
            while True:
                try:
                    # Ждём до expires токена (не рвём раньше — иначе телефон
                    # сканирует уже недействительный QR).
                    user = await self._qr.wait()
                    self._log("qr accepted")
                    if user is not None or await self._client.is_user_authorized():  # type: ignore[union-attr]
                        await self._mark_ready()
                        return
                except SessionPasswordNeededError:
                    self._auth_state = "password"
                    self._qr_png = None
                    self._log("qr needs 2FA password")
                    return
                except asyncio.TimeoutError:
                    self._log("qr expired, recreate")
                    try:
                        await self._qr.recreate()
                        self._qr_url = self._qr.url
                        self._qr_png = qr_data_url(self._qr.url)
                        expires = getattr(self._qr, "expires", None)
                        try:
                            self._qr_expires_at = (
                                expires.timestamp() if expires else time.time() + 30
                            )
                        except Exception:  # noqa: BLE001
                            self._qr_expires_at = time.time() + 30
                    except Exception as e:  # noqa: BLE001
                        self._login_error = str(e)
                        self._log(f"qr recreate fail: {e}")
                        await asyncio.sleep(3)
                        await self._start_qr_login()
                        return
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            self._login_error = str(e)
            self._log(f"qr wait fail: {e}")

    def refresh_qr(self) -> dict[str, Any]:
        if not self._loop:
            return {"ok": False, "error": "Не готов"}
        asyncio.run_coroutine_threadsafe(self._start_qr_login(), self._loop)
        return {"ok": True, "started": True}

    def use_phone_login(self) -> dict[str, Any]:
        if not self._loop:
            return {"ok": False, "error": "Не готов"}

        async def _switch() -> None:
            await self._stop_qr_wait()
            self._qr_png = None
            self._auth_state = "login"

        asyncio.run_coroutine_threadsafe(_switch(), self._loop)
        return {"ok": True}

    def use_qr_login(self) -> dict[str, Any]:
        return self.refresh_qr()

    def send_code(self, phone: str) -> dict[str, Any]:
        phone = (phone or "").strip()
        if not phone.startswith("+"):
            return {"ok": False, "error": "Формат +79001234567"}
        if not self._loop:
            return {"ok": False, "error": "Не готов"}
        self._login_busy = True
        self._login_error = None
        asyncio.run_coroutine_threadsafe(self._send_code(phone), self._loop)
        return {"ok": True, "started": True}

    async def _send_code(self, phone: str) -> None:
        assert self._client
        try:
            for _ in range(3):
                try:
                    r = await self._client.send_code_request(phone)
                    self._phone = phone
                    self._phone_code_hash = r.phone_code_hash
                    self._auth_state = "code"
                    return
                except Exception as e:  # noqa: BLE001
                    self._login_error = str(e)
                    await asyncio.sleep(1)
            self._auth_state = "login"
        finally:
            self._login_busy = False

    def sign_in_code(self, code: str) -> dict[str, Any]:
        if not self._loop:
            return {"ok": False, "error": "Не готов"}
        self._login_busy = True
        asyncio.run_coroutine_threadsafe(
            self._sign_in_code((code or "").strip()), self._loop
        )
        return {"ok": True, "started": True}

    async def _sign_in_code(self, code: str) -> None:
        assert self._client
        try:
            try:
                await self._client.sign_in(
                    self._phone, code, phone_code_hash=self._phone_code_hash
                )
            except SessionPasswordNeededError:
                self._auth_state = "password"
                return
            await self._mark_ready()
        except Exception as e:  # noqa: BLE001
            self._login_error = str(e)
            self._auth_state = "code"
        finally:
            self._login_busy = False

    def sign_in_password(self, password: str) -> dict[str, Any]:
        if not self._loop:
            return {"ok": False, "error": "Не готов"}
        password = (password or "").strip()
        if not password:
            return {"ok": False, "error": "Введи пароль 2FA"}
        self._login_busy = True
        self._login_error = None
        fut = asyncio.run_coroutine_threadsafe(
            self._sign_in_password(password), self._loop
        )
        try:
            fut.result(timeout=60)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        if self._auth_state == "ready":
            return {"ok": True}
        return {"ok": False, "error": self._login_error or "Неверный пароль"}

    async def _sign_in_password(self, password: str) -> None:
        assert self._client
        try:
            await self._client.sign_in(password=password)
            await self._mark_ready()
            self._log("2FA ok")
        except Exception as e:  # noqa: BLE001
            self._login_error = str(e)
            self._auth_state = "password"
            self._log(f"2FA fail: {e}")
        finally:
            self._login_busy = False

    # ----- snapshot / settings -----
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            # Подтянуть превью с диска, если кадр появился mid-download
            for jid in self._order:
                j = self._jobs.get(jid)
                if j and not j.thumb:
                    t = thumb_data_url(j.peer, j.msg_id)
                    if t:
                        j.thumb = t
            jobs = [self._jobs[i].to_dict() for i in self._order]
        watchers = self.store.list_watchers()
        settings = self.store.all_settings()
        active = sum(1 for j in jobs if j["status"] == "downloading")
        return {
            "ready": self._auth_state == "ready",
            "auth_state": self._auth_state,
            "error": self._start_error,
            "login_error": self._login_error,
            "login_busy": self._login_busy,
            "account": self._account,
            "version": APP_VERSION,
            "app_name": APP_NAME,
            "out_dir": str(self.out_dir),
            "data_dir": str(ROOT),
            "session_path": str(SESSION) + ".session",
            "qr_png": self._qr_png,
            "qr_url": self._qr_url,
            "jobs": jobs,
            "paused": self._paused,
            "settings": settings,
            "watchers": watchers,
            "clipboard_mode": bool(settings.get("clipboard_mode")),
            "watchers_master": bool(settings.get("watchers_master", True)),
            "stats": {
                "queued": sum(1 for j in jobs if j["status"] == "queued"),
                "active": active,
                "done": sum(1 for j in jobs if j["status"] == "done"),
                "watchers_on": sum(1 for w in watchers if w.get("enabled")),
            },
        }

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        for k, v in (patch or {}).items():
            if k in (
                "media_filter",
                "filename_template",
                "clipboard_mode",
                "watchers_master",
                "out_dir",
                "notify_on_done",
                "watch_hours",
                "ui_lang",
            ):
                if k == "ui_lang":
                    v = "en" if str(v).lower().startswith("en") else "ru"
                self.store.set_setting(k, v)
                if k == "out_dir":
                    self.out_dir = Path(str(v))
                    self.out_dir.mkdir(parents=True, exist_ok=True)
                if k == "watchers_master" and self._loop and self._auth_state == "ready":
                    asyncio.run_coroutine_threadsafe(self._setup_watchers(), self._loop)
        return {"ok": True, "settings": self.store.all_settings()}

    # ----- queue controls -----
    def set_paused(self, paused: bool) -> dict[str, Any]:
        self._paused = bool(paused)
        if self._pause_event and self._loop:
            def _apply() -> None:
                assert self._pause_event
                if self._paused:
                    self._pause_event.clear()
                else:
                    self._pause_event.set()

            self._loop.call_soon_threadsafe(_apply)
        return {"ok": True, "paused": self._paused}

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return {"ok": False}
            if job.status in ("queued", "paused"):
                job.status = "cancelled"
            else:
                job.cancel_requested = True
                if job.status == "downloading":
                    job.status = "cancelled"
            self._persist_job(job)
        return {"ok": True}

    def pause_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status == "queued":
                job.status = "paused"
                self._persist_job(job)
        return {"ok": True}

    def resume_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return {"ok": False, "error": "Нет задачи"}
            # Сброс флага отмены — иначе «Продолжить» сразу снова отменяет
            job.cancel_requested = False
            if job.status == "paused":
                job.status = "queued"
                job.error = None
                self._persist_job(job)
                if self._loop:
                    asyncio.run_coroutine_threadsafe(self._enqueue(job.id), self._loop)
                return {"ok": True}
            if job.status in ("error", "cancelled", "skipped"):
                # Повтор даже если уже было в history done
                try:
                    self.store.upsert_history(
                        peer_key=peer_key(job.peer),
                        msg_id=job.msg_id,
                        channel=job.channel,
                        media_type=job.media_type,
                        path=job.path,
                        url=job.url,
                        status="retry",
                    )
                except Exception:
                    pass
                job.status = "queued"
                job.error = None
                job.progress = 0.0
                job.received_mb = 0.0
                job.total_mb = 0.0
                self._persist_job(job)
                if self._loop:
                    asyncio.run_coroutine_threadsafe(self._enqueue(job.id), self._loop)
                return {"ok": True}
        return {"ok": False, "error": f"Статус {job.status}"}

    def remove(self, job_id: str) -> None:
        self.cancel_job(job_id)
        with self._lock:
            self._jobs.pop(job_id, None)
            self._order = [i for i in self._order if i != job_id]
        try:
            self.store.delete_queue_job(job_id)
        except Exception:
            pass

    def clear_finished(self) -> None:
        """Убрать done/error/cancelled из очереди; запомнить dismissed, чтобы не вернулись."""
        removed: list[str] = []
        with self._lock:
            keep = []
            for i in self._order:
                j = self._jobs[i]
                if j.status in ("done", "error", "cancelled", "skipped"):
                    removed.append(i)
                    try:
                        self.store.dismiss_queue_item(peer_key(j.peer), int(j.msg_id))
                    except Exception:
                        pass
                    self._jobs.pop(i, None)
                else:
                    keep.append(i)
            self._order = keep
        for jid in removed:
            try:
                self.store.delete_queue_job(jid)
            except Exception:
                pass

    # ----- add work -----
    def add_text(self, text: str, source: str = "manual") -> dict[str, Any]:
        if self._auth_state != "ready":
            return {"ok": False, "error": "Нужен вход", "ids": []}
        targets = parse_targets(text)
        if not targets:
            return {"ok": False, "error": "Нет ссылок t.me", "ids": []}
        ids: list[str] = []
        for t in targets:
            for msg_id in t.msg_ids:
                jid = self._queue_message(t.peer, msg_id, t.raw, source)
                if jid:
                    ids.append(jid)
        return {"ok": True, "ids": ids, "count": len(ids)}

    def _queue_message(
        self, peer: int | str, msg_id: int, url: str, source: str
    ) -> str | None:
        pk = peer_key(peer)
        if self.store.is_downloaded(pk, msg_id):
            job = Job(
                id=uuid.uuid4().hex[:10],
                url=url,
                peer=peer,
                msg_id=msg_id,
                status="skipped",
                error="Уже скачано ранее",
                peer_label=f"{peer}/{msg_id}",
                source=source,
            )
            with self._lock:
                self._jobs[job.id] = job
                self._order.append(job.id)
            self._persist_job(job)
            return job.id

        job = Job(
            id=uuid.uuid4().hex[:10],
            url=url,
            peer=peer,
            msg_id=msg_id,
            status="queued",
            peer_label=f"{peer}/{msg_id}",
            source=source,
        )
        try:
            self.store.undismiss_queue_item(pk, msg_id)
        except Exception:
            pass
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
        self._persist_job(job)
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._enqueue(job.id), self._loop)
        return job.id

    async def _enqueue(self, job_id: str) -> None:
        assert self._q is not None
        await self._q.put(job_id)

    async def _worker(self) -> None:
        assert self._q is not None
        while True:
            job_id = await self._q.get()
            try:
                if self._pause_event:
                    await self._pause_event.wait()
                with self._lock:
                    job = self._jobs.get(job_id)
                if not job or job.status in ("cancelled", "paused", "skipped", "done"):
                    continue
                await self._process(job_id)
            finally:
                self._q.task_done()

    async def _ensure_connected(self) -> None:
        """После sleep/сети Telethon часто disconnected, а UI всё ещё ready."""
        assert self._client is not None
        if not self._client.is_connected():
            self._log("telegram reconnect…")
            await self._client.connect()
        if not await self._client.is_user_authorized():
            self._auth_state = "qr"
            self._account = None
            raise RuntimeError("Сессия Telegram истекла — войди заново")

    async def _process(self, job_id: str) -> None:
        assert self._client
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            return
        if job.cancel_requested or job.status == "cancelled":
            job.status = "cancelled"
            return

        job.status = "downloading"
        self._active_job_id = job_id
        self._persist_job(job)
        media_filter = self.store.get_setting("media_filter", "video")
        template = self.store.get_setting(
            "filename_template", "{channel}_{id}_{type}"
        )

        try:
            await self._ensure_connected()
            entity = await self._client.get_entity(job.peer)
            title = (
                getattr(entity, "title", None)
                or getattr(entity, "username", None)
                or str(job.peer)
            )
            job.channel = str(title)

            msg = await self._client.get_messages(entity, ids=job.msg_id)
            if not msg:
                raise RuntimeError("Сообщение удалено или недоступно")

            # Превью сразу, до долгой загрузки файла
            await self._maybe_thumb(job, msg)

            # альбом
            messages = [msg]
            if getattr(msg, "grouped_id", None):
                gid = msg.grouped_id
                # соседние сообщения того же альбома
                around = await self._client.get_messages(
                    entity, ids=list(range(max(1, job.msg_id - 10), job.msg_id + 11))
                )
                messages = [
                    m
                    for m in around
                    if m and getattr(m, "grouped_id", None) == gid
                ]
                if not messages:
                    messages = [msg]

            saved_any = False
            last_path = None
            for m in messages:
                if job.cancel_requested:
                    job.status = "cancelled"
                    return
                mtype = detect_media_type(m)
                if not matches_filter(mtype, media_filter):
                    continue
                if not m.media:
                    continue

                # дедуп каждой части альбома
                if self.store.is_downloaded(peer_key(job.peer), m.id) and m.id != job.msg_id:
                    continue

                await self._maybe_thumb(job, m)

                rollover_day_folders(self.out_dir)
                dest_dir = channel_out_dir(self.out_dir, job.channel)
                orig = original_name(m)
                # временное имя — Telethon сам поставит расширение
                stem = build_filename(
                    template=template,
                    channel=job.channel,
                    msg_id=m.id,
                    caption=m.message or "",
                    original=orig,
                    media_type=mtype or "media",
                    ext="",
                )
                # убрать возможное пустое расширение
                stem = stem.rstrip(".")
                out_base = dest_dir / stem
                thumb_path = THUMBS / f"{peer_key(job.peer)}_{m.id}.jpg"

                def progress(
                    received: int,
                    total: int,
                    j=job,
                    base=out_base,
                    tp=thumb_path,
                    mid=m.id,
                ) -> None:
                    if j.cancel_requested:
                        raise asyncio.CancelledError()
                    j.received_mb = received / 1e6
                    j.total_mb = (total / 1e6) if total else 0
                    j.progress = (100.0 * received / total) if total else 0.0
                    # Кадр из частичного файла: рано (≈400КБ) и с ss=0
                    if j.thumb:
                        return
                    last = getattr(j, "_thumb_try_at", 0)
                    if received < 400_000 or received - last < 800_000:
                        return
                    try:
                        j._thumb_try_at = received  # type: ignore[attr-defined]
                        candidates = list(base.parent.glob(base.name + ".*")) + (
                            [base] if base.exists() else []
                        )
                        for cand in candidates:
                            if cand.is_file() and cand.stat().st_size > 350_000:
                                if thumb_from_video(cand, tp, partial=True):
                                    j.thumb = thumb_data_url(j.peer, mid)
                                break
                    except Exception:
                        pass

                try:
                    path = await self._client.download_media(
                        m,
                        file=str(out_base),
                        progress_callback=progress,
                    )
                except asyncio.CancelledError:
                    job.status = "cancelled"
                    return

                if not path:
                    continue
                path_s = str(path)
                last_path = path_s
                job.media_type = mtype
                job.path = path_s
                saved_any = True
                self.store.upsert_history(
                    peer_key=peer_key(job.peer),
                    msg_id=m.id,
                    channel=job.channel,
                    media_type=mtype,
                    path=path_s,
                    url=job.url,
                    status="done",
                )

            if not saved_any:
                if detect_media_type(msg) is None:
                    raise RuntimeError("В сообщении нет медиа")
                raise RuntimeError(
                    f"Нет медиа типа «{media_filter}» (смени фильтр в настройках)"
                )

            job.status = "done"
            job.progress = 100.0
            job.path = last_path
            if last_path:
                mark_finder_label(last_path)
            if self.store.get_setting("notify_on_done", True) and last_path:
                notify("TG Oxyfire Saver", f"Готово: {Path(last_path).name}")

        except FloodWaitError as e:
            job.status = "error"
            job.error = f"Flood wait: подожди {e.seconds} сек. и повтори"
            self._log(job.error)
        except (ChannelPrivateError, UsernameNotOccupiedError):
            job.status = "error"
            job.error = "Нет доступа к каналу/чату"
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            # Одна авто-попытка после reconnect
            if "disconnected" in msg.lower() and not getattr(job, "_reconnected_once", False):
                try:
                    job._reconnected_once = True  # type: ignore[attr-defined]
                    self._log(f"retry after disconnect: {job.id}")
                    await self._ensure_connected()
                    job.status = "queued"
                    job.error = None
                    self._persist_job(job)
                    await self._enqueue(job.id)
                    return
                except Exception as e2:  # noqa: BLE001
                    msg = str(e2)
            if job.cancel_requested:
                job.status = "cancelled"
            else:
                job.status = "error"
                job.error = msg
                self.store.upsert_history(
                    peer_key=peer_key(job.peer),
                    msg_id=job.msg_id,
                    channel=job.channel,
                    media_type=job.media_type,
                    path=job.path,
                    url=job.url,
                    status="error",
                    error=msg,
                )
        finally:
            self._active_job_id = None
            self._persist_job(job)

    async def _maybe_thumb(self, job: Job, msg: Any) -> None:
        try:
            thumb_path = THUMBS / f"{peer_key(job.peer)}_{msg.id}.jpg"
            # Слишком мелкий mthumb (часто ~600B) выглядит как чёрный квадрат
            if thumb_path.exists() and thumb_path.stat().st_size < 1500:
                try:
                    thumb_path.unlink()
                except OSError:
                    pass

            if thumb_path.exists() and thumb_path.stat().st_size >= 1500:
                job.thumb = thumb_data_url(job.peer, msg.id)
                return

            # Крупный thumb: перебираем индексы (0..n), -1 иногда даёт крошечный
            for thumb_arg in (0, 1, 2, 3, -1):
                try:
                    await self._client.download_media(  # type: ignore[union-attr]
                        msg, file=str(thumb_path), thumb=thumb_arg
                    )
                    if thumb_path.exists() and thumb_path.stat().st_size >= 1500:
                        break
                    if thumb_path.exists():
                        thumb_path.unlink(missing_ok=True)
                except Exception:
                    continue

            if (not thumb_path.exists() or thumb_path.stat().st_size < 1500) and getattr(
                msg, "photo", None
            ):
                try:
                    await self._client.download_media(msg.photo, file=str(thumb_path))  # type: ignore[union-attr]
                except Exception:
                    pass

            if (not thumb_path.exists() or thumb_path.stat().st_size < 1500) and job.path:
                thumb_from_video(job.path, thumb_path)

            job.thumb = thumb_data_url(job.peer, msg.id)
            if not job.thumb:
                self._log(f"thumb miss msg={msg.id}")
        except Exception as e:  # noqa: BLE001
            self._log(f"thumb err: {e}")

    # ----- history -----
    def history(self, query: str = "") -> list[dict[str, Any]]:
        rows = self.store.history(query, limit=500)
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["thumb"] = thumb_data_url(
                row.get("peer_key") or "", int(row.get("msg_id") or 0)
            )
            out.append(item)
        return out

    def retry_history(self, peer_key_s: str, msg_id: int, url: str = "") -> dict[str, Any]:
        peer: int | str
        if peer_key_s.lstrip("-").isdigit():
            peer = int(peer_key_s)
        else:
            peer = peer_key_s
        self.store.upsert_history(
            peer_key=peer_key_s,
            msg_id=msg_id,
            status="retry",
            url=url or None,
        )
        with self.store._lock:
            self.store._conn.execute(
                "UPDATE history SET status='retry' WHERE peer_key=? AND msg_id=?",
                (peer_key_s, msg_id),
            )
            self.store._conn.commit()
        link = url or f"https://t.me/c/{str(peer).replace('-100', '')}/{msg_id}"
        jid = self._queue_message(peer, msg_id, link, "history")
        return {"ok": True, "id": jid}

    def logout(self) -> dict[str, Any]:
        """Выйти из Telegram → QR для другого аккаунта."""
        if not self._loop:
            return {"ok": False, "error": "Сервис не запущен"}

        async def _do() -> dict[str, Any]:
            try:
                if self._client:
                    try:
                        if await self._client.is_user_authorized():
                            await self._client.log_out()
                    except Exception:
                        try:
                            await self._client.disconnect()
                        except Exception:
                            pass
                for p in ROOT.glob("tg_saver*"):
                    if p.is_file():
                        try:
                            p.unlink()
                        except OSError:
                            pass
                self._account = None
                self._auth_state = "qr"
                self._qr_png = None
                self._qr_url = None
                self._worker_started = False
                api_id = os.getenv("API_ID", "").strip()
                api_hash = os.getenv("API_HASH", "").strip()
                self._client = TelegramClient(
                    str(SESSION),
                    int(api_id),
                    api_hash,
                    device_model="TG Oxyfire Saver",
                    system_version="macOS",
                    app_version=APP_VERSION,
                    lang_code="ru",
                    system_lang_code="ru-RU",
                )
                await self._client.connect()
                await self._start_qr_login()
                return {"ok": True}
            except Exception as e:  # noqa: BLE001
                self._login_error = str(e)
                return {"ok": False, "error": str(e)}

        fut = asyncio.run_coroutine_threadsafe(_do(), self._loop)
        try:
            return fut.result(timeout=60)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    # ----- watchers -----
    async def _setup_watchers(self) -> None:
        assert self._client
        # снять старые
        for h in self._watch_handlers:
            try:
                self._client.remove_event_handler(h, events.NewMessage)
            except Exception:  # noqa: BLE001
                try:
                    self._client.remove_event_handler(h)
                except Exception:
                    pass
        self._watch_handlers.clear()

        if not self.store.get_setting("watchers_master", True):
            self._log("watchers master off")
            return

        enabled = [w for w in self.store.list_watchers() if w.get("enabled")]
        if not enabled:
            return

        peers = []
        for w in enabled:
            pk = w["peer_key"]
            try:
                peers.append(int(pk) if pk.lstrip("-").isdigit() else pk)
            except ValueError:
                peers.append(pk)

        async def on_new(event: events.NewMessage.Event) -> None:
            try:
                if not self.store.get_setting("watchers_master", True):
                    return
                if not self._within_watch_hours():
                    return
                chat = await event.get_chat()
                pk = peer_key(
                    getattr(chat, "id", None)
                    or event.chat_id
                )
                # normalize -100
                watchers = {w["peer_key"]: w for w in self.store.list_watchers()}
                w = watchers.get(pk) or watchers.get(str(event.chat_id))
                if not w or not w.get("enabled"):
                    return
                msg = event.message
                mtype = detect_media_type(msg)
                flt = w.get("media_filter") or self.store.get_setting(
                    "media_filter", "video"
                )
                if not matches_filter(mtype, flt):
                    return
                title = (
                    getattr(chat, "title", None)
                    or getattr(chat, "username", None)
                    or pk
                )
                url = f"https://t.me/c/{str(pk).replace('-100','')}/{msg.id}"
                if getattr(chat, "username", None):
                    url = f"https://t.me/{chat.username}/{msg.id}"
                self._queue_message(int(pk) if str(pk).lstrip("-").isdigit() else pk, msg.id, url, "watcher")
                self.store.update_watcher_last(w["peer_key"], msg.id)
            except Exception as e:  # noqa: BLE001
                self._log(f"watcher event err: {e}")

        handler = on_new
        self._client.add_event_handler(handler, events.NewMessage(chats=peers))
        self._watch_handlers.append(handler)
        self._log(f"watchers active: {len(peers)}")

    def _within_watch_hours(self) -> bool:
        raw = (self.store.get_setting("watch_hours", "") or "").strip()
        if not raw:
            return True
        try:
            a, b = raw.split("-", 1)
            start, end = int(a), int(b)
            hour = time.localtime().tm_hour
            if start <= end:
                return start <= hour < end
            # через полночь, напр. 22-6
            return hour >= start or hour < end
        except Exception:  # noqa: BLE001
            return True

    def add_watcher(self, link_or_username: str) -> dict[str, Any]:
        if self._auth_state != "ready" or not self._loop:
            return {"ok": False, "error": "Нужен вход"}
        fut = asyncio.run_coroutine_threadsafe(
            self._add_watcher(link_or_username.strip()), self._loop
        )
        try:
            return fut.result(timeout=60)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    async def _add_watcher(self, text: str) -> dict[str, Any]:
        assert self._client
        targets = parse_targets(text)
        entity = None
        if targets:
            entity = await self._client.get_entity(targets[0].peer)
        else:
            # username or t.me/name
            m = re.search(r"t\.me/([A-Za-z0-9_]+)", text)
            name = m.group(1) if m else text.lstrip("@")
            entity = await self._client.get_entity(name)
        pk = peer_key(entity.id)
        title = (
            getattr(entity, "title", None)
            or getattr(entity, "username", None)
            or pk
        )
        # last message
        msgs = await self._client.get_messages(entity, limit=1)
        last_id = msgs[0].id if msgs else 0
        self.store.upsert_watcher(
            pk,
            str(title),
            enabled=True,
            media_filter=self.store.get_setting("media_filter", "video"),
            last_msg_id=last_id,
        )
        await self._setup_watchers()
        return {"ok": True, "watcher": {"peer_key": pk, "title": title}}

    def set_watcher_enabled(self, peer_key_s: str, enabled: bool) -> dict[str, Any]:
        self.store.set_watcher_enabled(peer_key_s, enabled)
        if self._loop and self._auth_state == "ready":
            asyncio.run_coroutine_threadsafe(self._setup_watchers(), self._loop)
        return {"ok": True}

    def stop_all_watchers(self) -> dict[str, Any]:
        self.store.set_setting("watchers_master", False)
        self.store.set_all_watchers(False)
        if self._loop and self._auth_state == "ready":
            asyncio.run_coroutine_threadsafe(self._setup_watchers(), self._loop)
        return {"ok": True}

    def delete_watcher(self, peer_key_s: str) -> dict[str, Any]:
        self.store.delete_watcher(peer_key_s)
        if self._loop and self._auth_state == "ready":
            asyncio.run_coroutine_threadsafe(self._setup_watchers(), self._loop)
        return {"ok": True}

    # helpers for menu bar / external
    def open_folder(self) -> None:
        open_path(str(self.out_dir))

    def reveal(self, path: str) -> None:
        reveal_path(path)
