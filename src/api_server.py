"""Локальный HTTP API для окна и menu bar."""

from __future__ import annotations

from flask import Flask, jsonify, request, send_from_directory
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def create_app(service) -> Flask:
    app = Flask(__name__, static_folder=str(ROOT / "gui"), static_url_path="")

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/state")
    def state():
        return jsonify(service.snapshot())

    @app.post("/api/add")
    def add():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(service.add_text(data.get("text", ""), source=data.get("source", "manual")))

    @app.post("/api/settings")
    def settings():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(service.update_settings(data))

    @app.post("/api/pause")
    def pause():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(service.set_paused(bool(data.get("paused", True))))

    @app.post("/api/job/cancel")
    def job_cancel():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(service.cancel_job(data.get("id", "")))

    @app.post("/api/job/pause")
    def job_pause():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(service.pause_job(data.get("id", "")))

    @app.post("/api/job/resume")
    def job_resume():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(service.resume_job(data.get("id", "")))

    @app.post("/api/job/remove")
    def job_remove():
        data = request.get_json(force=True, silent=True) or {}
        service.remove(data.get("id", ""))
        return jsonify({"ok": True})

    @app.post("/api/clear_finished")
    def clear_finished():
        service.clear_finished()
        return jsonify({"ok": True})

    @app.get("/api/history")
    def history():
        return jsonify({"items": service.history(request.args.get("q", ""))})

    @app.post("/api/history/retry")
    def history_retry():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(
            service.retry_history(
                data.get("peer_key", ""),
                int(data.get("msg_id", 0)),
                data.get("url", ""),
            )
        )

    @app.post("/api/auth/qr/refresh")
    def qr_refresh():
        return jsonify(service.refresh_qr())

    @app.post("/api/auth/phone")
    def auth_phone():
        return jsonify(service.use_phone_login())

    @app.post("/api/auth/qr")
    def auth_qr():
        return jsonify(service.use_qr_login())

    @app.post("/api/auth/send_code")
    def send_code():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(service.send_code(data.get("phone", "")))

    @app.post("/api/auth/sign_code")
    def sign_code():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(service.sign_in_code(data.get("code", "")))

    @app.post("/api/auth/sign_password")
    def sign_password():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(service.sign_in_password(data.get("password", "")))

    @app.post("/api/auth/logout")
    def auth_logout():
        return jsonify(service.logout())

    @app.post("/api/watchers/add")
    def watchers_add():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(service.add_watcher(data.get("text", "")))

    @app.post("/api/watchers/enable")
    def watchers_enable():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(
            service.set_watcher_enabled(data.get("peer_key", ""), bool(data.get("enabled", True)))
        )

    @app.post("/api/watchers/stop_all")
    def watchers_stop():
        return jsonify(service.stop_all_watchers())

    @app.post("/api/watchers/delete")
    def watchers_delete():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(service.delete_watcher(data.get("peer_key", "")))

    @app.post("/api/open_folder")
    def open_folder():
        service.open_folder()
        return jsonify({"ok": True})

    @app.post("/api/reveal")
    def reveal():
        data = request.get_json(force=True, silent=True) or {}
        service.reveal(data.get("path", ""))
        return jsonify({"ok": True})

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True})

    return app
