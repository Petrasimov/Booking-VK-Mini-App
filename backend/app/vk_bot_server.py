"""
VK Bot Server — Long Poll сервер для обработки входящих сообщений.

Функции:
  - Обработка inline-кнопок подтверждения прихода гостей
  - Ввод суммы чека после подтверждения
  - Админ-панель в ЛС: статистика, экспорт CSV, графики, логи ошибок
  - Long Poll цикл для получения событий от VK
"""

import asyncio
import json
import logging
import os
import random
import re
from typing import Any, Dict, Optional

import httpx

from app.database import SessionLocal
from app.models import Reservation, ErrorLog
from app.admin.stats import get_stats
from app.vk_bot import (
    build_confirmation_message,
    build_reminder_message,
    build_feedback_message,
)
from app.admin.export import export_reservations_csv
from app.admin.charts import (
    bookings_chart,
    chart_guests_per_day,
    chart_came_vs_no_show,
    chart_popular_time,
)

logger = logging.getLogger(__name__)

# --- Конфигурация ---
VK_COMMUNITY_TOKEN = os.getenv("VK_COMMUNITY_TOKEN", "")
VK_ADMIN_ID = os.getenv("VK_ADMIN_ID", "")
VK_WAITERS_CHAT_ID = int(os.getenv("VK_WAITERS_CHAT_ID", "0"))
VK_API_VERSION = "5.199"
VK_API_BASE = "https://api.vk.com/method"

pending_checks: Dict[int, int] = {}  # vk_message_id -> reservation_id

# Коды ошибок VK API, при которых имеет смысл повторить запрос
RETRYABLE_VK_ERRORS = {1, 6, 9, 10}
MAX_VK_RETRIES = 3


# ===============================
# VK API — низкоуровневые вызовы
# ===============================
async def vk_api_call(method: str, params: dict, _retry: int = 0) -> dict:
    """Выполняет вызов VK API. При временных ошибках повторяет с exponential backoff.

    Временные ошибки (RETRYABLE_VK_ERRORS):
      1  — Unknown error
      6  — Too many requests per second
      9  — Flood control
      10 — Internal server error

    При рекурсивном вызове access_token и v НЕ передаются — они добавляются здесь.
    """
    params["access_token"] = VK_COMMUNITY_TOKEN
    params["v"] = VK_API_VERSION

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{VK_API_BASE}/{method}", data=params)
            data = response.json()

        if "error" in data:
            error = data["error"]
            error_code = error.get("error_code", 0)

            if error_code in RETRYABLE_VK_ERRORS and _retry < MAX_VK_RETRIES:
                delay = 2 ** _retry  # 1, 2, 4 секунды
                logger.warning(
                    "VK API %s error %d, retry %d in %ds",
                    method, error_code, _retry + 1, delay,
                )
                await asyncio.sleep(delay)
                # Передаём params без access_token и v — они добавятся в начале рекурсии
                clean_params = {
                    k: v for k, v in params.items()
                    if k not in ("access_token", "v")
                }
                return await vk_api_call(method, clean_params, _retry + 1)

            logger.error("VK API error in %s: %s", method, error)
            return {}

        return data.get("response", {})

    except Exception as e:
        logger.error("VK API call %s failed: %s", method, e)
        return {}


async def send_message(user_id: int, message: str, keyboard: dict = None):
    """Отправляет текстовое сообщение пользователю."""
    params = {"user_id": user_id, "message": message, "random_id": 0}
    if keyboard:
        params["keyboard"] = json.dumps(keyboard, ensure_ascii=False)
    await vk_api_call("messages.send", params)


async def send_chat_message(message: str, keyboard: dict = None) -> int:
    """Отправляет сообщение в чат официантов. Возвращает VK message_id."""
    params = {
        "peer_id": VK_WAITERS_CHAT_ID,
        "message": message,
        "random_id": random.randint(1, 2**31),
    }
    if keyboard:
        params["keyboard"] = json.dumps(keyboard, ensure_ascii=False)
    result = await vk_api_call("messages.send", params)
    # messages.send returns message_id (int) in response
    return result if isinstance(result, int) else 0


async def send_photo(user_id: int, photo_path: str, caption: str = ""):
    """
    Отправляет фото пользователю через VK.
    Шаги: получить upload URL → загрузить файл → сохранить → отправить.
    """
    # 1. Получаем URL для загрузки (peer_id обязателен для community-токена)
    upload_server = await vk_api_call("photos.getMessagesUploadServer", {"peer_id": user_id})
    if not upload_server or "upload_url" not in upload_server:
        logger.error("Failed to get photo upload server")
        await send_message(user_id, "Ошибка загрузки фото")
        return

    try:
        # 2. Загружаем файл на сервер VK
        async with httpx.AsyncClient() as client:
            with open(photo_path, "rb") as f:
                resp = await client.post(upload_server["upload_url"], files={"photo": f})
                upload_data = resp.json()

        # 3. Сохраняем фото в альбом сообщений
        saved = await vk_api_call("photos.saveMessagesPhoto", {
            "photo": upload_data["photo"],
            "server": upload_data["server"],
            "hash": upload_data["hash"],
        })
        if not saved:
            await send_message(user_id, "Ошибка сохранения фото")
            return

        # 4. Отправляем сообщение с вложением
        attachment = f"photo{saved[0]['owner_id']}_{saved[0]['id']}"
        await vk_api_call("messages.send", {
            "user_id": user_id,
            "message": caption,
            "attachment": attachment,
            "random_id": 0,
        })
        logger.info("Photo sent to user %d: %s", user_id, photo_path)

    except Exception as e:
        logger.error("Failed to send photo to user %d: %s", user_id, e)
        await send_message(user_id, "Ошибка отправки фото")


async def send_document(user_id: int, file_path: str, title: str = ""):
    """
    Отправляет документ (CSV и т.д.) пользователю через VK.
    Шаги: получить upload URL → загрузить файл → сохранить → отправить.
    """
    upload_server = await vk_api_call("docs.getMessagesUploadServer", {"type": "doc", "peer_id": user_id})
    if not upload_server or "upload_url" not in upload_server:
        logger.error("Failed to get doc upload server")
        await send_message(user_id, "Ошибка загрузки документа")
        return

    try:
        async with httpx.AsyncClient() as client:
            with open(file_path, "rb") as f:
                filename = title or os.path.basename(file_path)
                resp = await client.post(upload_server["upload_url"], files={"file": (filename, f)})
                upload_data = resp.json()

        save_params = {"file": upload_data["file"]}
        if title:
            save_params["title"] = title

        saved = await vk_api_call("docs.save", save_params)
        if not saved or "doc" not in saved:
            await send_message(user_id, "Ошибка сохранения документа")
            return

        doc = saved["doc"]
        attachment = f"doc{doc['owner_id']}_{doc['id']}"
        await vk_api_call("messages.send", {
            "user_id": user_id,
            "message": title or "Документ",
            "attachment": attachment,
            "random_id": 0,
        })
        logger.info("Document sent to user %d: %s", user_id, file_path)

    except Exception as e:
        logger.error("Failed to send document to user %d: %s", user_id, e)
        await send_message(user_id, "Ошибка отправки документа")


# ===============================
# Клавиатуры (VK keyboards)
# ===============================
def admin_keyboard() -> dict:
    """Главная клавиатура админ-панели."""
    return {
        "one_time": False,
        "buttons": [
            [
                {"action": {"type": "text", "label": "Статистика"}, "color": "primary"},
                {"action": {"type": "text", "label": "Экспорт CSV"}, "color": "primary"},
            ],
            [
                {"action": {"type": "text", "label": "Графики"}, "color": "secondary"},
                {"action": {"type": "text", "label": "Логи ошибок"}, "color": "negative"},
            ],
            [
                {"action": {"type": "text", "label": "Демо сообщений"}, "color": "secondary"},
            ],
        ],
    }


def charts_keyboard() -> dict:
    """Клавиатура выбора графиков."""
    return {
        "one_time": False,
        "buttons": [
            [
                {"action": {"type": "text", "label": "Брони по дням"}, "color": "primary"},
                {"action": {"type": "text", "label": "Гости по дням"}, "color": "primary"},
            ],
            [
                {"action": {"type": "text", "label": "Посещаемость"}, "color": "positive"},
                {"action": {"type": "text", "label": "Популярное время"}, "color": "positive"},
            ],
            [
                {"action": {"type": "text", "label": "Назад"}, "color": "secondary"},
            ],
        ],
    }


# ===============================
# Обработчики команд админа
# ===============================
async def handle_start(user_id: int):
    """Показывает главное меню админ-панели."""
    if str(user_id) != VK_ADMIN_ID:
        await send_message(user_id, "У вас нет доступа к этому боту")
        return
    logger.info("Admin %d opened admin panel", user_id)
    await send_message(user_id, "Админ-панель\n\nВыберите действие:", admin_keyboard())


async def handle_stats(user_id: int):
    """Показывает сводную статистику бронирований."""
    logger.info("Admin %d requested stats", user_id)
    stats = get_stats()
    message = (
        f"📊 Статистика бронирований\n\n"
        f"📋 Всего броней: {stats['total']}\n"
        f"👥 Всего гостей: {stats['total_guests']}\n"
        f"👤 Среднее гостей: {stats['avg_guests']:.1f}\n"
        f"✅ Пришли: {stats['came']}\n"
        f"❌ Не пришли: {stats['no_show']}"
    )
    await send_message(user_id, message, admin_keyboard())


async def handle_export(user_id: int):
    """Экспортирует все бронирования в CSV и отправляет файл."""
    logger.info("Admin %d requested CSV export", user_id)
    await send_message(user_id, "Экспортирую данные...")
    try:
        file_path = export_reservations_csv()
        await send_document(user_id, file_path, "reservations.csv")
    except Exception as e:
        logger.error("Export failed: %s", e)
        await send_message(user_id, "Ошибка экспорта данных")


async def handle_error_logs(user_id: int):
    """Показывает последние 10 ошибок из БД."""
    logger.info("Admin %d requested error logs", user_id)
    db = SessionLocal()
    try:
        errors = (
            db.query(ErrorLog)
            .order_by(ErrorLog.created_at.desc())
            .limit(10)
            .all()
        )
        if not errors:
            await send_message(user_id, "Ошибок не найдено", admin_keyboard())
            return

        lines = ["⚠️ Последние ошибки:\n"]
        for err in errors:
            ts = err.created_at.strftime("%d.%m %H:%M")
            lines.append(f"[{ts}] [{err.source}] {err.message[:100]}")

        await send_message(user_id, "\n".join(lines), admin_keyboard())
    finally:
        db.close()


async def handle_charts_menu(user_id: int):
    """Показывает меню выбора графиков."""
    await send_message(user_id, "Выберите график:", charts_keyboard())


async def handle_chart(user_id: int, chart_func, caption: str):
    """Универсальный обработчик генерации и отправки графика."""
    await send_message(user_id, "Генерирую график...")
    try:
        chart_path = chart_func()
        await send_photo(user_id, chart_path, caption)
    except Exception as e:
        logger.error("Chart generation failed: %s", e)
        await send_message(user_id, "Ошибка создания графика")


# ===============================
# Обработка подтверждения прихода
# ===============================
async def handle_guest_came(reservation_id: int, confirmed_by: int):
    """Отмечает прибытие гостя. Блокирует повторное подтверждение."""
    db = SessionLocal()
    try:
        reservation = db.get(Reservation, reservation_id)
        if not reservation:
            await send_chat_message(f"Бронь #{reservation_id} не найдена")
            return
        if reservation.appeared is not None:
            who = f"@id{reservation.visit_confirmed_by}" if reservation.visit_confirmed_by else "неизвестно"
            status = "Пришёл ✅" if reservation.appeared else "Не пришёл ❌"
            await send_chat_message(
                f"⚠️ На бронь #{reservation_id} уже внесены данные: {status}\n"
                f"Изменения внёс {who}"
            )
            return
        reservation.appeared = True
        reservation.visit_confirmed_by = confirmed_by
        db.commit()
    finally:
        db.close()

    logger.info("Reservation #%d: guest came, requesting check amount", reservation_id)
    msg_id = await send_chat_message(
        f"✅ Гость пришёл\n\n"
        f"Введите сумму чека для брони #{reservation_id}, "
        f"ответив на это сообщение:"
    )
    if msg_id:
        pending_checks[msg_id] = reservation_id



async def handle_guest_no_show(reservation_id: int, confirmed_by: int):
    """Отмечает неявку гостя. Блокирует повторное подтверждение."""
    db = SessionLocal()
    try:
        reservation = db.get(Reservation, reservation_id)
        if not reservation:
            await send_chat_message(f"Бронь #{reservation_id} не найдена")
            return
        if reservation.appeared is not None:
            who = f"@id{reservation.visit_confirmed_by}" if reservation.visit_confirmed_by else "неизвестно"
            status = "Пришёл ✅" if reservation.appeared else "Не пришёл ❌"
            await send_chat_message(
                f"⚠️ На бронь #{reservation_id} уже внесены данные: {status}\n"
                f"Изменения внёс {who}"
            )
            return
        reservation.appeared = False
        reservation.check = 0
        reservation.visit_confirmed_by = confirmed_by
        db.commit()
        await send_chat_message(f"❌ Гость не пришёл (бронь #{reservation_id})")
    finally:
        db.close()



async def handle_check_amount(reservation_id: int, check_str: str):
    """Сохраняет сумму чека в БД и подтверждает в чате официантов."""
    try:
        check_amount = int(check_str.strip())
        if check_amount < 0:
            raise ValueError("negative")
    except ValueError:
        await send_chat_message(
            f"⚠️ Некорректная сумма для брони #{reservation_id}. "
            f"Введите целое число (рублей)."
        )
        return

    db = SessionLocal()
    try:
        reservation = db.get(Reservation, reservation_id)
        if reservation:
            reservation.appeared = True
            reservation.check = check_amount
            db.commit()
            logger.info("Check %d RUB saved for reservation #%d", check_amount, reservation_id)
            await send_chat_message(
                f"✅ Чек сохранён\n\n"
                f"Сумма: {check_amount} руб.\n"
                f"Бронь #{reservation_id}"
            )
        else:
            await send_chat_message(f"Бронь #{reservation_id} не найдена")
    finally:
        db.close()


# ===============================
# Демо: предпросмотр сообщений гостю
# ===============================
async def handle_demo(user_id: int):
    """Отправляет администратору примеры всех сообщений, которые получает гость."""
    import random as _rnd
    from datetime import date, time, timedelta

    # Генерируем согласованные тестовые данные
    names = ["Анастасия", "Дмитрий", "Елена", "Михаил", "Ольга", "Сергей"]
    demo_name = _rnd.choice(names)
    demo_date = date.today() + timedelta(days=_rnd.randint(1, 7))
    demo_date_str = demo_date.strftime("%d.%m.%Y")
    hours = _rnd.choice([12, 13, 14, 18, 19, 20])
    minutes = _rnd.choice([0, 30])
    demo_time_str = f"{hours:02d}:{minutes:02d}"
    demo_guests = _rnd.randint(2, 6)

    await send_message(user_id, (
        "📬 Демонстрация сообщений\n\n"
        f"Тестовые данные:\n"
        f"👤 Имя: {demo_name}\n"
        f"📅 Дата: {demo_date_str}\n"
        f"⏰ Время: {demo_time_str}\n"
        f"👥 Гостей: {demo_guests}\n\n"
        "Ниже — 3 сообщения, которые получит гость:"
    ))

    # 1. Подтверждение бронирования
    await send_message(user_id, (
        "─────────────────────\n"
        "📨 Сообщение 1 из 3\n"
        "Отправляется сразу после бронирования\n"
        "─────────────────────\n\n"
        + build_confirmation_message(demo_name, demo_date_str, demo_time_str, demo_guests)
    ))

    # 2. Напоминание за час до визита
    await send_message(user_id, (
        "─────────────────────\n"
        "📨 Сообщение 2 из 3\n"
        f"Отправляется за 1 час до визита (в {hours - 1:02d}:{minutes:02d})\n"
        "─────────────────────\n\n"
        + build_reminder_message(demo_name, demo_time_str)
    ))

    # 3. Запрос обратной связи на следующий день
    await send_message(user_id, (
        "─────────────────────\n"
        "📨 Сообщение 3 из 3\n"
        f"Отправляется на следующий день в 12:00\n"
        "─────────────────────\n\n"
        + build_feedback_message(demo_name, demo_date_str, demo_time_str)
    ))

    logger.info("Demo messages sent to admin %d", user_id)


# ===============================
# Роутер входящих сообщений
# ===============================
# Маппинг текст -> обработчик (для команд админа)
ADMIN_COMMANDS = {
    "Статистика": handle_stats,
    "Экспорт CSV": handle_export,
    "Графики": handle_charts_menu,
    "Логи ошибок": handle_error_logs,
    "Демо сообщений": handle_demo,
    "Назад": handle_start,
}

CHART_COMMANDS = {
    "Брони по дням": (bookings_chart, "Бронирования по дням (30 дней)"),
    "Гости по дням": (chart_guests_per_day, "Гости по дням"),
    "Посещаемость": (chart_came_vs_no_show, "Пришли / Не пришли"),
    "Популярное время": (chart_popular_time, "Популярное время бронирований"),
}


async def handle_message(event: dict):
    """
    Главный роутер входящих сообщений.

    Приоритет обработки:
      1. Payload inline-кнопок (came / no_show) — из чата официантов
      2. Reply на сообщение «Введите сумму чека» — ввод суммы чека
      3. Команды администратора в ЛС
    """
    message = event.get("object", {}).get("message", {})
    user_id = message.get("from_id")
    peer_id = message.get("peer_id")
    text = message.get("text", "").strip()
    payload_str = message.get("payload")
    reply_message = message.get("reply_message") or {}
    replied_to_id = reply_message.get("id")

    if not user_id:
        return

    logger.debug(
        "Message from %d: text=%r, payload=%r, reply_to=%r",
        user_id, text, payload_str, replied_to_id,
    )

    # 1. Inline-кнопки «Пришёл» / «Не пришёл»
    if payload_str:
        try:
            payload = json.loads(payload_str)
            action = payload.get("action")
            rid = payload.get("reservation_id")

            if action == "came":
                await handle_guest_came(rid, user_id)
                return
            elif action == "no_show":
                await handle_guest_no_show(rid, user_id)
                return
        except Exception as e:
            logger.error("Payload parse error: %s", e)

    # 2. Reply на сообщение «Введите сумму чека» в чате официантов
    if reply_message:
        reservation_id = None

        # Точное совпадение по message_id (основной путь)
        if replied_to_id and replied_to_id in pending_checks:
            reservation_id = pending_checks.pop(replied_to_id)
            logger.info("Check reply matched by msg_id=%d → reservation #%d", replied_to_id, reservation_id)

        # Fallback: извлекаем номер брони из текста цитируемого сообщения
        if reservation_id is None:
            replied_text = reply_message.get("text", "")
            m = re.search(r"брони #(\d+)", replied_text)
            if m:
                reservation_id = int(m.group(1))
                # Убираем из pending_checks если там есть (мутируем на месте, не переприсваиваем)
                for _k in [k for k, v in pending_checks.items() if v == reservation_id]:
                    pending_checks.pop(_k, None)
                logger.info("Check reply matched by text regex → reservation #%d", reservation_id)

        if reservation_id is not None:
            await handle_check_amount(reservation_id, text)
            return

    # 4. Только для администратора — команды в ЛС
    if str(user_id) != VK_ADMIN_ID or peer_id != user_id:
        return

    if text.lower() in ("начать", "/start", "start"):
        await handle_start(user_id)
        return

    if text in ADMIN_COMMANDS:
        await ADMIN_COMMANDS[text](user_id)
        return

    if text in CHART_COMMANDS:
        func, caption = CHART_COMMANDS[text]
        await handle_chart(user_id, func, caption)
        return

    await handle_start(user_id)


# ===============================
# Long Poll — основной цикл
# ===============================
async def get_long_poll_server() -> Optional[dict]:
    """Получает параметры Long Poll сервера от VK API."""
    group_id = os.getenv("VK_GROUP_ID", "")
    if not group_id:
        logger.error("VK_GROUP_ID not set — Long Poll cannot start")
        return None
    result = await vk_api_call("groups.getLongPollServer", {"group_id": group_id})
    return result if result else None


async def run_long_poll():
    """
    Основной цикл Long Poll бота.
    Подключается к VK, слушает события, обрабатывает сообщения.
    При разрыве соединения — переподключается автоматически.
    """
    if not VK_COMMUNITY_TOKEN:
        logger.error("VK_COMMUNITY_TOKEN not set — bot cannot start")
        return

    logger.info("VK Bot starting (Long Poll)...")

    server = await get_long_poll_server()
    if not server:
        logger.error("Failed to get Long Poll server — bot stopped")
        return

    ts = server["ts"]
    key = server["key"]
    server_url = server["server"]
    logger.info("VK Bot connected to Long Poll")

    while True:
        try:
            params = {"act": "a_check", "key": key, "ts": ts, "wait": 25}

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(server_url, params=params)
                data = response.json()

            # Переподключение при ошибке Long Poll
            if "failed" in data:
                logger.warning("Long Poll reconnecting (failed=%s)", data.get("failed"))
                server = await get_long_poll_server()
                if server:
                    ts, key, server_url = server["ts"], server["key"], server["server"]
                continue

            ts = data["ts"]

            # Обработка входящих событий
            for event in data.get("updates", []):
                if event["type"] == "message_new":
                    try:
                        await handle_message(event)
                    except Exception as e:
                        logger.error("Error handling message: %s", e)

        except Exception as e:
            logger.error("Long Poll error: %s", e)
            await asyncio.sleep(5)


def start_bot():
    """Точка входа для запуска бота как отдельного процесса."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    asyncio.run(run_long_poll())


if __name__ == "__main__":
    start_bot()
