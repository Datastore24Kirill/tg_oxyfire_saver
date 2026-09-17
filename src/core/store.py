"""SQLite: настройки, история, дедуп, сторожи."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "tg_saver.db"

DEFAULT_SETTINGS = {
    "media_filter": "video",  # video|photo|document|all
    "filename_template": "{channel}_{id}_{type}",
    "clipboard_mode": False,
    "watchers_master": True,
    "out_dir": str(Path.home() / "Desktop" / "TelegramCaptures"),
    "notify_on_done": True,
    # Расписание сторожа: пусто = всегда; иначе "9-22" (локальные часы)
    "watch_hours": "",
    "ui_lang": "ru",  # ru|en
}


class Store:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        with self._lock:
            c = self._conn
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS history (
                    peer_key TEXT NOT NULL,
                    msg_id INTEGER NOT NULL,
                    channel TEXT,
                    media_type TEXT,
                    path TEXT,
                    url TEXT,
                    status TEXT,
                    error TEXT,
                    created_at REAL,
                    PRIMARY KEY (peer_key, msg_id)
                );
                CREATE TABLE IF NOT EXISTS watchers (
                    peer_key TEXT PRIMARY KEY,
                    title TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    media_filter TEXT,
                    last_msg_id INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS queue (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    peer TEXT NOT NULL,
                    msg_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    channel TEXT,
                    media_type TEXT,
                    source TEXT,
                    created_at REAL,
                    progress REAL DEFAULT 0,
                    received_mb REAL DEFAULT 0,
                    total_mb REAL DEFAULT 0,
                    path TEXT,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS queue_dismissed (
                    peer_key TEXT NOT NULL,
                    msg_id INTEGER NOT NULL,
                    dismissed_at REAL,
                    PRIMARY KEY (peer_key, msg_id)
                );
                """
            )
            c.commit()
            for k, v in DEFAULT_SETTINGS.items():
                cur = c.execute("SELECT 1 FROM settings WHERE key=?", (k,))
                if cur.fetchone() is None:
                    c.execute(
                        "INSERT INTO settings(key,value) VALUES(?,?)",
                        (k, json.dumps(v)),
                    )
            c.commit()

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
        if not row:
            return DEFAULT_SETTINGS.get(key, default)
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )
            self._conn.commit()

    def all_settings(self) -> dict[str, Any]:
        out = dict(DEFAULT_SETTINGS)
        with self._lock:
            for row in self._conn.execute("SELECT key, value FROM settings"):
                try:
                    out[row["key"]] = json.loads(row["value"])
                except json.JSONDecodeError:
                    out[row["key"]] = row["value"]
        return out

    def is_downloaded(self, peer_key: str, msg_id: int) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM history WHERE peer_key=? AND msg_id=? AND status='done'",
                (peer_key, msg_id),
            ).fetchone()
        return row is not None

    def upsert_history(self, **kwargs: Any) -> None:
        peer_key = str(kwargs["peer_key"])
        msg_id = int(kwargs["msg_id"])
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO history(peer_key,msg_id,channel,media_type,path,url,status,error,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(peer_key,msg_id) DO UPDATE SET
                  channel=excluded.channel,
                  media_type=excluded.media_type,
                  path=excluded.path,
                  url=excluded.url,
                  status=excluded.status,
                  error=excluded.error,
                  created_at=excluded.created_at
                """,
                (
                    peer_key,
                    msg_id,
                    kwargs.get("channel"),
                    kwargs.get("media_type"),
                    kwargs.get("path"),
                    kwargs.get("url"),
                    kwargs.get("status", "done"),
                    kwargs.get("error"),
                    kwargs.get("created_at", time.time()),
                ),
            )
            self._conn.commit()

    def history(self, query: str = "", limit: int = 500) -> list[dict[str, Any]]:
        q = f"%{(query or '').strip()}%"
        with self._lock:
            if query.strip():
                rows = self._conn.execute(
                    """
                    SELECT * FROM history
                    WHERE channel LIKE ? OR url LIKE ? OR path LIKE ? OR cast(msg_id as text) LIKE ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (q, q, q, q, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM history ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def list_watchers(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM watchers ORDER BY title COLLATE NOCASE"
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_watcher(
        self,
        peer_key: str,
        title: str,
        enabled: bool = True,
        media_filter: str | None = None,
        last_msg_id: int | None = None,
    ) -> None:
        with self._lock:
            existing = self._conn.execute(
                "SELECT last_msg_id FROM watchers WHERE peer_key=?", (peer_key,)
            ).fetchone()
            if existing:
                self._conn.execute(
                    """
                    UPDATE watchers SET title=?, enabled=?, media_filter=COALESCE(?, media_filter),
                      last_msg_id=COALESCE(?, last_msg_id)
                    WHERE peer_key=?
                    """,
                    (
                        title,
                        1 if enabled else 0,
                        media_filter,
                        last_msg_id,
                        peer_key,
                    ),
                )
            else:
                self._conn.execute(
                    """
                    INSERT INTO watchers(peer_key,title,enabled,media_filter,last_msg_id)
                    VALUES(?,?,?,?,?)
                    """,
                    (
                        peer_key,
                        title,
                        1 if enabled else 0,
                        media_filter or "video",
                        last_msg_id or 0,
                    ),
                )
            self._conn.commit()

    def set_watcher_enabled(self, peer_key: str, enabled: bool) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE watchers SET enabled=? WHERE peer_key=?",
                (1 if enabled else 0, peer_key),
            )
            self._conn.commit()

    def set_all_watchers(self, enabled: bool) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE watchers SET enabled=?", (1 if enabled else 0,)
            )
            self._conn.commit()

    def delete_watcher(self, peer_key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM watchers WHERE peer_key=?", (peer_key,))
            self._conn.commit()

    def update_watcher_last(self, peer_key: str, last_msg_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE watchers SET last_msg_id=? WHERE peer_key=?",
                (last_msg_id, peer_key),
            )
            self._conn.commit()

    def upsert_queue_job(self, job: dict[str, Any]) -> None:
        """Активная очередь (queued/downloading/paused) — переживает рестарт."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO queue(
                  id,url,peer,msg_id,status,channel,media_type,source,
                  created_at,progress,received_mb,total_mb,path,error
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  url=excluded.url,
                  peer=excluded.peer,
                  msg_id=excluded.msg_id,
                  status=excluded.status,
                  channel=excluded.channel,
                  media_type=excluded.media_type,
                  source=excluded.source,
                  created_at=excluded.created_at,
                  progress=excluded.progress,
                  received_mb=excluded.received_mb,
                  total_mb=excluded.total_mb,
                  path=excluded.path,
                  error=excluded.error
                """,
                (
                    job["id"],
                    job.get("url") or "",
                    str(job.get("peer") or ""),
                    int(job.get("msg_id") or 0),
                    job.get("status") or "queued",
                    job.get("channel"),
                    job.get("media_type"),
                    job.get("source") or "manual",
                    float(job.get("created_at") or time.time()),
                    float(job.get("progress") or 0),
                    float(job.get("received_mb") or 0),
                    float(job.get("total_mb") or 0),
                    job.get("path"),
                    job.get("error"),
                ),
            )
            self._conn.commit()

    def delete_queue_job(self, job_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM queue WHERE id=?", (job_id,))
            self._conn.commit()

    def list_queue_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM queue ORDER BY created_at ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def clear_finished_queue(self) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM queue WHERE status IN ('done','error','cancelled','skipped')"
            )
            self._conn.commit()

    def dismiss_queue_item(self, peer_key: str, msg_id: int) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO queue_dismissed(peer_key, msg_id, dismissed_at)
                VALUES(?,?,?)
                ON CONFLICT(peer_key, msg_id) DO UPDATE SET dismissed_at=excluded.dismissed_at
                """,
                (str(peer_key), int(msg_id), time.time()),
            )
            self._conn.commit()

    def is_queue_dismissed(self, peer_key: str, msg_id: int) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM queue_dismissed WHERE peer_key=? AND msg_id=?",
                (str(peer_key), int(msg_id)),
            ).fetchone()
        return row is not None

    def undismiss_queue_item(self, peer_key: str, msg_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM queue_dismissed WHERE peer_key=? AND msg_id=?",
                (str(peer_key), int(msg_id)),
            )
            self._conn.commit()
