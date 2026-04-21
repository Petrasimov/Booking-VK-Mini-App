"""
ORM-модели базы данных.

Reservation     — бронирование столика.
ScheduledTask   — отложенная задача (напоминание, фидбек, подтверждение).
ErrorLog        — лог ошибок приложения.
RateLimitEntry  — запись rate-limiter (хранится в БД между перезапусками).
"""

from sqlalchemy import Column, Integer, String, Date, Time, DateTime, Boolean, Text, ForeignKey, Index
from datetime import datetime
from app.database import Base


class Reservation(Base):
    """Бронирование столика в кофейне."""
    __tablename__ = "reservation"
    __table_args__ = (
        # Индекс для поиска по дате (статистика, дубликаты)
        Index("ix_reservation_date", "date"),
        # Составной индекс для быстрой проверки дубликатов (phone + date)
        Index("ix_reservation_phone_date", "phone", "date"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)          # Имя гостя
    guests = Column(Integer, nullable=False)             # Количество гостей
    phone = Column(String(20), nullable=False)           # Телефон (только цифры)
    date = Column(Date, nullable=False)                  # Дата визита
    time = Column(Time, nullable=False)                  # Время визита
    comment = Column(String(500), nullable=True)         # Комментарий / пожелания

    vk_user_id = Column(Integer, nullable=True)          # VK ID гостя (для уведомлений)
    vk_notifications = Column(Boolean, default=False)    # Разрешил ли гость уведомления

    created_at = Column(DateTime, default=datetime.utcnow)  # Время создания записи
    appeared = Column(Boolean, nullable=True)                # Пришёл ли гость (None = не отмечено)
    visit_confirmed_by = Column(Integer, nullable=True)
    check = Column(Integer, nullable=True)                   # Сумма чека в рублях


class ScheduledTask(Base):
    """Отложенная задача, хранится в БД и выполняется планировщиком."""
    __tablename__ = "scheduled_task"
    __table_args__ = (
        # Составной индекс для быстрого поиска незавершённых задач с наступившим временем
        Index("ix_task_pending", "completed", "scheduled_at"),
    )

    id = Column(Integer, primary_key=True)
    # ForeignKey с CASCADE: при удалении брони задачи удаляются автоматически
    reservation_id = Column(
        Integer,
        ForeignKey("reservation.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_type = Column(String(50), nullable=False)       # visit_confirmation | reminder | feedback
    scheduled_at = Column(DateTime, nullable=False)      # Когда выполнить
    completed = Column(Boolean, default=False)           # Выполнена ли задача
    created_at = Column(DateTime, default=datetime.utcnow)


class ErrorLog(Base):
    """Лог ошибок приложения (frontend + backend)."""
    __tablename__ = "error_log"

    id = Column(Integer, primary_key=True)
    source = Column(String(20), nullable=False)          # frontend | backend
    level = Column(String(20), nullable=False)           # error | warning | critical
    message = Column(Text, nullable=False)               # Текст ошибки
    details = Column(Text, nullable=True)                # Стек-трейс / доп. информация
    created_at = Column(DateTime, default=datetime.utcnow)


class RateLimitEntry(Base):
    """
    Запись rate-limiter в БД.

    В отличие от in-memory подхода, сохраняется между перезапусками сервера.
    Это предотвращает обход лимита через рестарт приложения после деплоя.
    """
    __tablename__ = "rate_limit"
    __table_args__ = (
        Index("ix_rate_limit_ip", "ip"),
    )

    id = Column(Integer, primary_key=True)
    ip = Column(String(50), nullable=False)              # IP-адрес клиента
    window_start = Column(DateTime, nullable=False)      # Начало временного окна
    count = Column(Integer, default=1, nullable=False)   # Количество запросов в окне
