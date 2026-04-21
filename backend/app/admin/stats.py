"""
Модуль статистики бронирований.

Функции:
  get_stats()        — сводная статистика (всего, пришли, не пришли, среднее)
  bookings_per_day() — количество броней по дням за N дней
  guests_per_day()   — количество гостей по дням за месяц
  came_vs_no_show()  — соотношение пришедших и не пришедших
  popular_times()    — распределение броней по времени
"""

import logging
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import func, cast, Integer
from app.database import SessionLocal
from app.models import Reservation

logger = logging.getLogger(__name__)


def get_stats() -> dict:
    """Возвращает сводную статистику по всем бронированиям."""
    db = SessionLocal()
    try:
        total = db.query(Reservation).count()
        came = db.query(Reservation).filter(Reservation.appeared == True).count()
        no_show = db.query(Reservation).filter(Reservation.appeared == False).count()
        guests_sum = db.query(func.sum(cast(Reservation.guests, Integer))).scalar() or 0
        avg_guests = guests_sum / total if total else 0

        logger.info("Stats: total=%d, came=%d, no_show=%d, avg_guests=%.1f",
                     total, came, no_show, avg_guests)

        return {
            "total": total,
            "total_guests": guests_sum,
            "came": came,
            "no_show": no_show,
            "avg_guests": round(avg_guests, 2),
        }
    finally:
        db.close()


def bookings_per_day(days: int = 30) -> list:
    """Возвращает список (дата, кол-во броней) за последние N дней по дате создания."""
    db = SessionLocal()
    try:
        start_dt = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (
            db.query(func.date(Reservation.created_at), func.count(Reservation.id))
            .filter(Reservation.created_at >= start_dt)
            .group_by(func.date(Reservation.created_at))
            .order_by(func.date(Reservation.created_at))
            .all()
        )
        logger.info("Bookings per day: %d data points", len(rows))
        return rows
    finally:
        db.close()


def guests_per_day_range(days: int = 30) -> dict:
    """Возвращает кол-во гостей по дням за последние N дней по дате создания брони."""
    db = SessionLocal()
    try:
        start_dt = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (
            db.query(func.date(Reservation.created_at), func.sum(cast(Reservation.guests, Integer)))
            .filter(Reservation.created_at >= start_dt)
            .group_by(func.date(Reservation.created_at))
            .order_by(func.date(Reservation.created_at))
            .all()
        )
        def _fmt(d):
            if isinstance(d, str):
                return date.fromisoformat(d).strftime("%d.%m")
            return d.strftime("%d.%m")
        return {
            "dates": [_fmt(r[0]) for r in rows],
            "guests": [r[1] for r in rows],
        }
    finally:
        db.close()


def guests_per_day(year: int, month: int) -> dict:
    """Возвращает кол-во гостей по дням за указанный месяц."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Reservation.date, func.sum(cast(Reservation.guests, Integer)))
            .filter(
                func.extract("year", Reservation.date) == year,
                func.extract("month", Reservation.date) == month,
            )
            .group_by(Reservation.date)
            .order_by(Reservation.date)
            .all()
        )
        logger.info("Guests per day (%d-%02d): %d data points", year, month, len(rows))
        return {
            "dates": [r[0].strftime("%d.%m") for r in rows],
            "guests": [r[1] for r in rows],
        }
    finally:
        db.close()


def came_vs_no_show() -> dict:
    """Возвращает кол-во пришедших и не пришедших гостей."""
    db = SessionLocal()
    try:
        came = db.query(Reservation).filter(Reservation.appeared == True).count()
        no_show = db.query(Reservation).filter(Reservation.appeared == False).count()
        logger.info("Attendance: came=%d, no_show=%d", came, no_show)
        return {"came": came, "no_show": no_show}
    finally:
        db.close()


def popular_times() -> dict:
    """Возвращает распределение бронирований по времени."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Reservation.time, func.count(Reservation.id))
            .group_by(Reservation.time)
            .order_by(Reservation.time)
            .all()
        )
        logger.info("Popular times: %d time slots", len(rows))
        return {
            "time": [r[0] for r in rows],
            "count": [r[1] for r in rows],
        }
    finally:
        db.close()
