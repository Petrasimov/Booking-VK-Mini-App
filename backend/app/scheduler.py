"""
Планировщик отложенных задач.

Каждые POLL_INTERVAL секунд проверяет таблицу scheduled_task в БД.
Выполняет задачи, у которых наступило время (scheduled_at <= now).

Типы задач:
  visit_confirmation — запрос подтверждения прихода в чат официантов
  reminder           — напоминание гостю за час до визита (VK ЛС)
  feedback           — запрос обратной связи на следующий день (VK ЛС)
"""

import asyncio
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import delete
from app.database import SessionLocal
from app.models import Reservation, ScheduledTask, RateLimitEntry
from app.vk_bot import (
    build_feedback_message,
    build_reminder_message,
    send_vk_chat_message,
    send_vk_message,
    send_waiters_confirmation_request,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL = 60  # Интервал проверки в секундах (1 минута)

# Отслеживаем дату последней отправки сводки, чтобы не слать дважды в одни сутки
_last_summary_date: date | None = None


async def execute_task(task: ScheduledTask, reservation: Reservation):
    """
    Выполняет конкретную задачу в зависимости от task_type.
    Вызывает соответствующую VK API функцию.
    """
    if task.task_type == "visit_confirmation":
        # Отправляем в чат официантов запрос «Гость пришёл?»
        await send_waiters_confirmation_request(
            name=reservation.name,
            guests=reservation.guests,
            time=reservation.time.strftime("%H:%M"),
            reservation_id=reservation.id,
        )

    elif task.task_type == "reminder":
        # Напоминание гостю за час до визита
        if reservation.vk_user_id and reservation.vk_notifications:
            message = build_reminder_message(
                name=reservation.name,
                time=reservation.time.strftime("%H:%M"),
            )
            await send_vk_message(reservation.vk_user_id, message)

    elif task.task_type == "feedback":
        # Запрос обратной связи на следующий день
        if reservation.vk_user_id and reservation.vk_notifications:
            message = build_feedback_message(
                name=reservation.name,
                date=str(reservation.date),
                time=reservation.time.strftime("%H:%M"),
            )
            await send_vk_message(reservation.vk_user_id, message)

    else:
        logger.warning("Unknown task type: %s (task #%d)", task.task_type, task.id)


async def process_pending_tasks():
    """Находит и выполняет все задачи, у которых наступило время."""
    db = SessionLocal()
    try:
        now = datetime.now()
        tasks = (
            db.query(ScheduledTask)
            .filter(ScheduledTask.completed == False, ScheduledTask.scheduled_at <= now)
            .all()
        )

        if not tasks:
            return

        logger.info("Found %d pending tasks", len(tasks))

        for task in tasks:
            reservation = db.get(Reservation, task.reservation_id)

            # Если бронирование удалено — помечаем задачу выполненной
            if not reservation:
                logger.warning("Reservation #%d not found for task #%d — skipping",
                               task.reservation_id, task.id)
                task.completed = True
                db.commit()
                continue

            try:
                await execute_task(task, reservation)
                task.completed = True
                db.commit()
                logger.info("Task #%d (%s) for reservation #%d completed",
                            task.id, task.task_type, task.reservation_id)
            except Exception as e:
                logger.error("Task #%d (%s) for reservation #%d failed: %s",
                             task.id, task.task_type, task.reservation_id, e)
    finally:
        db.close()


async def cleanup_rate_limit():
    """Removes rate_limit entries older than 2 minutes (stale records from all IPs)."""
    db = SessionLocal()
    try:
        cutoff = datetime.now() - timedelta(seconds=120)
        db.execute(delete(RateLimitEntry).where(RateLimitEntry.window_start < cutoff))
        db.commit()
    finally:
        db.close()


async def send_daily_summary():
    """Отправляет сводку броней на сегодня в чат официантов."""
    db = SessionLocal()
    try:
        today = date.today()
        reservations = (
            db.query(Reservation)
            .filter(Reservation.date == today)
            .order_by(Reservation.time)
            .all()
        )

        if not reservations:
            message = f"☕ Доброе утро! На 📅 {today.strftime('%d.%m')} бронирований нет."
        else:
            lines = [f"☕ Доброе утро! 📊 Брони на 📅 {today.strftime('%d.%m.%Y')} ({len(reservations)} шт.):\n"]
            for r in reservations:
                lines.append(
                    f"⏰ {r.time.strftime('%H:%M')} — 👤 {r.name}, 👥 {r.guests} чел. 📱 ({r.phone})"
                )
            message = "\n".join(lines)

        await send_vk_chat_message(message)
        logger.info("Daily summary sent: %d reservations", len(reservations))
    finally:
        db.close()


async def run_scheduler():
    """Main scheduler loop — polls every POLL_INTERVAL seconds."""
    global _last_summary_date
    logger.info("Scheduler started (polling every %d sec)", POLL_INTERVAL)

    _cleanup_counter = 0

    while True:
        try:
            await process_pending_tasks()

            # Daily summary at 09:00 local time — sent once per day
            now = datetime.now()
            today = now.date()
            if now.hour == 9 and _last_summary_date != today:
                _last_summary_date = today
                try:
                    await send_daily_summary()
                except Exception as e:
                    logger.error("Daily summary failed: %s", e)

            # Cleanup stale rate_limit rows — every 60 cycles (~1 hour)
            _cleanup_counter += 1
            if _cleanup_counter >= 60:
                _cleanup_counter = 0
                try:
                    await cleanup_rate_limit()
                except Exception as e:
                    logger.error("Rate limit cleanup failed: %s", e)

        except Exception as e:
            logger.error("Scheduler error: %s", e)

        await asyncio.sleep(POLL_INTERVAL)
