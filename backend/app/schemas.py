"""
Pydantic-схемы для валидации входных данных и формата ответов.

ReservationCreate  — входные данные для создания брони.
ReservationResponse — формат ответа клиенту после создания.
ErrorReport        — отчёт об ошибке с фронтенда.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import date as Date, time as Time
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
