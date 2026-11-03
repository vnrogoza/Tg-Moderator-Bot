import time
import random
import string
from typing import Dict, Any, List, Optional


class ChatModerationStore:
    def __init__(self):
        self.users: Dict[str, Dict[str, Any]] = {}
        self.messages: List[Dict[str, Any]] = []
        self.settings: Dict[str, Any] = {
            "muteThreshold": -10,
            "banThreshold": -25,
            "muteDurationMinutes": 120,
            "autoDeleteProfanity": True,
            "showRatingBadgeUnderAll": False,
            "commentNeutralMessages": False,
            "realTelegramConnected": False,
            "telegramBotUsername": "ModAIBot",
        }
        self.seed_initial_data()

    def seed_initial_data(self):
        now = int(time.time() * 1000)

        initial_users = [
            {
                "id": "user_101",
                "username": "alex_tech",
                "fullName": "Алексей Смирнов",
                "avatarUrl": "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=100&auto=format&fit=crop&q=80",
                "rating": 18,
                "totalMessages": 24,
                "toxicMessages": 0,
                "profanityMessages": 0,
                "positiveMessages": 19,
                "status": "active",
                "lastActivity": now - 1000 * 60 * 15,
                "riskLevel": "low",
                "history": [
                    {
                        "id": "h1",
                        "text": "Привет всем! Если кому-то нужна помощь с настройкой вебхуков — пишите, подготовил инструкцию.",
                        "timestamp": now - 1000 * 60 * 60 * 3,
                        "score": 4,
                        "sentiment": "constructive",
                        "profanity": False,
                        "actionTaken": "allow",
                    },
                    {
                        "id": "h2",
                        "text": "Отличная идея, поддерживаю! Добавил ссылку на документацию в закреп.",
                        "timestamp": now - 1000 * 60 * 30,
                        "score": 3,
                        "sentiment": "positive",
                        "profanity": False,
                        "actionTaken": "allow",
                    },
                ],
            },
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
                "id": "user_103",
                "username": "dmitry_chaos",
                "fullName": "Дмитрий Тролль",
                "avatarUrl": "https://images.unsplash.com/photo-1570295999919-56ceb5ecca61?w=100&auto=format&fit=crop&q=80",
                "rating": -14,
                "totalMessages": 9,
                "toxicMessages": 6,
                "profanityMessages": 3,
                "positiveMessages": 0,
                "status": "muted",
                "mutedUntil": now + 1000 * 60 * 95,
                "lastActivity": now - 1000 * 60 * 25,
                "riskLevel": "critical",
                "history": [
                    {
                        "id": "h4",
                        "text": "Вы все тут тупые и ничего не понимаете, идите на*** отсюда",
                        "timestamp": now - 1000 * 60 * 180,
                        "score": -5,
                        "sentiment": "aggressive",
                        "profanity": True,
                        "actionTaken": "delete",
                    },
                    {
                        "id": "h5",
                        "text": "Админ криворукий даун, удали свой чат",
                        "timestamp": now - 1000 * 60 * 25,
                        "score": -5,
                        "sentiment": "aggressive",
                        "profanity": True,
                        "actionTaken": "mute_temp",
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

        self.messages = [
            {
                "id": "msg_1",
                "userId": "user_101",
                "user": {
                    "id": "user_101",
                    "username": "alex_tech",
                    "fullName": "Алексей Смирнов",
                    "rating": 14,
                    "status": "active",
                    "avatarUrl": initial_users[0]["avatarUrl"],
                },
                "text": "Привет всем! Если кому-то нужна помощь с настройкой вебхуков — пишите, подготовил инструкцию.",
                "timestamp": now - 1000 * 60 * 40,
                "moderation": {
                    "score": 4,
                    "sentiment": "constructive",
                    "profanityDetected": False,
                    "profanityWords": [],
                    "toxicityScore": 0.0,
                    "categories": ["Взаимопомощь", "Конструктив"],
                    "explanation": "Предложение бескорыстной помощи участникам чата и полезный материал.",
                    "action": "allow",
                },
            },
            {
                "id": "msg_2",
                "userId": "user_102",
                "user": {
                    "id": "user_102",
                    "username": "anna_dev",
                    "fullName": "Анна Кузнецова",
                    "rating": 12,
                    "status": "active",
                    "avatarUrl": initial_users[1]["avatarUrl"],
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
                "id": "msg_3",
                "userId": "user_103",
                "user": {
                    "id": "user_103",
                    "username": "dmitry_chaos",
                    "fullName": "Дмитрий Тролль",
                    "rating": -9,
                    "status": "active",
                    "avatarUrl": initial_users[2]["avatarUrl"],
                },
                "text": "Админ криворукий даун, удали свой чат и не позорься",
                "timestamp": now - 1000 * 60 * 25,
                "isDeleted": True,
                "moderation": {
                    "score": -5,
                    "sentiment": "aggressive",
                    "profanityDetected": False,
                    "profanityWords": ["даун"],
                    "toxicityScore": 0.95,
                    "categories": ["Оскорбление", "Агрессия", "Троллинг"],
                    "explanation": "Прямое грубое оскорбление администрации. Токсичность 95%.",
                    "action": "mute_temp",
                    "muteDurationMinutes": 120,
                },
                "botReply": "🔇 Пользователь @dmitry_chaos временно заблокирован на 2 ч. Причина: Накоплен критический отрицательный рейтинг (-14). Оценка сообщения: [-5/5]",
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
                    "avatarUrl": initial_users[3]["avatarUrl"],
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

    def get_settings(self) -> Dict[str, Any]:
        return dict(self.settings)

    def update_settings(self, partial: Dict[str, Any]) -> Dict[str, Any]:
        self.settings.update(partial)
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

        for u in self.users.values():
            if u.get("status") == "muted" and u.get("mutedUntil") and now > u["mutedUntil"]:
                u["status"] = "active"
                u.pop("mutedUntil", None)
                if u.get("rating", 0) <= mute_th or u.get("rating", 0) < 0:
                    u["rating"] = 0
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
                "chatId": chat_id,
            }
            self.users[str(user_id)] = user
        else:
            if username:
                user["username"] = username
            if full_name:
                user["fullName"] = full_name
            if avatar_url:
                user["avatarUrl"] = avatar_url
            if chat_id is not None:
                user["chatId"] = chat_id
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

        # Check currently muted
        if user.get("status") == "muted" and user.get("mutedUntil") and now < user["mutedUntil"]:
            remaining_mins = max(1, int((user["mutedUntil"] - now) / 60000))
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
                    "explanation": f"Сообщение отклонено: пользователь находится во временном муте (осталось {remaining_mins} мин).",
                },
                "botReply": f"🔇 @{user['username']}, вы временно заблокированы в чате. До снятия ограничений: {remaining_mins} мин.",
            }
            self.messages.append(blocked_msg)
            return {"message": blocked_msg, "user": user, "autoAction": "blocked_muted"}

        # Check currently banned
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
                    "explanation": "Пользователь навсегда заблокирован за критические нарушения.",
                },
                "botReply": f"🚫 @{user['username']} заблокирован навсегда за систематические грубые нарушения.",
            }
            self.messages.append(blocked_msg)
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

        if self.settings["autoDeleteProfanity"] and moderation.get("profanityDetected"):
            should_delete = True

        if user["rating"] <= ban_th:
            user["status"] = "banned"
            auto_action = "banned"
            should_delete = True
            bot_reply = f"🚫 Пользователь @{user['username']} навсегда заблокирован в чате. Кумулятивный рейтинг упал до критической отметки ({user['rating']} ≤ {ban_th})."
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

        self.recalc_risk_level(user)

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

        return {"message": new_msg, "user": user, "autoAction": auto_action}

    def get_messages(self) -> List[Dict[str, Any]]:
        return self.messages

    def clear_messages(self):
        self.messages = []

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
            mins = duration_minutes or self.settings["muteDurationMinutes"]
            user["mutedUntil"] = now + mins * 60 * 1000
        elif status == "active":
            user.pop("mutedUntil", None)
            if reset_rating_if_negative and (user.get("rating", 0) <= self.settings["muteThreshold"] or user.get("rating", 0) < 0):
                user["rating"] = 0

        self.recalc_risk_level(user)
        return user

    def unblock_user(self, user_id: str, new_rating: int = 0) -> Optional[Dict[str, Any]]:
        user = self.get_user(user_id)
        if not user:
            return None

        user["status"] = "active"
        user.pop("mutedUntil", None)
        user["rating"] = max(0, new_rating)
        self.recalc_risk_level(user)
        return user

    def reset_user_rating(self, user_id: str, new_rating: int = 0) -> Optional[Dict[str, Any]]:
        user = self.get_user(user_id)
        if not user:
            return None
        user["rating"] = new_rating
        user["status"] = "active"
        user.pop("mutedUntil", None)
        self.recalc_risk_level(user)
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
