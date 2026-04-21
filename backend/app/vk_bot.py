"""
VK Bot — модуль отправки сообщений через VK API.

Функции:
  send_vk_message()                — личное сообщение пользователю
  send_vk_chat_message()           — сообщение в групповой чат (официанты)
  send_admin_notification()        — уведомление администратору
  send_waiters_new_reservation()   — новая бронь в чат официантов
  send_waiters_confirmation_request() — запрос подтверждения прихода
  build_*()                        — шаблоны сообщений
"""

import os
import json
import random
import logging
import httpx

logger = logging.getLogger(__name__)

# --- Конфигурация из .env ---
VK_COMMUNITY_TOKEN = os.getenv("VK_COMMUNITY_TOKEN", "")
VK_ADMIN_ID = os.getenv("VK_ADMIN_ID", "")
VK_WAITERS_CHAT_ID = os.getenv("VK_WAITERS_CHAT_ID", "")
CAFE_ADDRESS = os.getenv("CAFE_ADDRESS", "")
VK_API_VERSION = "5.199"
VK_API_URL = "https://api.vk.com/method/messages.send"

MAX_RETRIES = 2  # Количество повторных попыток отправки


# ===============================
# Отправка личного сообщения
# ===============================
async def send_vk_message(user_id: int, message: str) -> bool:
    """
    Отправляет личное сообщение пользователю через VK API.
    Повторяет до MAX_RETRIES раз при временных ошибках.
    Не повторяет при ошибках прав доступа (901, 7, 15).
    """
    if not VK_COMMUNITY_TOKEN:
        logger.warning("VK_COMMUNITY_TOKEN not set — message skipped")
        return False

    logger.info("Sending VK message to user %d", user_id)

    params = {
        "user_id": user_id,
        "message": message,
        "random_id": random.randint(1, 2**31),
        "access_token": VK_COMMUNITY_TOKEN,
        "v": VK_API_VERSION,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(VK_API_URL, data=params)
                data = response.json()

            if "error" in data:
                code = data["error"].get("error_code")
                msg = data["error"].get("error_msg")
                logger.error("VK API error (user=%d, attempt=%d): code=%s, msg=%s",
                             user_id, attempt, code, msg)
                # Ошибки прав — не повторяем
                if code in (901, 7, 15):
                    return False
                continue

            logger.info("VK message sent to user %d (attempt %d)", user_id, attempt)
            return True

        except Exception as e:
            logger.error("VK request failed (user=%d, attempt=%d): %s", user_id, attempt, e)

    logger.error("All %d attempts failed for user %d", MAX_RETRIES, user_id)
    return False


# ===============================
# Отправка в групповой чат
# ===============================
async def send_vk_chat_message(message: str, keyboard: dict = None) -> bool:
    """
    Отправляет сообщение в групповой чат официантов.
    Использует peer_id из VK_WAITERS_CHAT_ID.
    """
    if not VK_WAITERS_CHAT_ID or not VK_COMMUNITY_TOKEN:
        logger.warning("VK chat config missing — message skipped")
        return False

    try:
        peer_id = int(VK_WAITERS_CHAT_ID)
        params = {
            "peer_id": peer_id,
            "message": message,
            "random_id": random.randint(1, 2**31),
            "access_token": VK_COMMUNITY_TOKEN,
            "v": VK_API_VERSION,
        }

        if keyboard:
            params["keyboard"] = json.dumps(keyboard, ensure_ascii=False)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(VK_API_URL, data=params)
            data = response.json()

        if "error" in data:
            logger.error("VK chat error (peer=%d): %s", peer_id, data["error"])
            return False

        logger.info("Message sent to waiters chat (peer=%d)", peer_id)
        return True

    except Exception as e:
        logger.error("Failed to send to waiters chat: %s", e)
        return False


# ===============================
# Admin-уведомления
# ===============================
async def send_admin_notification(message: str) -> bool:
    """Отправляет уведомление администратору в ЛС."""
    if not VK_ADMIN_ID:
        logger.warning("VK_ADMIN_ID not set — admin notification skipped")
        return False
    try:
        return await send_vk_message(int(VK_ADMIN_ID), message)
    except ValueError:
        logger.error("Invalid VK_ADMIN_ID: %s", VK_ADMIN_ID)
        return False


# ===============================
# Шаблоны сообщений
# ===============================
def build_confirmation_message(name: str, date: str, time: str, guests: int) -> str:
    """Подтверждение бронирования для гостя."""
    return (
        f"☕ Здравствуйте, {name}!\n\n"
        f"✅ Ваше бронирование подтверждено:\n"
        f"📅 Дата: {date}\n"
        f"⏰ Время: {time}\n"
        f"👥 Гостей: {guests}\n"
        f"📍 Адрес: {CAFE_ADDRESS}\n\n"
        f"🍰 Мы вас ждём!"
    )


def build_reminder_message(name: str, time: str) -> str:
    """Напоминание за час до визита."""
    return (
        f"🔔 {name}, напоминаем — через час вас ждёт столик!\n\n"
        f"⏰ Время: {time}\n"
        f"📍 Адрес: {CAFE_ADDRESS}\n\n"
        f"☕ До встречи!"
    )


def build_feedback_message(name: str, date: str, time: str) -> str:
    """Запрос обратной связи на следующий день после визита."""
    return (
        f"🌟 {name}, спасибо, что вчера ({date}) в {time} посетили нас!\n\n"
        f"🍰 Надеемся, вам было уютно в Шоколаднице.\n\n"
        f"💬 Нам очень важно ваше мнение:\n"
        f"- Насколько удобно было пользоваться приложением?\n"
        f"- Как вы оцените качество обслуживания?\n\n"
        f"☕ Будем рады, если оставите отзыв в нашей группе!\n"
        f"https://vk.com/club234068981"
    )


def build_new_reservation_message(
    name: str, guests: int, phone: str, date: str, time: str, reservation_id: int
) -> str:
    """Сообщение о новой брони (для чата/админа)."""
    return (
        f"📋 НОВАЯ БРОНЬ\n\n"
        f"👤 Имя: {name}\n"
        f"👥 Гостей: {guests}\n"
        f"📱 Телефон: {phone}\n"
        f"📅 Дата: {date}\n"
        f"⏰ Время: {time}\n"
        f"🆔 ID брони: {reservation_id}"
    )


def build_upcoming_reservation_message(
    name: str, guests: int, phone: str, time: str, reservation_id: int
) -> str:
    """Напоминание о скором визите гостя (для чата/админа)."""
    return (
        f"🔔 ГОСТЬ ПО ЗАПИСИ\n\n"
        f"👤 Имя: {name}\n"
        f"👥 Гостей: {guests}\n"
        f"📱 Телефон: {phone}\n"
        f"⏰ Время: {time}\n"
        f"🆔 ID брони: {reservation_id}"
    )


# ===============================
# Клавиатура подтверждения прихода
# ===============================
def create_confirmation_keyboard(reservation_id: int) -> dict:
    """Inline-клавиатура: Пришёл / Не пришёл."""
    return {
        "inline": True,
        "buttons": [[
            {
                "action": {
                    "type": "text",
                    "label": "✅ Пришёл",
                    "payload": json.dumps({"action": "came", "reservation_id": reservation_id}),
                },
                "color": "positive",
            },
            {
                "action": {
                    "type": "text",
                    "label": "❌ Не пришёл",
                    "payload": json.dumps({"action": "no_show", "reservation_id": reservation_id}),
                },
                "color": "negative",
            },
        ]],
    }


# ===============================
# Уведомления официантам
# ===============================
async def send_waiters_new_reservation(
    name: str, guests: int, phone: str, date: str, time: str, reservation_id: int,
    comment: str = ""
) -> bool:
    """Отправляет уведомление о новой брони в чат официантов."""
    message = (
        f"📋 НОВАЯ БРОНЬ\n\n"
        f"👤 Имя: {name}\n"
        f"👥 Гостей: {guests}\n"
        f"📱 Телефон: {phone}\n"
        f"📅 Дата: {date}\n"
        f"⏰ Время: {time}\n"
    )
    if comment:
        message += f"💬 Комментарий: {comment}\n"
    message += f"\n🆔 Бронь #{reservation_id}"
    logger.info("Notifying waiters about reservation #%d", reservation_id)
    return await send_vk_chat_message(message)


async def send_waiters_confirmation_request(
    name: str, guests: int, time: str, reservation_id: int
) -> bool:
    """Отправляет запрос подтверждения прихода в чат официантов с кнопками."""
    message = (
        f"☕ ГОСТЬ ДОЛЖЕН ПРИЙТИ\n\n"
        f"👤 {name}\n"
        f"👥 Гостей: {guests}\n"
        f"⏰ Время: {time}\n\n"
        f"Гость пришёл?"
    )
    keyboard = create_confirmation_keyboard(reservation_id)
    logger.info("Sending confirmation request for reservation #%d", reservation_id)
    return await send_vk_chat_message(message, keyboard)
