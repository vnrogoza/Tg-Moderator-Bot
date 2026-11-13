#!/usr/bin/env python3
"""
Telegram Chat Moderator - Python Backend Server
Supports running with zero external dependencies (standard library http.server),
or with FastAPI/Uvicorn if installed.
"""

import os
import sys
import json
import time
import argparse
import mimetypes
import subprocess
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from socketserver import ThreadingMixIn

_frontend_build_done = threading.Event()
_frontend_build_done.set()

# Add root directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Try loading .env if python-dotenv is available, otherwise manual parse
env_path = ROOT_DIR / ".env"
if env_path.is_file():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from backend.store import store
from backend.gemini_moderator import analyze_message_with_gemini
from backend.telegram_bot import telegram_service


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class ModeratorRequestHandler(BaseHTTPRequestHandler):
    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/health":
            self.send_json({"status": "ok", "backend": "python", "timestamp": int(time.time() * 1000)})
            return

        if path == "/api/chat/messages":
            self.send_json({"messages": store.get_messages()})
            return

        if path == "/api/users":
            self.send_json({"users": store.get_all_users()})
            return

        if path.startswith("/api/users/"):
            uid = path.replace("/api/users/", "").strip()
            user = store.get_user(uid)
            if user:
                self.send_json({"user": user})
            else:
                self.send_json({"error": "Пользователь не найден"}, status=404)
            return

        if path == "/api/stats":
            self.send_json({"stats": store.get_stats()})
            return

        if path == "/api/settings":
            self.send_json({"settings": store.get_settings()})
            return

        if path == "/api/telegram/status":
            token = telegram_service.get_token()
            if not token:
                self.send_json({
                    "connected": False,
                    "message": "Токен бота не настроен. Добавьте его в настройках или в TELEGRAM_BOT_TOKEN.",
                })
                return
            result = telegram_service.init_bot()
            status = telegram_service.get_status()
            self.send_json({
                "connected": result.get("success", False),
                "botName": result.get("botName"),
                "isPolling": status.get("isPolling", False),
                "lastUpdateId": status.get("lastUpdateId", 0),
                "conflict": status.get("conflict", False),
                "consecutiveConflicts": status.get("consecutiveConflicts", 0),
                "lastError": status.get("lastError"),
                "error": result.get("error"),
            })
            return

        if path == "/api/telegram/webhook-info":
            info = telegram_service.get_webhook_info()
            self.send_json(info)
            return

        # Static files & SPA fallback
        self.serve_static_or_spa(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = self.read_json_body()

        if path == "/api/moderation/analyze":
            text = body.get("text", "")
            if not text:
                self.send_json({"error": "Параметр 'text' обязателен."}, status=400)
                return
            result = analyze_message_with_gemini(text, body.get("userSummary"))
            self.send_json(result)
            return

        if path == "/api/chat/send":
            text = body.get("text", "")
            if not text:
                self.send_json({"error": "Параметр 'text' обязателен."}, status=400)
                return

            uid = body.get("userId") or f"user_{str(int(time.time() * 1000))[-4:]}"
            uname = body.get("username") or f"user_{uid}"
            fname = body.get("fullName") or uname

            existing = store.get_user(uid)
            user_summary = (
                f"Рейтинг: {existing.get('rating')}, нарушений: {existing.get('toxicMessages')}, статус: {existing.get('status')}"
                if existing
                else None
            )

            mod = analyze_message_with_gemini(text, user_summary)
            outcome = store.process_incoming_message(
                user_id=uid,
                username=uname,
                full_name=fname,
                text=text,
                moderation=mod,
                avatar_url=body.get("avatarUrl"),
            )
            self.send_json(outcome)
            return

        if path == "/api/chat/clear":
            store.clear_messages()
            self.send_json({"success": True})
            return

        if path.startswith("/api/users/") and path.endswith("/action"):
            parts = path.split("/")
            # path is /api/users/<id>/action
            uid = parts[3]
            action = body.get("action")
            duration = body.get("durationMinutes")
            new_rating = body.get("newRating")

            user = store.get_user(uid)
            chat_id = user.get("chatId") if user else None

            if action == "mute":
                is_permanent = (duration == 0)
                if is_permanent:
                    updated = store.update_user_status(uid, "muted", duration_minutes=0)
                    until_unix = 0
                else:
                    dur = duration if (duration is not None and duration > 0) else 60
                    updated = store.update_user_status(uid, "muted", duration_minutes=dur)
                    until_unix = int(time.time()) + dur * 60

                target_chats = [chat_id] if chat_id else telegram_service.get_known_chat_ids()
                for c_id in target_chats:
                    telegram_service.restrict_member_sync(c_id, uid, until_unix)
                self.send_json({"user": updated, "success": True})
                return

            elif action in ("unmute", "unban"):
                target_score = new_rating if new_rating is not None else 0
                updated = store.unblock_user(uid, target_score)
                tg_res = telegram_service.unban_and_unmute_member_sync(uid, chat_id)
                self.send_json({"user": updated, "telegram": tg_res, "success": True})
                return

            elif action == "ban":
                updated = store.update_user_status(uid, "banned")
                tg_res = telegram_service.ban_member_sync(uid, chat_id)
                self.send_json({"user": updated, "telegram": tg_res, "success": True})
                return

            elif action == "reset_rating":
                target_score = new_rating if new_rating is not None else 0
                updated = store.reset_user_rating(uid, target_score)
                tg_res = telegram_service.unban_and_unmute_member_sync(uid, chat_id)
                self.send_json({"user": updated, "telegram": tg_res, "success": True})
                return

            self.send_json({"error": "Неизвестное действие"}, status=400)
            return

        if path == "/api/settings":
            updated = store.update_settings(body)
            self.send_json({"settings": updated})
            return

        if path == "/api/telegram/start-polling":
            telegram_service.start_polling_thread()
            self.send_json({"success": True, "message": "Long Polling запущен"})
            return

        if path == "/api/telegram/stop-polling":
            telegram_service.stop_polling()
            self.send_json({"success": True, "message": "Long Polling остановлен"})
            return

        if path == "/api/telegram/set-token":
            telegram_service.set_token(body.get("token", ""))
            res = telegram_service.init_bot()
            self.send_json(res)
            return

        if path == "/api/telegram/set-webhook":
            res = telegram_service.set_webhook(body.get("webhookUrl", ""))
            self.send_json(res)
            return

        if path == "/api/telegram/webhook":
            telegram_service.handle_webhook_update_sync(body)
            self.send_json({"ok": True})
            return

        self.send_json({"error": "Endpoint not found"}, status=404)

    def serve_static_or_spa(self, rel_path):
        dist_dir = ROOT_DIR / "dist"
        if not (dist_dir / "index.html").is_file() and not _frontend_build_done.is_set():
            _frontend_build_done.wait(timeout=25)

        clean_path = rel_path.lstrip("/")
        target_file = dist_dir / clean_path

        # If specific file exists in dist
        if clean_path and target_file.is_file():
            self.send_file(target_file)
            return

        # Otherwise serve index.html
        index_file = dist_dir / "index.html"
        if index_file.is_file():
            self.send_file(index_file)
            return

        self.send_response(404)
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(b"Frontend not built. Run 'npm run build' first.")

    def send_file(self, file_path: Path):
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "application/octet-stream"

        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        # Clean logging
        pass


def _build_frontend_bg():
    try:
        vite_bin = ROOT_DIR / "node_modules" / ".bin" / "vite"
        cmd = [str(vite_bin), "build"] if vite_bin.is_file() else ["npx", "vite", "build"]
        subprocess.run(cmd, cwd=str(ROOT_DIR), check=True)
    except Exception as e:
        print(f"Warning building frontend: {e}", flush=True)
    finally:
        _frontend_build_done.set()


def _init_telegram_bg():
    try:
        token = telegram_service.get_token()
        if token:
            res = telegram_service.init_bot()
            if res.get("success"):
                print(f"✅ Telegram bot connected: @{res.get('botName')}", flush=True)
                if os.getenv("TELEGRAM_POLLING_ENABLED") != "false":
                    telegram_service.start_polling_thread()
    except Exception as e:
        print(f"Warning initializing Telegram bot: {e}", flush=True)


def run_python_server(host="0.0.0.0", port=3000):
    server_address = (host, port)
    httpd = ThreadedHTTPServer(server_address, ModeratorRequestHandler)
    print(f"🚀 Telegram Chat Moderator Server (Pure Python) running on http://{host}:{port}", flush=True)

    dist_dir = ROOT_DIR / "dist"
    if not (dist_dir / "index.html").is_file():
        print("dist/ not found, building frontend assets in background...", flush=True)
        _frontend_build_done.clear()
        threading.Thread(target=_build_frontend_bg, daemon=True).start()

    threading.Thread(target=_init_telegram_bg, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Python server...", flush=True)
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telegram Chat Moderator Server (Python)")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", 3000)), help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address")
    args, _ = parser.parse_known_args()

    run_python_server(host=args.host, port=args.port)
