import os
import time
import asyncio
import logging
from typing import Dict, Any, List, Set, Optional
import requests
from dotenv import load_dotenv

from server.store import store
from server.gemini_moderator import analyze_message_with_gemini

load_dotenv()

logger = logging.getLogger("telegram_bot")


class TelegramService:
    def __init__(self):
        self.token: str = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        self.bot_info: Optional[Dict[str, Any]] = None
        self.is_polling: bool = False
        self.polling_task: Optional[asyncio.Task] = None
        self.last_update_id: int = 0
        self.consecutive_conflicts: int = 0
        self.conflict_detected: bool = False
        self.last_error: Optional[str] = None
        self.known_chat_ids: Set[Any] = set()

    def set_token(self, new_token: str):
        self.token = new_token.strip()
        if self.token:
            self.stop_polling()
            res = self.init_bot()
            if res.get("success"):
                logger.info(f"Bot initialized: @{res.get('botName')}")
        else:
            self.stop_polling()
            self.bot_info = None
            store.update_settings({"realTelegramConnected": False, "telegramBotUsername": None})

    def get_token(self) -> str:
        return self.token

    def get_status(self) -> Dict[str, Any]:
        return {
            "connected": bool(self.bot_info),
            "botName": self.bot_info.get("username") if self.bot_info else None,
            "isPolling": self.is_polling,
            "lastUpdateId": self.last_update_id,
            "conflict": self.conflict_detected,
            "consecutiveConflicts": self.consecutive_conflicts,
            "lastError": self.last_error,
        }

    def get_known_chat_ids(self) -> List[Any]:
        return list(self.known_chat_ids)

    def init_bot(self) -> Dict[str, Any]:
        if not self.token:
            return {"success": False, "error": "Токен Telegram бота не задан."}

        try:
            url = f"https://api.telegram.org/bot{self.token}/getMe"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if data.get("ok"):
                self.bot_info = data.get("result")
                store.update_settings({
                    "realTelegramConnected": True,
                    "telegramBotUsername": self.bot_info.get("username"),
                })
                return {"success": True, "botName": self.bot_info.get("username")}
            else:
                return {"success": False, "error": data.get("description", "Неверный токен бота")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_webhook(self) -> Dict[str, Any]:
        if not self.token:
            return {"success": False, "description": "Токен не настроен"}
        try:
            url = f"https://api.telegram.org/bot{self.token}/deleteWebhook?drop_pending_updates=false"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            return {"success": data.get("ok", False), "description": data.get("description")}
        except Exception as e:
            return {"success": False, "description": str(e)}

    def get_webhook_info(self) -> Dict[str, Any]:
        if not self.token:
            return {"ok": False, "error": "Токен не настроен"}
        try:
            url = f"https://api.telegram.org/bot{self.token}/getWebhookInfo"
            resp = requests.get(url, timeout=10)
            return resp.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_webhook(self, webhook_url: str) -> Dict[str, Any]:
        if not self.token:
            return {"success": False, "description": "Токен не настроен"}
        try:
            self.stop_polling()
            url = f"https://api.telegram.org/bot{self.token}/setWebhook"
            resp = requests.post(url, json={"url": webhook_url}, timeout=10)
            data = resp.json()
            return {"success": data.get("ok", False), "description": data.get("description")}
        except Exception as e:
            return {"success": False, "description": str(e)}

    async def start_polling(self):
        if self.is_polling:
            logger.info("[Telegram Polling] Polling is already active.")
            return
        if not self.token:
            logger.info("[Telegram Polling] Cannot start: Token is not configured.")
            return

        self.consecutive_conflicts = 0
        self.conflict_detected = False
        self.last_error = None

        logger.info("[Telegram Polling] Deleting any webhook to enable getUpdates...")
        self.delete_webhook()

        self.is_polling = True
        logger.info("[Telegram Polling] Starting polling loop...")
        self.polling_task = asyncio.create_task(self._poll_loop())

    def stop_polling(self):
        self.is_polling = False
        if self.polling_task:
            self.polling_task.cancel()
            self.polling_task = None
        logger.info("[Telegram Polling] Polling stopped.")

    async def _poll_loop(self):
        import aiohttp

        while self.is_polling and self.token:
            next_delay = 1.0
            try:
                url = f"https://api.telegram.org/bot{self.token}/getUpdates"
                params = {
                    "offset": self.last_update_id + 1,
                    "limit": 20,
                    "timeout": 4,
                }
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        data = await resp.json()

                if data.get("ok") and isinstance(data.get("result"), list):
                    if self.consecutive_conflicts > 0 or self.conflict_detected:
                        logger.info("[Telegram Polling] getUpdates resumed successfully. Conflict resolved.")
                    self.consecutive_conflicts = 0
                    self.conflict_detected = False
                    self.last_error = None

                    for update in data["result"]:
                        u_id = update.get("update_id", 0)
                        if u_id > self.last_update_id:
                            self.last_update_id = u_id
                        await self.handle_webhook_update(update)
                    next_delay = 1.0
                elif not data.get("ok"):
                    desc = str(data.get("description", ""))
                    is_conflict = (
                        data.get("error_code") == 409
                        or "conflict" in desc.lower()
                        or "terminated by other getupdates" in desc.lower()
                    )
                    if is_conflict:
                        self.consecutive_conflicts += 1
                        self.conflict_detected = True
                        self.last_error = desc or "Conflict: terminated by other getUpdates"

                        if self.consecutive_conflicts >= 4:
                            logger.warning(f"[Telegram Polling] Paused polling after {self.consecutive_conflicts} consecutive 409 errors.")
                            self.is_polling = False
                            break
                        else:
                            next_delay = min(10.0 * self.consecutive_conflicts, 30.0)
                            logger.warning(f"[Telegram Polling] Conflict detected ({self.consecutive_conflicts}/4): Backing off for {next_delay}s...")
                    else:
                        logger.warning(f"[Telegram Polling] getUpdates error: {desc}")
                        self.last_error = desc
                        next_delay = 4.0
            except asyncio.CancelledError:
                break
            except Exception as err:
                logger.warning(f"[Telegram Polling] Loop exception: {err}")
                next_delay = 4.0

            if self.is_polling:
                await asyncio.sleep(next_delay)

    async def send_message(self, chat_id: Any, text: str, reply_to_message_id: Optional[int] = None):
        if not self.token:
            return
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            }
            if reply_to_message_id:
                payload["reply_to_message_id"] = reply_to_message_id
            requests.post(url, json=payload, timeout=8)
        except Exception as err:
            logger.error(f"Failed to send Telegram message: {err}")

    async def delete_message(self, chat_id: Any, message_id: int):
        if not self.token:
            return
        try:
            url = f"https://api.telegram.org/bot{self.token}/deleteMessage"
            requests.post(url, json={"chat_id": chat_id, "message_id": message_id}, timeout=8)
        except Exception as err:
            logger.error(f"Failed to delete Telegram message: {err}")

    async def restrict_member(self, chat_id: Any, user_id: Any, until_date_unix: int):
        if not self.token:
            return
        is_numeric = str(user_id).isdigit()
        if not is_numeric:
            return

        try:
            url = f"https://api.telegram.org/bot{self.token}/restrictChatMember"
            payload = {
                "chat_id": chat_id,
                "user_id": int(user_id),
                "until_date": until_date_unix,
                "permissions": {
                    "can_send_messages": False,
                    "can_send_audios": False,
                    "can_send_documents": False,
                    "can_send_photos": False,
                    "can_send_videos": False,
                    "can_send_video_notes": False,
                    "can_send_voice_notes": False,
                    "can_send_polls": False,
                    "can_send_other_messages": False,
                    "can_add_web_page_previews": False,
                    "can_change_info": False,
                    "can_invite_users": False,
                    "can_pin_messages": False,
                },
            }
            requests.post(url, json=payload, timeout=8)
        except Exception as err:
            logger.error(f"Failed to restrict Telegram chat member: {err}")

    async def ban_member(self, user_id: Any, specific_chat_id: Optional[Any] = None) -> Dict[str, Any]:
        if not self.token:
            return {"success": False, "chats": []}
        if not str(user_id).isdigit():
            return {"success": True, "chats": []}

        chat_ids = [specific_chat_id] if specific_chat_id else list(self.known_chat_ids)
        affected = []

        for c_id in chat_ids:
            try:
                url = f"https://api.telegram.org/bot{self.token}/banChatMember"
                resp = requests.post(url, json={"chat_id": c_id, "user_id": int(user_id)}, timeout=8)
                data = resp.json()
                if data.get("ok"):
                    affected.append(c_id)
            except Exception as e:
                logger.error(f"banChatMember error on chat {c_id}: {e}")

        return {"success": len(affected) > 0, "chats": affected}

    async def unban_member(self, user_id: Any, specific_chat_id: Optional[Any] = None) -> Dict[str, Any]:
        if not self.token:
            return {"success": False, "chats": []}
        if not str(user_id).isdigit():
            return {"success": True, "chats": []}

        chat_ids = [specific_chat_id] if specific_chat_id else list(self.known_chat_ids)
        affected = []

        for c_id in chat_ids:
            try:
                url = f"https://api.telegram.org/bot{self.token}/unbanChatMember"
                resp = requests.post(
                    url,
                    json={"chat_id": c_id, "user_id": int(user_id), "only_if_banned": False},
                    timeout=8,
                )
                data = resp.json()
                if data.get("ok"):
                    affected.append(c_id)
            except Exception as e:
                logger.error(f"unbanChatMember error on chat {c_id}: {e}")

        return {"success": len(affected) > 0, "chats": affected}

    async def unmute_member(self, user_id: Any, specific_chat_id: Optional[Any] = None) -> Dict[str, Any]:
        if not self.token:
            return {"success": False, "chats": []}
        if not str(user_id).isdigit():
            return {"success": True, "chats": []}

        chat_ids = [specific_chat_id] if specific_chat_id else list(self.known_chat_ids)
        affected = []

        for c_id in chat_ids:
            try:
                url = f"https://api.telegram.org/bot{self.token}/restrictChatMember"
                payload = {
                    "chat_id": c_id,
                    "user_id": int(user_id),
                    "permissions": {
                        "can_send_messages": True,
                        "can_send_audios": True,
                        "can_send_documents": True,
                        "can_send_photos": True,
                        "can_send_videos": True,
                        "can_send_video_notes": True,
                        "can_send_voice_notes": True,
                        "can_send_polls": True,
                        "can_send_other_messages": True,
                        "can_add_web_page_previews": True,
                        "can_change_info": False,
                        "can_invite_users": True,
                        "can_pin_messages": False,
                    },
                }
                resp = requests.post(url, json=payload, timeout=8)
                data = resp.json()
                if data.get("ok"):
                    affected.append(c_id)
            except Exception as e:
                logger.error(f"unmuteMember error on chat {c_id}: {e}")

        return {"success": len(affected) > 0, "chats": affected}

    async def unban_and_unmute_member(self, user_id: Any, specific_chat_id: Optional[Any] = None) -> Dict[str, Any]:
        unban_res = await self.unban_member(user_id, specific_chat_id)
        unmute_res = await self.unmute_member(user_id, specific_chat_id)
        all_chats = list(set(unban_res["chats"] + unmute_res["chats"]))
        return {
            "success": unban_res["success"] or unmute_res["success"],
            "unbannedChats": all_chats,
        }

    async def handle_webhook_update(self, update: Dict[str, Any]):
        msg = update.get("message") or update.get("edited_message") or update.get("channel_post")
        if not msg:
            return

        text = (msg.get("text") or msg.get("caption") or "").strip()
        if not text:
            return

        chat_id = msg.get("chat", {}).get("id")
        if chat_id:
            self.known_chat_ids.add(chat_id)

        message_id = msg.get("message_id")
        from_user = msg.get("from")
        if not from_user:
            return

        user_id = str(from_user.get("id"))
        username = from_user.get("username") or from_user.get("first_name") or f"user_{user_id}"
        full_name = " ".join(filter(None, [from_user.get("first_name"), from_user.get("last_name")])) or username
        avatar_url = f"https://api.dicebear.com/7.x/bottts/svg?seed={user_id}"

        # Bot commands handling
        if text.startswith("/"):
            command = text.split()[0].lower().split("@")[0]

            if command in ("/start", "/help"):
                help_text = f"""<b>🤖 Робот-модератор чата (Python + Gemini AI)</b>
Я анализирую каждое сообщение в чате с помощью ИИ:
• Оценка качества сообщений от -5 до +5
• Фильтрация мата и оскорблений
• Определение эмоциональной тональности
• Подсчет персональной кармы участников
• Автоматический временный мут при накоплении отрицательного рейтинга (порог: {store.get_settings()['muteThreshold']})

Команды:
/rating - проверить свой рейтинг
/stats - статистика модерации чата
/unban @username - разблокировать пользователя (для админов)
/unmute @username - снять мут с пользователя
/rules - правила чата"""
                await self.send_message(chat_id, help_text, message_id)
                return

            if command in ("/rating", "/karma"):
                u = store.get_user(user_id)
                rating = u.get("rating", 0) if u else 0
                status = u.get("status", "active") if u else "active"
                sign = "+" if rating > 0 else ""
                status_icon = "🔇 Заблокирован" if status == "muted" else "🚫 Бан" if status == "banned" else "✅ Активен"
                rating_text = f"""👤 <b>Рейтинг @{username}</b>: {sign}{rating}
📊 Всего сообщений: {u.get('totalMessages', 0) if u else 0}
Статус: {status_icon}"""
                await self.send_message(chat_id, rating_text, message_id)
                return

            if command == "/stats":
                st = store.get_stats()
                stats_msg = f"""📊 <b>Статистика модерации чата</b>
• Проанализировано сообщений: {st['totalMessages']}
• Нарушений пресечено: {st['totalViolations']}
• Ненормативной лексики: {st['profanityCount']}
• Пользователей в муте: {st['mutedUsersCount']}
• Средний рейтинг участников: {st['averageRating']}"""
                await self.send_message(chat_id, stats_msg, message_id)
                return

            if command in ("/unban", "/unmute"):
                target_user_id = None
                target_username = None

                reply_from = msg.get("reply_to_message", {}).get("from")
                if reply_from:
                    target_user_id = str(reply_from.get("id"))
                    target_username = reply_from.get("username") or reply_from.get("first_name") or target_user_id
                else:
                    parts = text.split()
                    if len(parts) > 1:
                        query = parts[1].strip()
                        u_found = store.get_user_by_username(query) or store.get_user(query)
                        if u_found:
                            target_user_id = u_found["id"]
                            target_username = u_found["username"]
                        elif query.isdigit():
                            target_user_id = query
                            target_username = f"user_{query}"

                if not target_user_id:
                    await self.send_message(
                        chat_id,
                        "ℹ️ Чтобы разблокировать пользователя, ответьте на его сообщение командой <code>/unban</code> или укажите логин: <code>/unban @username</code>",
                        message_id,
                    )
                    return

                store.update_user_status(target_user_id, "active", None, True)
                await self.unban_and_unmute_member(target_user_id, chat_id)
                display_name = f"@{target_username.lstrip('@')}" if target_username else target_user_id
                await self.send_message(
                    chat_id,
                    f"✅ <b>Пользователь {display_name} успешно разблокирован!</b>\nВсе ограничения и мут сняты, карма сброшена до 0.",
                    message_id,
                )
                return

        # Moderate message with Gemini AI
        u_exist = store.get_user(user_id)
        user_summary = (
            f"Текущий рейтинг: {u_exist.get('rating')}, нарушений: {u_exist.get('toxicMessages')}"
            if u_exist
            else None
        )

        mod_result = analyze_message_with_gemini(text, user_summary)
        result = store.process_incoming_message(
            user_id=user_id,
            username=username,
            full_name=full_name,
            text=text,
            moderation=mod_result,
            avatar_url=avatar_url,
            chat_id=chat_id,
        )

        score = mod_result.get("score", 0)
        score_sign = "+" if score > 0 else ""
        score_emoji = (
            "🌟" if score >= 3
            else "👍" if score > 0
            else "💬" if score == 0
            else "⚠️" if score >= -2
            else "🚨"
        )
        score_badge = f"{score_emoji} <b>[{score_sign}{score}/5]</b> {mod_result.get('explanation')} | Карма: {result['user'].get('rating')}"

        settings = store.get_settings()
        is_neutral = (not mod_result.get("profanityDetected")) and (
            mod_result.get("sentiment") == "neutral" or score == 0
        )

        # Auto-delete profanity
        if settings.get("autoDeleteProfanity") and mod_result.get("profanityDetected"):
            await self.delete_message(chat_id, message_id)

        # Auto-banned
        if result.get("autoAction") == "banned":
            await self.ban_member(user_id, chat_id)
            await self.send_message(
                chat_id,
                f"🚫 <b>Пользователь @{username} навсегда заблокирован в чате.</b>\nПричина: Кумулятивный рейтинг упал до критической отметки ({result['user'].get('rating')}).",
            )
        elif result.get("autoAction") == "muted":
            until_unix = int(time.time()) + settings.get("muteDurationMinutes", 120) * 60
            await self.restrict_member(chat_id, user_id, until_unix)
            await self.send_message(
                chat_id,
                f"🔇 <b>Пользователь @{username} временно заблокирован на {settings.get('muteDurationMinutes')} мин!</b>\nПричина: Высокий отрицательный рейтинг ({result['user'].get('rating')}).\nОценка: [{score_sign}{score}/5] {mod_result.get('explanation')}",
            )
        elif result.get("message", {}).get("botReply"):
            await self.send_message(chat_id, result["message"]["botReply"], message_id)
        elif is_neutral:
            if settings.get("commentNeutralMessages"):
                await self.send_message(chat_id, score_badge, message_id)
        elif settings.get("showRatingBadgeUnderAll") or score <= -2:
            await self.send_message(chat_id, score_badge, message_id)


telegram_service = TelegramService()
