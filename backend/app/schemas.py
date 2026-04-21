"""
Pydantic-схемы для валидации входных данных и формата ответов.

ReservationCreate  — входные данные для создания брони.
ReservationResponse — формат ответа клиенту после создания.
ErrorReport        — отчёт об ошибке с фронтенда.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import date as Date, time as Time, datetime
import re


class ReservationCreate(BaseModel):
    """Валидация данных при создании бронирования."""

    name: str = Field(min_length=2, max_length=100, description="Имя гостя")
    guests: int = Field(ge=1, le=20, description="Количество гостей (1-20)")
    phone: str = Field(min_length=10, max_length=20, description="Телефон (цифры)")
    date: Date = Field(description="Дата визита")
    time: Time = Field(description="Время визита")
    comment: str | None = Field(default=None, max_length=500, description="Комментарий")
    vk_user_id: int | None = None
    vk_notifications: bool = False

    @field_validator("name")
    @classmethod
    def name_must_be_valid(cls, v: str) -> str:
        """Имя: только буквы, пробелы, дефисы."""
        cleaned = v.strip()
        if not re.match(r"^[a-zA-Zа-яА-ЯёЁ\s\-]+$", cleaned):
            raise ValueError("Имя содержит недопустимые символы")
        return cleaned

    @field_validator("phone")
    @classmethod
    def phone_must_be_digits(cls, v: str) -> str:
        """Телефон: только цифры, минимум 10."""
        digits = re.sub(r"\D", "", v)
        if len(digits) < 10:
            raise ValueError("Телефон должен содержать минимум 10 цифр")
        return digits


class ReservationResponse(BaseModel):
    """Формат ответа после успешного создания бронирования."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    guests: int
    phone: str
    date: Date
    time: Time
    comment: str | None = None


class ErrorReport(BaseModel):
    """Отчёт об ошибке с фронтенда."""
    message: str = Field(max_length=2000)
    details: str | None = Field(default=None, max_length=5000)
    source: str = Field(default="frontend", max_length=20)

# ─────────────────────────────────────────────
# Схемы для заведения
# ─────────────────────────────────────────────

class PlanLimitsResponse(BaseModel):
    """Информация о лимитах текущего тарифа."""
    bookings_per_month: int | None = None  # None = безлимит
    bookings_used_this_month: int = 0
    history_days: int | None = None        # None = вся история
    export_enabled: bool = False
    locations: int = 1


class VenueConfigResponse(BaseModel):
    """
    Ответ GET /api/config — всё необходимое фронтенду при старте.

    Если заведение не зарегистрировано — is_registered: false,
    остальные поля отсутствуют. Фронтенд показывает онбординг.
    """
    is_registered: bool

    # Поля ниже присутствуют только если is_registered: true
    venue_id: int | None = None
    name: str | None = None
    category: str | None = None
    timezone: str | None = None
    plan: str | None = None
    plan_expires_at: datetime | None = None
    plan_limits: PlanLimitsResponse | None = None
    config: dict | None = None


class VenueRegisterRequest(BaseModel):
    """Данные для регистрации нового заведения (POST /api/venue/register)."""
    name: str = Field(min_length=2, max_length=200)
    category: str = Field(min_length=2, max_length=50)
    address: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=30)
    timezone: str = Field(default="Europe/Moscow", max_length=50)
    config: dict | None = None  # если None — берётся шаблон по умолчанию


class VenueConfigUpdateRequest(BaseModel):
    """Данные для обновления конфига заведения (PATCH /api/venue/config)."""
    config: dict
    name: str | None = Field(default=None, min_length=2, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=30)
    timezone: str | None = Field(default=None, max_length=50)