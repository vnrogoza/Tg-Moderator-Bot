#!/usr/bin/env python3
"""
Standalone Telegram Bot Moderator in pure Python
Запуск автономного Telegram-бота в терминале:
    python bot.py
"""

import os
import sys
import time
import logging
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from backend.store import store
from backend.gemini_moderator import analyze_message_with_ai

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("StandaloneBot")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("❌ ОШИБКА: TELEGRAM_BOT_TOKEN не задан в .env файле!")
    logger.info("Укажите токен бота из @BotFather в .env и перезапустите.")
    sys.exit(1)

import telebot
from telebot import types

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

logger.info("🤖 Инициализация Telegram AI Модератора (Python + Gemini 2.5)...")
try:
    me = bot.get_me()
    logger.info(f"✅ Успешное подключение к боту @{me.username} (ID: {me.id})")
except Exception as e:
    logger.error(f"❌ Не удалось подключиться к Telegram: {e}")
    sys.exit(1)


@bot.message_handler(commands=["start", "help"])
def send_welcome(message: types.Message):
    text = f"""<b>🤖 Робот-модератор сообществ Telegram (Python)</b>

Я автоматически слежу за порядком в чате с помощью нейросети Google Gemini:
• Оцениваю сообщения по шкале от -5 до +5
• Нахожу мат, завуалированные оскорбления и скрытый негатив
• Накапливаю персональную карму участников
• Выдаю временный мут при рейтинге ниже {store.get_settings()['muteThreshold']}
• Блокирую нарушителей навсегда при падении кармы ниже {store.get_settings()['banThreshold']}

<b>Доступные команды:</b>
/rating — узнать свой текущий рейтинг и статус
/stats — статистика модерации чата
/unban @username — разблокировать участника (для администраторов)
/rules — правила общения в группе"""
    bot.reply_to(message, text)


@bot.message_handler(commands=["rating", "karma"])
def check_rating(message: types.Message):
    u = store.get_user(str(message.from_user.id))
    rating = u.get("rating", 0) if u else 0
    status = u.get("status", "active") if u else "active"
    status_label = "🔇 Мут" if status == "muted" else "🚫 Бан" if status == "banned" else "✅ Активен"
    sign = "+" if rating > 0 else ""
    text = f"""👤 <b>Рейтинг @{message.from_user.username or message.from_user.first_name}</b>: {sign}{rating}
📊 Сообщений: {u.get('totalMessages', 0) if u else 0}
Статус: {status_label}"""
    bot.reply_to(message, text)


@bot.message_handler(commands=["stats"])
def show_stats(message: types.Message):
    st = store.get_stats()
    text = f"""📊 <b>Статистика модерации</b>
• Проверено сообщений: {st['totalMessages']}
• Пресечено нарушений: {st['totalViolations']}
• Мата удалено: {st['profanityCount']}
• Пользователей в муте: {st['mutedUsersCount']}
• Средний рейтинг участников: {st['averageRating']}"""
    bot.reply_to(message, text)


@bot.message_handler(commands=["unban", "unmute"])
def admin_unban(message: types.Message):
    target_id = None
    target_name = None

    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = str(message.reply_to_message.from_user.id)
        target_name = message.reply_to_message.from_user.username or message.reply_to_message.from_user.first_name
    else:
        parts = message.text.split()
        if len(parts) > 1:
            q = parts[1].strip()
            user_found = store.get_user_by_username(q) or store.get_user(q)
            if user_found:
                target_id = user_found["id"]
                target_name = user_found["username"]
            elif q.isdigit():
                target_id = q
                target_name = f"user_{q}"

    if not target_id:
        bot.reply_to(
            message,
            "ℹ️ Ответьте на сообщение нарушителя командой <code>/unban</code> или введите <code>/unban @username</code>",
        )
        return

    # Unban in Telegram: restore messaging abilities and clear kick status if any
    try:
        if target_id.isdigit():
            bot.unban_chat_member(message.chat.id, int(target_id), only_if_banned=True)
            bot.restrict_chat_member(
                message.chat.id,
                int(target_id),
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
    except Exception as e:
        logger.warning(f"Telegram API unban warning: {e}")

    store.update_user_status(target_id, "active", None, True)
    bot.reply_to(
        message,
        f"✅ Пользователю @{str(target_name).lstrip('@')} возвращена возможность отправлять сообщения! Ограничения сняты, рейтинг сброшен до 0.",
    )


@bot.message_handler(func=lambda msg: True, content_types=["text"])
def moderate_incoming_message(message: types.Message):
    text = (message.text or "").strip()
    if not text:
        return

    user_id = str(message.from_user.id)
    username = message.from_user.username or message.from_user.first_name or f"user_{user_id}"
    full_name = " ".join(filter(None, [message.from_user.first_name, message.from_user.last_name])) or username

    # Check context in store
    u = store.get_user(user_id)
    summary = f"Рейтинг: {u.get('rating')}, нарушений: {u.get('toxicMessages')}" if u else None

    logger.info(f"🔍 Проверка сообщения от @{username}: '{text}'")
    mod = analyze_message_with_ai(text, summary)

    outcome = store.process_incoming_message(
        user_id=user_id,
        username=username,
        full_name=full_name,
        text=text,
        moderation=mod,
        chat_id=message.chat.id,
    )

    score = mod.get("score", 0)
    sign = "+" if score > 0 else ""
    logger.info(f"📊 Результат: оценка [{sign}{score}/5], карма: {outcome['user']['rating']}")

    settings = store.get_settings()

    # Auto-delete profanity
    if settings.get("autoDeleteProfanity") and mod.get("profanityDetected"):
        try:
            bot.delete_message(message.chat.id, message.message_id)
            logger.info(f"🗑 Удалено матерное сообщение от @{username}")
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")

    # Auto-actions: настоящий бан и исключение из чата
    if outcome.get("autoAction") == "banned":
        try:
            bot.ban_chat_member(message.chat.id, int(user_id))
        except Exception as e:
            logger.warning(f"Ban member error: {e}")
        bot.send_message(
            message.chat.id,
            f"🚫 <b>Пользователь @{username} исключён и заблокирован в чате!</b>\nКумулятивный рейтинг упал до {outcome['user']['rating']}.",
        )
    elif outcome.get("autoAction") == "muted":
        until_unix = int(time.time()) + settings.get("muteDurationMinutes", 120) * 60
        try:
            bot.restrict_chat_member(
                message.chat.id,
                int(user_id),
                until_date=until_unix,
                can_send_messages=False,
            )
        except Exception as e:
            logger.warning(f"Restrict member error: {e}")
        bot.send_message(
            message.chat.id,
            f"🔇 <b>@{username} временно заблокирован на {settings.get('muteDurationMinutes')} мин!</b>\n"
            f"Причина: Высокий отрицательный рейтинг ({outcome['user']['rating']}). Оценка сообщения: [{sign}{score}/5]",
        )
    elif outcome.get("message", {}).get("botReply"):
        bot.reply_to(message, outcome["message"]["botReply"])
    elif score <= -2:
        emoji = "🌟" if score >= 3 else "👍" if score > 0 else "💬" if score == 0 else "⚠️" if score >= -2 else "🚨"
        badge = f"{emoji} <b>[{sign}{score}/5]</b> {mod.get('explanation')} | Карма: {outcome['user']['rating']}"
        bot.reply_to(message, badge)


if __name__ == "__main__":
    logger.info("🚀 Бот запущен и слушает сообщения в Telegram (Long Polling)...")
    logger.info("Нажмите Ctrl+C для остановки.")
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем.")
