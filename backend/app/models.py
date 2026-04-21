"""
ORM-модели базы данных.

Venue           — заведение (кафе, барбершоп, клиника и т.д.).
VenueRole       — роль пользователя VK в заведении (owner, manager, staff).
Reservation     — бронирование.
ScheduledTask   — отложенная задача (напоминание, фидбек, подтверждение).
ErrorLog        — лог ошибок приложения.
RateLimitEntry  — запись rate-limiter (хранится в БД между перезапусками).
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime,
    ForeignKey, Index, Integer, JSON, String, Text, Time,
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
    # Допустимые значения category:
    # cafe | barbershop | clinic | fitness | beauty | photo_studio | coworking | other

    config      = Column(JSON, nullable=False, default=dict)
    # Структура config задаётся шаблоном из venue_templates.py
    # и может быть изменена владельцем через панель управления.

    timezone    = Column(String(50),  nullable=False, default="Europe/Moscow")
    address     = Column(String(500), nullable=True)
    phone       = Column(String(30),  nullable=True)

    owner_vk_id = Column(BigInteger, nullable=False)
    # VK user_id владельца — дублируем здесь для быстрой проверки прав
    # без JOIN с venue_roles.

    # Тариф
    plan            = Column(String(20), nullable=False, default="free")
    # Допустимые значения: free | standard | pro
    plan_expires_at = Column(DateTime, nullable=True)
    # None = бессрочно (для free) или дата окончания платного плана.

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
        # Один пользователь — одна роль в одном заведении
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
# Reservation — бронирование
# ─────────────────────────────────────────────

class Reservation(Base):
    """Бронирование в заведении."""
    __tablename__ = "reservation"
    __table_args__ = (
        Index("ix_reservation_date",       "date"),
        Index("ix_reservation_phone_date", "phone", "date"),
        Index("ix_reservation_venue",      "venue_id"),
    )

    id      = Column(Integer, primary_key=True)
    # venue_id — обязателен для мультитенантности.
    # nullable=True временно, для обратной совместимости со старыми данными.
    # После seed-миграции все старые брони получат venue_id=1.
    venue_id = Column(Integer, ForeignKey("venues.id", ondelete="CASCADE"),
                      nullable=True, index=True)

    name    = Column(String(100), nullable=False)   # Имя гостя
    guests  = Column(Integer,     nullable=False)   # Количество гостей
    phone   = Column(String(20),  nullable=False)   # Телефон (только цифры)
    date    = Column(Date,        nullable=False)   # Дата визита
    time    = Column(Time,        nullable=False)   # Время визита
    comment = Column(String(500), nullable=True)    # Комментарий / пожелания

    # Дополнительные поля ниши (мастер, услуга, зал и т.д.)
    # Хранятся как JSON: {"master": "Алексей", "service": "Стрижка"}
    extra_data = Column(JSON, nullable=False, default=dict)

    vk_user_id        = Column(Integer,  nullable=True)   # VK ID гостя
    vk_notifications  = Column(Boolean,  default=False)   # Разрешил уведомления

    created_at         = Column(DateTime, default=datetime.utcnow)
    appeared           = Column(Boolean,  nullable=True)  # None = не отмечено
    visit_confirmed_by = Column(Integer,  nullable=True)
    check              = Column(Integer,  nullable=True)  # Сумма чека в рублях


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
    # visit_confirmation | reminder | feedback | aggregate | cold_archive | cleanup
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

    id           = Column(Integer,  primary_key=True)
    venue_id     = Column(Integer,  ForeignKey("venues.id", ondelete="CASCADE"),
                          nullable=True, index=True)
    ip           = Column(String(50), nullable=False)
    window_start = Column(DateTime,   nullable=False)
    count        = Column(Integer,    default=1, nullable=False)