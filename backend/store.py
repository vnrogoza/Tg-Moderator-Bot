import os
import sys
import time
import json
import sqlite3
import random
import string
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "moderator.db"


class ChatModerationStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.users: Dict[str, Dict[str, Any]] = {}
        self.messages: List[Dict[str, Any]] = []
        self.settings: Dict[str, Any] = {
            "muteThreshold": -10,
            "banThreshold": -25,
            "muteDurationMinutes": 120,
            "autoDeleteProfanity": True,
            "commentProfanityMessages": True,
            "commentToxicMessages": True,
            "commentNeutralMessages": False,
            "realTelegramConnected": False,
            "telegramBotUsername": "ModAIBot",
        }
        self._init_db()
        self._load_from_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT,
                    fullName TEXT,
                    avatarUrl TEXT,
                    rating INTEGER DEFAULT 0,
                    totalMessages INTEGER DEFAULT 0,
                    toxicMessages INTEGER DEFAULT 0,
                    profanityMessages INTEGER DEFAULT 0,
                    positiveMessages INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    mutedUntil INTEGER,
                    lastActivity INTEGER,
                    riskLevel TEXT DEFAULT 'low',
                    chatId TEXT,
                    history TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    userId TEXT,
                    userJson TEXT,
                    text TEXT,
                    timestamp INTEGER,
                    moderationJson TEXT,
                    isDeleted INTEGER DEFAULT 0,
                    botReply TEXT
                )
            """)
            conn.commit()
            conn.close()

    def _load_from_db(self):
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()

            # Load settings
            cur.execute("SELECT key, value FROM settings")
            rows = cur.fetchall()
            for r in rows:
                try:
                    self.settings[r["key"]] = json.loads(r["value"])
                except Exception:
                    self.settings[r["key"]] = r["value"]

            # Load users
            cur.execute("SELECT * FROM users")
            user_rows = cur.fetchall()

            if not user_rows:
                # Seed initial demo data
                conn.close()
                self._seed_initial_data()
                return

            self.users = {}
            for r in user_rows:
                u = dict(r)
                u["history"] = json.loads(u.get("history") or "[]")
                self.users[u["id"]] = u

            # Load recent messages
            cur.execute("SELECT * FROM messages ORDER BY timestamp ASC LIMIT 100")
            msg_rows = cur.fetchall()
            self.messages = []
            for r in msg_rows:
                m = {
                    "id": r["id"],
                    "userId": r["userId"],
                    "user": json.loads(r["userJson"] or "{}"),
                    "text": r["text"],
                    "timestamp": r["timestamp"],
                    "moderation": json.loads(r["moderationJson"] or "{}"),
                    "isDeleted": bool(r["isDeleted"]),
                    "botReply": r["botReply"],
                }
                self.messages.append(m)

            conn.close()

    def _persist_user(self, user: Dict[str, Any]):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (
                id, username, fullName, avatarUrl, rating, totalMessages,
                toxicMessages, profanityMessages, positiveMessages, status,
                mutedUntil, lastActivity, riskLevel, chatId, history
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username=excluded.username,
                fullName=excluded.fullName,
                avatarUrl=excluded.avatarUrl,
                rating=excluded.rating,
                totalMessages=excluded.totalMessages,
                toxicMessages=excluded.toxicMessages,
                profanityMessages=excluded.profanityMessages,
                positiveMessages=excluded.positiveMessages,
                status=excluded.status,
                mutedUntil=excluded.mutedUntil,
                lastActivity=excluded.lastActivity,
                riskLevel=excluded.riskLevel,
                chatId=excluded.chatId,
                history=excluded.history
        """, (
            str(user["id"]),
            user.get("username"),
            user.get("fullName"),
            user.get("avatarUrl"),
            user.get("rating", 0),
            user.get("totalMessages", 0),
            user.get("toxicMessages", 0),
            user.get("profanityMessages", 0),
            user.get("positiveMessages", 0),
            user.get("status", "active"),
            user.get("mutedUntil"),
            user.get("lastActivity", int(time.time() * 1000)),
            user.get("riskLevel", "low"),
            str(user.get("chatId", "")) if user.get("chatId") is not None else None,
            json.dumps(user.get("history", []), ensure_ascii=False),
        ))
        conn.commit()
        conn.close()

    def _persist_message(self, msg: Dict[str, Any]):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO messages (
                id, userId, userJson, text, timestamp, moderationJson, isDeleted, botReply
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            msg["id"],
            str(msg.get("userId", "")),
            json.dumps(msg.get("user", {}), ensure_ascii=False),
            msg.get("text", ""),
            msg.get("timestamp", int(time.time() * 1000)),
            json.dumps(msg.get("moderation", {}), ensure_ascii=False),
            1 if msg.get("isDeleted") else 0,
            msg.get("botReply"),
        ))
        conn.commit()
        conn.close()

    def _persist_settings(self):
        conn = self._get_connection()
        cur = conn.cursor()
        for k, v in self.settings.items():
            val = json.dumps(v, ensure_ascii=False)
            cur.execute("""
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """, (k, val))
        conn.commit()
        conn.close()

    def _seed_initial_data(self):
        now = int(time.time() * 1000)

        initial_users = [
            {            
                "id": "user_102",
                "username": "anna_dev",
                "fullName": "Анна Кузнецова",
                "avatarUrl": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&auto=format&fit=crop&q=80",
                "rating": 12,
                "totalMessages": 14,
                "toxicMessages": 0,
                "profanityMessages": 0,
                "positiveMessages": 10,
                "status": "active",
                "lastActivity": now - 1000 * 60 * 45,
                "riskLevel": "low",
                "history": [
                    {
                        "id": "h3",
                        "text": "Спасибо огромное за фикс, всё заработало с первого раза!",
                        "timestamp": now - 1000 * 60 * 120,
                        "score": 4,
                        "sentiment": "positive",
                        "profanity": False,
                        "actionTaken": "allow",
                    },
                ],
            },            
            {
                "id": "user_104",
                "username": "ivan_coder",
                "fullName": "Иван Петров",
                "avatarUrl": "https://images.unsplash.com/photo-1527980965255-d3b416303d12?w=100&auto=format&fit=crop&q=80",
                "rating": 3,
                "totalMessages": 6,
                "toxicMessages": 1,
                "profanityMessages": 0,
                "positiveMessages": 3,
                "status": "active",
                "lastActivity": now - 1000 * 60 * 5,
                "riskLevel": "medium",
                "history": [
                    {
                        "id": "h6",
                        "text": "Подскажите, где посмотреть параметры для Telegram Bot API?",
                        "timestamp": now - 1000 * 60 * 60,
                        "score": 1,
                        "sentiment": "neutral",
                        "profanity": False,
                        "actionTaken": "allow",
                    },
                ],
            },
        ]

        for u in initial_users:
            self.users[u["id"]] = u
            self._persist_user(u)

        initial_messages = [            
            {
                "id": "msg_2",
                "userId": "user_102",
                "user": {
                    "id": "user_102",
                    "username": "anna_dev",
                    "fullName": "Анна Кузнецова",
                    "rating": 12,
                    "status": "active",
                    "avatarUrl": initial_users[0]["avatarUrl"],
                },
                "text": "Спасибо огромное за фикс, всё заработало с первого раза! 👍",
                "timestamp": now - 1000 * 60 * 30,
                "moderation": {
                    "score": 3,
                    "sentiment": "positive",
                    "profanityDetected": False,
                    "profanityWords": [],
                    "toxicityScore": 0.0,
                    "categories": ["Благодарность", "Доброжелательность"],
                    "explanation": "Искренняя благодарность и позитивный тон.",
                    "action": "allow",
                },
            },            
            {
                "id": "msg_4",
                "userId": "user_104",
                "user": {
                    "id": "user_104",
                    "username": "ivan_coder",
                    "fullName": "Иван Петров",
                    "rating": 3,
                    "status": "active",
                    "avatarUrl": initial_users[1]["avatarUrl"],
                },
                "text": "Подскажите пожалуйста, в какой вкладке настраивается вебхук модератора?",
                "timestamp": now - 1000 * 60 * 10,
                "moderation": {
                    "score": 1,
                    "sentiment": "neutral",
                    "profanityDetected": False,
                    "profanityWords": [],
                    "toxicityScore": 0.0,
                    "categories": ["Вопрос по теме"],
                    "explanation": "Вежливый вопрос по функционалу чата.",
                    "action": "allow",
                },
            },
        ]

        self.messages = initial_messages
        for m in initial_messages:
            self._persist_message(m)

        self._persist_settings()

    def get_settings(self) -> Dict[str, Any]:
        return dict(self.settings)

    def update_settings(self, partial: Dict[str, Any]) -> Dict[str, Any]:
        self.settings.update(partial)
        self._persist_settings()
        return dict(self.settings)

    def recalc_risk_level(self, user: Dict[str, Any]):
        status = user.get("status", "active")
        rating = user.get("rating", 0)
        toxic = user.get("toxicMessages", 0)
        total = max(1, user.get("totalMessages", 0))
        mute_th = self.settings["muteThreshold"]

        if status == "banned" or status == "muted" or rating <= mute_th:
            user["riskLevel"] = "critical"
        elif rating < 0 or (toxic > 0 and (toxic / total) > 0.3):
            user["riskLevel"] = "high"
        elif toxic > 0:
            user["riskLevel"] = "medium"
        else:
            user["riskLevel"] = "low"

    def get_all_users(self) -> List[Dict[str, Any]]:
        now = int(time.time() * 1000)
        mute_th = self.settings["muteThreshold"]

        changed = False
        for u in self.users.values():
            if u.get("status") == "muted" and u.get("mutedUntil") and now > u["mutedUntil"]:
                u["status"] = "active"
                u.pop("mutedUntil", None)
                if u.get("rating", 0) <= mute_th or u.get("rating", 0) < 0:
                    u["rating"] = 0
                self._persist_user(u)
                changed = True
            self.recalc_risk_level(u)

        return sorted(self.users.values(), key=lambda x: x.get("rating", 0), reverse=True)

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not user_id:
            return None
        user = self.users.get(str(user_id))
        if not user:
            user = self.get_user_by_username(str(user_id))
        if user and user.get("status") == "muted" and user.get("mutedUntil"):
            now = int(time.time() * 1000)
            if now > user["mutedUntil"]:
                user["status"] = "active"
                user.pop("mutedUntil", None)
                if user.get("rating", 0) <= self.settings["muteThreshold"] or user.get("rating", 0) < 0:
                    user["rating"] = 0
                self.recalc_risk_level(user)
                self._persist_user(user)
        return user

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        clean = username.lstrip("@").lower().strip()
        for u in self.users.values():
            if u.get("username", "").lower() == clean:
                return u
        return None

    def get_or_create_user(
        self,
        user_id: str,
        username: str,
        full_name: str,
        avatar_url: Optional[str] = None,
        chat_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        user = self.get_user(user_id)
        if not user:
            user = {
                "id": str(user_id),
                "username": username or f"user_{user_id}",
                "fullName": full_name or username or "Участник",
                "avatarUrl": avatar_url or f"https://api.dicebear.com/7.x/bottts/svg?seed={user_id}",
                "rating": 0,
                "totalMessages": 0,
                "toxicMessages": 0,
                "profanityMessages": 0,
                "positiveMessages": 0,
                "status": "active",
                "lastActivity": int(time.time() * 1000),
                "riskLevel": "low",
                "history": [],
                "chatId": str(chat_id) if chat_id is not None else None,
            }
            self.users[str(user_id)] = user
            self._persist_user(user)
        else:
            updated = False
            if username and user.get("username") != username:
                user["username"] = username
                updated = True
            if full_name and user.get("fullName") != full_name:
                user["fullName"] = full_name
                updated = True
            if avatar_url and user.get("avatarUrl") != avatar_url:
                user["avatarUrl"] = avatar_url
                updated = True
            if chat_id is not None and user.get("chatId") != str(chat_id):
                user["chatId"] = str(chat_id)
                updated = True
            if updated:
                self._persist_user(user)
        return user

    def process_incoming_message(
        self,
        user_id: str,
        username: str,
        full_name: str,
        text: str,
        moderation: Dict[str, Any],
        avatar_url: Optional[str] = None,
        chat_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        user = self.get_or_create_user(user_id, username, full_name, avatar_url, chat_id)
        now = int(time.time() * 1000)
        user["lastActivity"] = now

        mute_th = self.settings["muteThreshold"]
        ban_th = self.settings["banThreshold"]

        # Check expired mute
        if user.get("status") == "muted" and user.get("mutedUntil") and now >= user["mutedUntil"]:
            user["status"] = "active"
            user.pop("mutedUntil", None)
            if user.get("rating", 0) <= mute_th or user.get("rating", 0) < 0:
                user["rating"] = 0
            self.recalc_risk_level(user)

        # Check currently muted (temporary or permanent)
        if user.get("status") == "muted":
            if user.get("mutedUntil") and now < user["mutedUntil"]:
                remaining_mins = max(1, int((user["mutedUntil"] - now) / 60000))
                explanation = f"Сообщение отклонено: пользователь находится во временном муте (осталось {remaining_mins} мин)."
                bot_reply = f"🔇 @{user['username']}, вы временно заблокированы в чате. До снятия ограничений: {remaining_mins} мин."
            elif not user.get("mutedUntil"):
                explanation = "Сообщение отклонено: пользователю установлен постоянный мут (режим «Только чтение»)."
                bot_reply = f"🔇 @{user['username']}, вам бессрочно запрещено писать сообщения в чате (режим «Только чтение»)."
            else:
                explanation = None
                bot_reply = None

            if explanation:
                blocked_msg = {
                    "id": f"msg_{now}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=4))}",
                    "userId": str(user_id),
                    "user": {
                        "id": user["id"],
                        "username": user["username"],
                        "fullName": user["fullName"],
                        "rating": user["rating"],
                        "status": user["status"],
                        "avatarUrl": user.get("avatarUrl"),
                    },
                    "text": text,
                    "timestamp": now,
                    "isDeleted": True,
                    "moderation": {
                        **moderation,
                        "action": "delete",
                        "explanation": explanation,
                    },
                    "botReply": bot_reply,
                }
                self.messages.append(blocked_msg)
                self._persist_message(blocked_msg)
                return {"message": blocked_msg, "user": user, "autoAction": "blocked_muted"}

        # Check currently banned (excluded from chat)
        if user.get("status") == "banned":
            blocked_msg = {
                "id": f"msg_{now}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=4))}",
                "userId": str(user_id),
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "fullName": user["fullName"],
                    "rating": user["rating"],
                    "status": user["status"],
                    "avatarUrl": user.get("avatarUrl"),
                },
                "text": text,
                "timestamp": now,
                "isDeleted": True,
                "moderation": {
                    **moderation,
                    "action": "ban",
                    "explanation": "Сообщение отклонено: пользователь заблокирован и исключён из чата (Бан).",
                },
                "botReply": f"🚫 @{user['username']} заблокирован и исключён из группы за систематические нарушения.",
            }
            self.messages.append(blocked_msg)
            self._persist_message(blocked_msg)
            return {"message": blocked_msg, "user": user, "autoAction": "blocked_banned"}

        # Apply cumulative rating
        score = moderation.get("score", 0)
        user["rating"] = user.get("rating", 0) + score
        user["totalMessages"] = user.get("totalMessages", 0) + 1

        if score < 0:
            user["toxicMessages"] = user.get("toxicMessages", 0) + 1
        elif score > 0:
            user["positiveMessages"] = user.get("positiveMessages", 0) + 1

        if moderation.get("profanityDetected"):
            user["profanityMessages"] = user.get("profanityMessages", 0) + 1

        # History log
        history_item = {
            "id": f"h_{now}",
            "text": text,
            "timestamp": now,
            "score": score,
            "sentiment": moderation.get("sentiment", "neutral"),
            "profanity": moderation.get("profanityDetected", False),
            "actionTaken": moderation.get("action", "allow"),
        }
        user.setdefault("history", []).insert(0, history_item)
        if len(user["history"]) > 50:
            user["history"].pop()

        auto_action = None
        bot_reply = None
        should_delete = False

        if user["rating"] <= ban_th:
            user["status"] = "banned"
            auto_action = "banned"
            should_delete = True
            bot_reply = f"🚫 Пользователь @{user['username']} исключён и заблокирован в чате (Бан). Кумулятивный рейтинг упал до критической отметки ({user['rating']} ≤ {ban_th})."
        elif user["rating"] <= mute_th:
            user["status"] = "muted"
            duration_ms = self.settings["muteDurationMinutes"] * 60 * 1000
            user["mutedUntil"] = now + duration_ms
            auto_action = "muted"
            should_delete = True
            sign = "+" if score > 0 else ""
            bot_reply = f"🔇 Пользователь @{user['username']} временно заблокирован на {self.settings['muteDurationMinutes']} мин! Накоплен высокий отрицательный рейтинг: {user['rating']} (порог мута: {mute_th}). Оценка сообщения: [{sign}{score}/5]"
        elif score <= -3:
            user["status"] = "warned"
            bot_reply = f"⚠️ Предупреждение @{user['username']}: оценка сообщения [{score}/5]. Причина: {moderation.get('explanation', '')}. Текущий рейтинг: {user['rating']}. При достижении {mute_th} включится авто-мут."

        if self.settings.get("autoDeleteProfanity") and moderation.get("profanityDetected"):
            should_delete = True
            if self.settings.get("commentProfanityMessages", True):
                bot_reply = f"⚠️ Сообщение удалено: использование ненормативной лексики в чате запрещено."
        elif self.settings.get("commentToxicMessages", True) and not bot_reply and not should_delete:
            is_toxic = (
                score < 0
                or moderation.get("sentiment") in ("negative", "aggressive")
                or moderation.get("toxicityScore", 0) > 0.3
            )
            if is_toxic:
                bot_reply = f"⚠️ Предупреждение: обнаружена токсичность в сообщении. Пожалуйста, соблюдайте правила вежливого общения."

        self.recalc_risk_level(user)
        self._persist_user(user)

        new_msg = {
            "id": f"msg_{now}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=4))}",
            "userId": str(user_id),
            "user": {
                "id": user["id"],
                "username": user["username"],
                "fullName": user["fullName"],
                "rating": user["rating"],
                "status": user["status"],
                "avatarUrl": user.get("avatarUrl"),
            },
            "text": text,
            "timestamp": now,
            "moderation": moderation,
            "isDeleted": should_delete,
            "botReply": bot_reply,
        }

        self.messages.append(new_msg)
        if len(self.messages) > 100:
            self.messages.pop(0)

        self._persist_message(new_msg)
        return {"message": new_msg, "user": user, "autoAction": auto_action}

    def get_messages(self) -> List[Dict[str, Any]]:
        return self.messages

    def clear_messages(self):
        self.messages = []
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM messages")
        conn.commit()
        conn.close()

    def update_user_status(
        self,
        user_id: str,
        status: str,
        duration_minutes: Optional[int] = None,
        reset_rating_if_negative: bool = True,
    ) -> Optional[Dict[str, Any]]:
        user = self.get_user(user_id)
        if not user:
            return None

        user["status"] = status
        now = int(time.time() * 1000)

        if status == "muted":
            if duration_minutes == 0:
                user["mutedUntil"] = None
            else:
                mins = duration_minutes if (duration_minutes is not None and duration_minutes > 0) else self.settings["muteDurationMinutes"]
                user["mutedUntil"] = now + mins * 60 * 1000
        elif status == "active":
            user.pop("mutedUntil", None)
            if reset_rating_if_negative and (user.get("rating", 0) <= self.settings["muteThreshold"] or user.get("rating", 0) < 0):
                user["rating"] = 0

        self.recalc_risk_level(user)
        self._persist_user(user)
        return user

    def unblock_user(self, user_id: str, new_rating: int = 0) -> Optional[Dict[str, Any]]:
        user = self.get_user(user_id)
        if not user:
            return None

        user["status"] = "active"
        user.pop("mutedUntil", None)
        user["rating"] = max(0, new_rating)
        self.recalc_risk_level(user)
        self._persist_user(user)
        return user

    def reset_user_rating(self, user_id: str, new_rating: int = 0) -> Optional[Dict[str, Any]]:
        user = self.get_user(user_id)
        if not user:
            return None
        user["rating"] = new_rating
        user["status"] = "active"
        user.pop("mutedUntil", None)
        self.recalc_risk_level(user)
        self._persist_user(user)
        return user

    def get_stats(self) -> Dict[str, Any]:
        total_messages = len(self.messages)
        total_violations = 0
        profanity_count = 0
        sum_rating = 0
        muted_users_count = 0
        banned_users_count = 0

        sentiment_counts = {
            "positive": 0,
            "neutral": 0,
            "negative": 0,
            "aggressive": 0,
            "constructive": 0,
        }

        for msg in self.messages:
            mod = msg.get("moderation")
            if mod:
                if mod.get("score", 0) < 0 or mod.get("profanityDetected"):
                    total_violations += 1
                if mod.get("profanityDetected"):
                    profanity_count += 1
                sent = mod.get("sentiment", "neutral")
                if sent in sentiment_counts:
                    sentiment_counts[sent] += 1

        all_users = self.get_all_users()
        for u in all_users:
            sum_rating += u.get("rating", 0)
            if u.get("status") == "muted":
                muted_users_count += 1
            if u.get("status") == "banned":
                banned_users_count += 1

        avg_rating = round(sum_rating / len(all_users), 1) if all_users else 0.0

        return {
            "totalMessages": total_messages,
            "totalViolations": total_violations,
            "profanityCount": profanity_count,
            "averageRating": avg_rating,
            "mutedUsersCount": muted_users_count,
            "bannedUsersCount": banned_users_count,
            "totalUsersCount": len(all_users),
            "sentimentCounts": sentiment_counts,
        }


store = ChatModerationStore()
