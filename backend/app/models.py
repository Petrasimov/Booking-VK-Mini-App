"""
ORM-модели базы данных.

Venue              — заведение (кафе, барбершоп, клиника и т.д.).
VenueRole          — роль пользователя VK в заведении (owner, manager, staff).
Reservation        — бронирование (Hot storage — последние 6 мес).
ReservationArchive — архив броней (Warm storage — 6 мес – 2 года).
VenueStatsDaily    — агрегированная статистика по дням (хранится вечно).
ScheduledTask      — отложенная задача (напоминание, фидбек, архивирование).
ErrorLog           — лог ошибок приложения.
RateLimitEntry     — запись rate-limiter (хранится в БД между перезапусками).

Стратегия хранения броней (Hot → Warm → Cold):
  Hot:  таблица reservation       — последние 6 мес, все индексы активны
  Warm: таблица reservation_archive — 6 мес – 2 года, минимум индексов
  Cold: Cloudflare R2 (JSON/CSV)  — старше 2 лет, анонимизировано
  Stats: venue_stats_daily         — агрегаты за каждый день, вечно
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime,
    ForeignKey, Index, Integer, JSON, Numeric, String, Text, Time,
    UniqueConstraint,
)

from app.database import Base


# ─────────────────────────────────────────────
# Venue — заведение
# ─────────────────────────────────────────────

class Venue(Base):
    """
    Заведение, подключённое к платформе.

    Каждое заведение привязано к одной VK-группе (vk_group_id).
    Все настройки хранятся в JSON-поле config:
      - time_slots, working_hours, working_days
      - fields (какие поля показывать в форме)
      - services, masters (для барбершопов, клиник и т.д.)
      - notifications_chat_id, vk_group_token
      - logo_url, accent_color, welcome_text (брендинг)
    """
    __tablename__ = "venues"

    id          = Column(Integer, primary_key=True)
    vk_group_id = Column(BigInteger, unique=True, nullable=False, index=True)

    name        = Column(String(200), nullable=False)
    category    = Column(String(50),  nullable=False)
    # cafe | barbershop | clinic | fitness | beauty | photo_studio | coworking | other

    config      = Column(JSON, nullable=False, default=dict)

    timezone    = Column(String(50),  nullable=False, default="Europe/Moscow")
    address     = Column(String(500), nullable=True)
    phone       = Column(String(30),  nullable=True)

    owner_vk_id = Column(BigInteger, nullable=False)

    # Тариф
    plan            = Column(String(20), nullable=False, default="free")
    # free | standard | pro
    plan_expires_at = Column(DateTime, nullable=True)

    is_active  = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow,
                        onupdate=datetime.utcnow)


# ─────────────────────────────────────────────
# VenueRole — роль пользователя в заведении
# ─────────────────────────────────────────────

class VenueRole(Base):
    """
    Привязка VK-пользователя к заведению с определённой ролью.

    Роли:
      owner   — полный доступ: настройки, статистика, тариф, брони
      manager — брони + статистика (без настроек и тарифа)
      staff   — только подтверждение прихода гостей
    """
    __tablename__ = "venue_roles"
    __table_args__ = (
        UniqueConstraint("venue_id", "vk_user_id", name="uq_venue_role_user"),
        Index("ix_venue_role_user", "vk_user_id"),
    )

    id         = Column(Integer, primary_key=True)
    venue_id   = Column(Integer, ForeignKey("venues.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    vk_user_id = Column(BigInteger, nullable=False)
    role       = Column(String(20), nullable=False)  # owner | manager | staff
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# ─────────────────────────────────────────────
# Reservation — бронирование (Hot storage)
# ─────────────────────────────────────────────

class Reservation(Base):
    """
    Бронирование в заведении.

    Hot storage — хранит только последние 6 месяцев.
    Старые записи автоматически переносятся в ReservationArchive
    ночным джобом aggregate_job (scheduler.py).
    """
    __tablename__ = "reservation"
    __table_args__ = (
        Index("ix_reservation_date",       "date"),
        Index("ix_reservation_phone_date", "phone", "date"),
        Index("ix_reservation_venue",      "venue_id"),
    )

    id       = Column(Integer, primary_key=True)
    venue_id = Column(Integer, ForeignKey("venues.id", ondelete="CASCADE"),
                      nullable=True, index=True)

    name    = Column(String(100), nullable=False)
    guests  = Column(Integer,     nullable=False)
    phone   = Column(String(20),  nullable=False)
    date    = Column(Date,        nullable=False)
    time    = Column(Time,        nullable=False)
    comment = Column(String(500), nullable=True)

    # Дополнительные поля ниши: {"master": "Алексей", "service": "Стрижка"}
    extra_data = Column(JSON, nullable=False, default=dict)

    vk_user_id        = Column(Integer, nullable=True)
    vk_notifications  = Column(Boolean, default=False)

    created_at         = Column(DateTime, default=datetime.utcnow)
    appeared           = Column(Boolean,  nullable=True)
    visit_confirmed_by = Column(Integer,  nullable=True)
    check              = Column(Integer,  nullable=True)


# ─────────────────────────────────────────────
# ReservationArchive — архив броней (Warm storage)
# ─────────────────────────────────────────────

class ReservationArchive(Base):
    """
    Warm storage — брони возрастом от 6 месяцев до 2 лет.

    Заполняется автоматически из aggregate_job.
    Не имеет индексов по phone/date — читается редко.
    Читается только для CSV-экспорта (тариф Pro).

    Через 2 года cold_archive_job:
      - анонимизирует данные (152-ФЗ)
      - выгружает в Cloudflare R2
      - удаляет из этой таблицы
    """
    __tablename__ = "reservation_archive"
    __table_args__ = (
        Index("ix_archive_venue", "venue_id"),
        Index("ix_archive_date",  "date"),
    )

    id         = Column(Integer, primary_key=True)
    venue_id   = Column(Integer, ForeignKey("venues.id", ondelete="CASCADE"),
                        nullable=True, index=True)

    # Копия полей из Reservation
    name       = Column(String(100), nullable=True)
    guests     = Column(Integer,     nullable=True)
    phone      = Column(String(20),  nullable=True)   # удаляется при cold archive
    date       = Column(Date,        nullable=True)
    time       = Column(Time,        nullable=True)
    comment    = Column(String(500), nullable=True)
    extra_data = Column(JSON,        nullable=False, default=dict)

    appeared   = Column(Boolean,  nullable=True)
    check      = Column(Integer,  nullable=True)

    # Метаданные архивирования
    original_id = Column(Integer, nullable=True)   # id из таблицы reservation
    created_at  = Column(DateTime, nullable=True)  # оригинальная дата создания брони
    archived_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# ─────────────────────────────────────────────
# VenueStatsDaily — агрегированная статистика
# ─────────────────────────────────────────────

class VenueStatsDaily(Base):
    """
    Агрегированная статистика по дням — одна строка на день на заведение.

    Хранится ВЕЧНО. Не удаляется при архивировании броней.
    Используется для построения графиков за любой период.

    Заполняется автоматически из aggregate_job перед архивированием броней.
    При запросе статистики глубже 6 мес — читается именно отсюда.

    Вес: ~150 байт × 365 дней × 1 000 заведений = ~55 МБ/год — ничтожно.
    """
    __tablename__ = "venue_stats_daily"
    __table_args__ = (
        # Один день — одна запись на заведение
        UniqueConstraint("venue_id", "date", name="uq_stats_venue_date"),
        Index("ix_stats_venue_date", "venue_id", "date"),
    )

    id       = Column(Integer, primary_key=True)
    venue_id = Column(Integer, ForeignKey("venues.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    date     = Column(Date, nullable=False)

    # Счётчики за день
    bookings   = Column(Integer, nullable=False, default=0)   # всего броней
    guests     = Column(Integer, nullable=False, default=0)   # всего гостей
    came       = Column(Integer, nullable=False, default=0)   # пришли
    no_show    = Column(Integer, nullable=False, default=0)   # не пришли

    # Самый популярный слот времени в этот день ("19:00")
    peak_hour  = Column(String(5), nullable=True)

    # Сумма чеков (если заведение фиксирует)
    revenue    = Column(Numeric(12, 2), nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow,
                        onupdate=datetime.utcnow)


# ─────────────────────────────────────────────
# ScheduledTask — отложенная задача
# ─────────────────────────────────────────────

class ScheduledTask(Base):
    """Отложенная задача, выполняется планировщиком."""
    __tablename__ = "scheduled_task"
    __table_args__ = (
        Index("ix_task_pending", "completed", "scheduled_at"),
        Index("ix_task_venue",   "venue_id"),
    )

    id             = Column(Integer, primary_key=True)
    venue_id       = Column(Integer, ForeignKey("venues.id", ondelete="CASCADE"),
                            nullable=True, index=True)
    reservation_id = Column(Integer, ForeignKey("reservation.id", ondelete="CASCADE"),
                            nullable=False)
    task_type      = Column(String(50), nullable=False)
    # visit_confirmation | reminder | feedback
    # aggregate | cold_archive | cleanup  ← новые типы для Этапа 3
    scheduled_at   = Column(DateTime, nullable=False)
    completed      = Column(Boolean,  default=False)
    created_at     = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────
# ErrorLog — лог ошибок
# ─────────────────────────────────────────────

class ErrorLog(Base):
    """Лог ошибок приложения (frontend + backend)."""
    __tablename__ = "error_log"

    id         = Column(Integer, primary_key=True)
    venue_id   = Column(Integer, ForeignKey("venues.id", ondelete="SET NULL"),
                        nullable=True, index=True)
    source     = Column(String(20), nullable=False)   # frontend | backend
    level      = Column(String(20), nullable=False)   # error | warning | critical
    message    = Column(Text,       nullable=False)
    details    = Column(Text,       nullable=True)
    created_at = Column(DateTime,   default=datetime.utcnow)


# ─────────────────────────────────────────────
# RateLimitEntry — rate limiter
# ─────────────────────────────────────────────

class RateLimitEntry(Base):
    """
    Запись rate-limiter в БД.
    Сохраняется между перезапусками — предотвращает обход через рестарт.
    """
    __tablename__ = "rate_limit"
    __table_args__ = (
        Index("ix_rate_limit_ip", "ip"),
    )

    id           = Column(Integer,   primary_key=True)
    venue_id     = Column(Integer,   ForeignKey("venues.id", ondelete="CASCADE"),
                          nullable=True, index=True)
    ip           = Column(String(50), nullable=False)
    window_start = Column(DateTime,   nullable=False)
    count        = Column(Integer,    default=1, nullable=False)