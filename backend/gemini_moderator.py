import os
import re
import json
import logging
from typing import Dict, Any, List, Optional
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("gemini_moderator")

# Common Russian profanity roots and patterns for ultra-fast local checking and fallback
RUSSIAN_PROFANITY_PATTERNS = [
    re.compile(r"х[уеёuy][йяеёиюжп]", re.IGNORECASE),
    re.compile(r"п[иеie]зд[аеыуо]", re.IGNORECASE),
    re.compile(r"еб[аеёиу]|ёб[аеёты]", re.IGNORECASE),
    re.compile(r"бл[яе]д[ьия]", re.IGNORECASE),
    re.compile(r"с[уu]к[аеио]", re.IGNORECASE),
    re.compile(r"п[ие]д[оае]р[аеыу]?", re.IGNORECASE),
    re.compile(r"г[ао]вн[ое]", re.IGNORECASE),
    re.compile(r"м[уu]д[аеио]к", re.IGNORECASE),
    re.compile(r"шл[юе]х[аеу]", re.IGNORECASE),
    re.compile(r"залуп", re.IGNORECASE),
    re.compile(r"\bчмо\b", re.IGNORECASE),
    re.compile(r"\bтварь\b", re.IGNORECASE),
    re.compile(r"\bурод\b", re.IGNORECASE),
    re.compile(r"\bмразь\b", re.IGNORECASE),
    re.compile(r"х\*й|п\*зд|б\*яд|с\*ка|е\*ать", re.IGNORECASE),
]

POSITIVE_WORDS = [
    "спасибо", "благодарю", "отлично", "молодец", "помог", "круто",
    "супер", "здравствуйте", "добрый день", "удачи", "респект",
    "красавчик", "пожалуйста", "отличная идея", "классно"
]
AGGRESSIVE_WORDS = [
    "заткнись", "пошел на", "идиот", "дебил", "тупой", "убейся",
    "ненавижу", "сдохни", "гори в аду", "задолбал", "даун"
]
NEGATIVE_WORDS = [
    "плохо", "ужасно", "ерунда", "фигня", "отстой", "бесит", "надоело", "бред"
]


def fallback_rule_analysis(text: str) -> Dict[str, Any]:
    lower = text.lower()
    found_profanity = []

    for pattern in RUSSIAN_PROFANITY_PATTERNS:
        match = pattern.search(text)
        if match:
            found_profanity.append(match.group(0))

    profanity_detected = len(found_profanity) > 0

    pos_count = sum(1 for w in POSITIVE_WORDS if w in lower)
    agg_count = sum(1 for w in AGGRESSIVE_WORDS if w in lower)
    neg_count = sum(1 for w in NEGATIVE_WORDS if w in lower)

    # Check CAPS LOCK rage
    upper_count = len(re.sub(r"[^А-ЯЁA-Z]", "", text))
    letters_count = len(re.sub(r"[^А-Яа-яЁёA-Za-z]", "", text))
    is_caps_rage = letters_count > 6 and (upper_count / letters_count) > 0.7

    categories = []
    if profanity_detected or agg_count > 0:
        toxicity_score = min(1.0, 0.6 + len(found_profanity) * 0.2 + agg_count * 0.2)
        score = -4 - min(1, len(found_profanity) - 1) if profanity_detected else -3
        sentiment = "aggressive"
        if profanity_detected:
            categories.append("Ненормативная лексика")
        if agg_count > 0:
            categories.append("Оскорбления / Агрессия")
    elif is_caps_rage or neg_count > 0:
        toxicity_score = 0.4
        score = -2 if is_caps_rage else -1
        sentiment = "negative"
        if is_caps_rage:
            categories.append("Капс / Крик")
        if neg_count > 0:
            categories.append("Негативная тональность")
    elif pos_count > 0:
        toxicity_score = 0.0
        score = min(5, 2 + pos_count)
        sentiment = "constructive" if pos_count > 1 else "positive"
        categories.append("Взаимопомощь / Конструктив" if pos_count > 1 else "Доброжелательность")
    else:
        toxicity_score = 0.0
        score = 0
        sentiment = "neutral"
        categories.append("Информационное сообщение")

    action = "allow"
    if score <= -4:
        action = "delete"
    elif score < 0:
        action = "warn"

    explanation = (
        f"Обнаружена ненормативная лексика ({', '.join(found_profanity)}). Резкое снижение рейтинга."
        if profanity_detected
        else "Выявлена прямая агрессия или оскорбление участников."
        if agg_count > 0
        else "Позитивное и вежливое общение в чате."
        if score > 0
        else "Нейтральное сообщение без нарушений правил сообщества."
    )

    return {
        "score": score,
        "sentiment": sentiment,
        "profanityDetected": profanity_detected,
        "profanityWords": found_profanity,
        "toxicityScore": toxicity_score,
        "categories": categories,
        "explanation": explanation,
        "action": action,
        "muteDurationMinutes": 60 if score <= -4 else None,
    }


def analyze_message_with_gemini(text: str, user_history_summary: Optional[str] = None) -> Dict[str, Any]:
    fallback = fallback_rule_analysis(text)

    # Fast-path: If blatant profanity or extreme aggression is detected locally,
    # penalize immediately without spending Gemini API quota
    if fallback.get("profanityDetected") and fallback.get("score", 0) <= -4:
        return fallback

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return fallback

    safe_text = text.replace('"', '\\"')
    user_context = f"Контекст пользователя: {user_history_summary}\n" if user_history_summary else ""

    prompt = f"""Ты строгий и объективный робот-модератор сообществ Telegram.
Твоя задача — проанализировать сообщение пользователя, выявить ненормативную лексику (мат, завуалированный мат, эвфемизмы, транслит), оценить эмоциональную тональность, степень токсичности и выставить оценку от -5 до +5.

Правила шкалы оценки (score строго от -5 до +5):
- +5: Исключительная польза, решение проблем других участников, глубокий конструктив, высокая вежливость.
- +3 до +4: Дружелюбное, полезное, позитивное общение, поддержка, благодарность.
- +1 до +2: Приятная беседа, легкий позитив, приветствие.
- 0: Полностью нейтральный текст, вопрос по теме, ссылка без спама, технический ответ.
- -1 до -2: Легкая пассивная агрессия, сарказм, токсичный тон, переход на личности, капс-крик.
- -3 до -4: Явные оскорбления, унижение, нецензурная брань/мат (даже легкий или скрытый точками), спам.
- -5: Жесткий мат, прямые угрозы расправой, разжигание ненависти, деструктивный троллинг.

Сообщение для анализа: "{safe_text}"
{user_context}
Ответь в строгом формате JSON:
{{
  "score": -5..5,
  "sentiment": "positive" | "neutral" | "negative" | "aggressive" | "constructive",
  "profanityDetected": true | false,
  "profanityWords": ["слово1"],
  "toxicityScore": 0.0..1.0,
  "categories": ["Ненормативная лексика"],
  "explanation": "краткое емкое объяснение на русском языке (до 15 слов)",
  "action": "allow" | "warn" | "delete" | "mute_temp" | "ban"
}}
Ответь ТОЛЬКО валидным JSON-объектом без лишнего текста."""

    try:
        raw_text = ""
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            raw_text = response.text.strip() if response and response.text else ""
        except ImportError:
            import urllib.request
            req_data = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"}
            }).encode("utf-8")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={api_key}"
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=4) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                candidates = res_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        raw_text = parts[0].get("text", "").strip()

        if not raw_text:
            return fallback

        # Clean markdown wrappers if any
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]

        parsed = json.loads(raw_text.strip())

        # Clamp score strictly -5..+5
        score = max(-5, min(5, int(parsed.get("score", fallback["score"]))))

        valid_sentiments = ["positive", "neutral", "negative", "aggressive", "constructive"]
        sentiment = parsed.get("sentiment")
        if sentiment not in valid_sentiments:
            sentiment = fallback["sentiment"]

        profanity_detected = bool(parsed.get("profanityDetected", fallback["profanityDetected"]))
        profanity_words = parsed.get("profanityWords")
        if not isinstance(profanity_words, list) or len(profanity_words) == 0:
            profanity_words = fallback["profanityWords"]

        valid_actions = ["allow", "warn", "delete", "mute_temp", "ban"]
        action = parsed.get("action")
        if action not in valid_actions:
            action = fallback["action"]

        # Safety override: if profanity is detected, enforce at least deletion
        if profanity_detected and action == "allow":
            action = "delete"

        toxicity_score = parsed.get("toxicityScore")
        if not isinstance(toxicity_score, (int, float)):
            toxicity_score = fallback["toxicityScore"]

        categories = parsed.get("categories")
        if not isinstance(categories, list):
            categories = fallback["categories"]

        explanation = parsed.get("explanation") or fallback["explanation"]

        return {
            "score": score,
            "sentiment": sentiment,
            "profanityDetected": profanity_detected,
            "profanityWords": profanity_words,
            "toxicityScore": float(toxicity_score),
            "categories": categories,
            "explanation": explanation,
            "action": action,
            "muteDurationMinutes": 60 if score <= -4 else None,
        }
    except Exception as e:
        logger.warning(f"Gemini API call failed, using rule-based fallback: {e}")
        return fallback
