"""
Ночные джобы управления жизненным циклом данных.

Три джоба (запускаются из scheduler.py):

  run_aggregate_job()
    Каждую ночь в 03:00.
    Берёт брони старше 6 месяцев из таблицы reservation →
    агрегирует в venue_stats_daily (upsert) →
    копирует в reservation_archive →
    удаляет из reservation.
    Результат: Hot-таблица остаётся маленькой, статистика сохраняется вечно.

  run_cold_archive_job()
    1-го числа каждого месяца в 02:00.
    Берёт записи из reservation_archive старше 2 лет →
    анонимизирует (152-ФЗ: телефон → хэш, имя → инициалы) →
    TODO: загружает в Cloudflare R2 →
    удаляет из reservation_archive.

  run_cleanup_job()
    Каждую ночь в 04:00.
    Удаляет старые выполненные ScheduledTask, RateLimitEntry, ErrorLog.
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import select, delete, func, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import (
    Reservation,
    ReservationArchive,
    VenueStatsDaily,
    ScheduledTask,
    RateLimitEntry,
    ErrorLog,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Настройки
# ─────────────────────────────────────────────

HOT_RETENTION_MONTHS = 6    # брони моложе этого — остаются в reservation
WARM_RETENTION_YEARS = 2    # брони старше этого — уходят в cold archive
TASK_RETENTION_DAYS  = 30   # выполненные задачи хранятся 30 дней
RATE_LIMIT_TTL_HOURS = 24   # записи rate limiter живут 24 часа
ERROR_LOG_DAYS       = 90   # логи ошибок хранятся 90 дней


# ─────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────

def _anonymize_phone(phone: str | None) -> str | None:
    """
    Анонимизирует телефон для cold archive (152-ФЗ).
    Возвращает SHA-256 хэш первых 10 цифр, усечённый до 16 символов.
    """
    if not phone:
        return None
    digits = "".join(c for c in phone if c.isdigit())[:10]
    return hashlib.sha256(digits.encode()).hexdigest()[:16]


def _anonymize_name(name: str | None) -> str | None:
    """
    Анонимизирует имя для cold archive.
    Оставляет только первую букву каждого слова: "Иван Петров" → "И.П."
    """
    if not name:
        return None
    parts = name.strip().split()
    return ".".join(p[0].upper() for p in parts if p) + "."


def _get_hot_cutoff() -> date:
    """Граничная дата: брони старше этой даты подлежат архивированию."""
    today = date.today()
    # Вычитаем 6 месяцев (примерно)
    year  = today.year - (1 if today.month <= 6 else 0)
    month = (today.month - 6) % 12 or 12
    return today.replace(year=year, month=month)


def _get_warm_cutoff() -> date:
    """Граничная дата: записи старше этой уходят в cold archive."""
    return date.today() - timedelta(days=WARM_RETENTION_YEARS * 365)


# ─────────────────────────────────────────────
# Джоб 1: Агрегация и перенос в архив (Hot → Warm)
# ─────────────────────────────────────────────

def run_aggregate_job(db: Session) -> dict:
    """
    Агрегирует старые брони в venue_stats_daily и переносит в reservation_archive.

    Возвращает словарь с результатами:
      archived_count  — количество перенесённых броней
      venues_affected — количество затронутых заведений
      stats_upserted  — количество обновлённых строк статистики
    """
    cutoff = _get_hot_cutoff()
    logger.info("aggregate_job: archiving reservations older than %s", cutoff)

    # 1. Получаем все брони для архивирования
    reservations = db.execute(
        select(Reservation).where(Reservation.date < cutoff)
    ).scalars().all()

    if not reservations:
        logger.info("aggregate_job: no reservations to archive")
        return {"archived_count": 0, "venues_affected": 0, "stats_upserted": 0}

    logger.info("aggregate_job: found %d reservations to archive", len(reservations))

    # 2. Группируем по (venue_id, date) для агрегации
    from collections import defaultdict
    groups: dict[tuple, list[Reservation]] = defaultdict(list)
    for r in reservations:
        key = (r.venue_id, r.date)
        groups[key].append(r)

    # 3. Агрегируем и upsert в venue_stats_daily
    stats_upserted = 0
    for (venue_id, stat_date), rows in groups.items():
        bookings = len(rows)
        guests   = sum(r.guests or 0 for r in rows)
        came     = sum(1 for r in rows if r.appeared is True)
        no_show  = sum(1 for r in rows if r.appeared is False)

        # Самое популярное время
        time_counter = Counter(
            r.time.strftime("%H:%M") for r in rows if r.time
        )
        peak_hour = time_counter.most_common(1)[0][0] if time_counter else None

        # Сумма чеков
        revenue = sum(r.check for r in rows if r.check) or None

        # Upsert: если запись за этот день уже есть — обновляем, иначе создаём
        existing = db.execute(
            select(VenueStatsDaily).where(
                VenueStatsDaily.venue_id == venue_id,
                VenueStatsDaily.date     == stat_date,
            )
        ).scalar_one_or_none()

        if existing:
            existing.bookings  += bookings
            existing.guests    += guests
            existing.came      += came
            existing.no_show   += no_show
            existing.updated_at = datetime.utcnow()
            if peak_hour:
                existing.peak_hour = peak_hour
            if revenue:
                existing.revenue = (existing.revenue or 0) + revenue
        else:
            db.add(VenueStatsDaily(
                venue_id  = venue_id,
                date      = stat_date,
                bookings  = bookings,
                guests    = guests,
                came      = came,
                no_show   = no_show,
                peak_hour = peak_hour,
                revenue   = revenue,
            ))
        stats_upserted += 1

    db.flush()

    # 4. Копируем брони в reservation_archive
    archived_ids   = []
    venues_affected = set()

    for r in reservations:
        db.add(ReservationArchive(
            venue_id    = r.venue_id,
            name        = r.name,
            guests      = r.guests,
            phone       = r.phone,
            date        = r.date,
            time        = r.time,
            comment     = r.comment,
            extra_data  = r.extra_data or {},
            appeared    = r.appeared,
            check       = r.check,
            original_id = r.id,
            created_at  = r.created_at,
        ))
        archived_ids.append(r.id)
        if r.venue_id:
            venues_affected.add(r.venue_id)

    db.flush()

    # 5. Удаляем из reservation
    db.execute(
        delete(Reservation).where(Reservation.id.in_(archived_ids))
    )
    db.commit()

    result = {
        "archived_count":  len(archived_ids),
        "venues_affected": len(venues_affected),
        "stats_upserted":  stats_upserted,
    }
    logger.info(
        "aggregate_job completed: archived=%d venues=%d stats=%d",
        result["archived_count"], result["venues_affected"], result["stats_upserted"],
    )
    return result


# ─────────────────────────────────────────────
# Джоб 2: Cold archive (Warm → Cold)
# ─────────────────────────────────────────────

def run_cold_archive_job(db: Session) -> dict:
    """
    Переносит записи старше 2 лет из reservation_archive в cold storage.

    Текущая реализация: анонимизирует и удаляет (логирует что было бы загружено).
    TODO: загрузка в Cloudflare R2 (добавить после получения ключей в .env).

    Возвращает:
      cold_count — количество обработанных записей
    """
    cutoff = _get_warm_cutoff()
    logger.info("cold_archive_job: processing records older than %s", cutoff)

    old_records = db.execute(
        select(ReservationArchive).where(
            ReservationArchive.date < cutoff
        )
    ).scalars().all()

    if not old_records:
        logger.info("cold_archive_job: no records to cold-archive")
        return {"cold_count": 0}

    logger.info("cold_archive_job: found %d records for cold archive", len(old_records))

    cold_ids = []
    for record in old_records:
        # Анонимизируем перед удалением
        record.phone = _anonymize_phone(record.phone)
        record.name  = _anonymize_name(record.name)
        cold_ids.append(record.id)

    db.flush()

    # TODO: загрузить в Cloudflare R2 перед удалением
    # Формат файла: venues/{venue_id}/archive_{year}_{month}.json
    logger.info(
        "cold_archive_job: [TODO] would upload %d records to R2, deleting now",
        len(cold_ids),
    )

    db.execute(
        delete(ReservationArchive).where(ReservationArchive.id.in_(cold_ids))
    )
    db.commit()

    logger.info("cold_archive_job completed: cold_count=%d", len(cold_ids))
    return {"cold_count": len(cold_ids)}


# ─────────────────────────────────────────────
# Джоб 3: Очистка служебных таблиц
# ─────────────────────────────────────────────

def run_cleanup_job(db: Session) -> dict:
    """
    Удаляет устаревшие служебные записи.

    Удаляет:
      - ScheduledTask (completed=True) старше TASK_RETENTION_DAYS дней
      - RateLimitEntry старше RATE_LIMIT_TTL_HOURS часов
      - ErrorLog старше ERROR_LOG_DAYS дней

    Возвращает количество удалённых записей по каждой таблице.
    """
    now = datetime.utcnow()

    # Удаляем выполненные задачи
    task_cutoff = now - timedelta(days=TASK_RETENTION_DAYS)
    task_result = db.execute(
        delete(ScheduledTask).where(
            ScheduledTask.completed == True,
            ScheduledTask.created_at < task_cutoff,
        )
    )
    tasks_deleted = task_result.rowcount

    # Удаляем устаревшие записи rate limiter
    rate_cutoff = now - timedelta(hours=RATE_LIMIT_TTL_HOURS)
    rate_result = db.execute(
        delete(RateLimitEntry).where(
            RateLimitEntry.window_start < rate_cutoff,
        )
    )
    rate_deleted = rate_result.rowcount

    # Удаляем старые логи ошибок
    error_cutoff = now - timedelta(days=ERROR_LOG_DAYS)
    error_result = db.execute(
        delete(ErrorLog).where(
            ErrorLog.created_at < error_cutoff,
        )
    )
    errors_deleted = error_result.rowcount

    db.commit()

    result = {
        "tasks_deleted":  tasks_deleted,
        "rate_deleted":   rate_deleted,
        "errors_deleted": errors_deleted,
    }
    logger.info(
        "cleanup_job completed: tasks=%d rate=%d errors=%d",
        tasks_deleted, rate_deleted, errors_deleted,
    )
    return result