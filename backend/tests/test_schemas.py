"""
Тесты Pydantic-схем: валидация входных данных.
"""

import pytest
from datetime import date, time
from pydantic import ValidationError
from app.schemas import ReservationCreate, ErrorReport


class TestReservationCreate:
    """Тесты валидации ReservationCreate."""

    def test_valid_reservation(self):
        """Корректные данные — создаётся без ошибок."""
        r = ReservationCreate(
            name="Иван",
            guests=3,
            phone="89001234567",
            date=date(2026, 3, 15),
            time=time(14, 0),
        )
        assert r.name == "Иван"
        assert r.guests == 3
        assert r.phone == "89001234567"  # валидатор оставляет только цифры

    def test_name_too_short(self):
        """Имя < 2 символов — ошибка."""
        with pytest.raises(ValidationError):
            ReservationCreate(
                name="A",
                guests=1,
                phone="89001234567",
                date=date(2026, 3, 15),
                time=time(14, 0),
            )

    def test_name_invalid_chars(self):
        """Имя с цифрами — ошибка."""
        with pytest.raises(ValidationError):
            ReservationCreate(
                name="Ivan123",
                guests=1,
                phone="89001234567",
                date=date(2026, 3, 15),
                time=time(14, 0),
            )

    def test_name_strips_whitespace(self):
        """Пробелы по краям убираются."""
        r = ReservationCreate(
            name="  Иван  ",
            guests=1,
            phone="89001234567",
            date=date(2026, 3, 15),
            time=time(14, 0),
        )
        assert r.name == "Иван"

    def test_guests_too_many(self):
        """Больше 20 гостей — ошибка."""
        with pytest.raises(ValidationError):
            ReservationCreate(
                name="Иван",
                guests=25,
                phone="89001234567",
                date=date(2026, 3, 15),
                time=time(14, 0),
            )

    def test_guests_zero(self):
        """0 гостей — ошибка."""
        with pytest.raises(ValidationError):
            ReservationCreate(
                name="Иван",
                guests=0,
                phone="89001234567",
                date=date(2026, 3, 15),
                time=time(14, 0),
            )

    def test_phone_too_short(self):
        """Телефон < 10 цифр — ошибка."""
        with pytest.raises(ValidationError):
            ReservationCreate(
                name="Иван",
                guests=1,
                phone="12345",
                date=date(2026, 3, 15),
                time=time(14, 0),
            )

    def test_phone_strips_non_digits(self):
        """Из телефона убираются все нецифровые символы."""
        r = ReservationCreate(
            name="Иван",
            guests=1,
            phone="+7 (900) 123-45-67",
            date=date(2026, 3, 15),
            time=time(14, 0),
        )
        assert r.phone == "79001234567"

    def test_optional_comment(self):
        """Комментарий может быть None."""
        r = ReservationCreate(
            name="Иван",
            guests=1,
            phone="89001234567",
            date=date(2026, 3, 15),
            time=time(14, 0),
        )
        assert r.comment is None

    def test_vk_fields_default(self):
        """VK-поля по умолчанию: None и False."""
        r = ReservationCreate(
            name="Иван",
            guests=1,
            phone="89001234567",
            date=date(2026, 3, 15),
            time=time(14, 0),
        )
        assert r.vk_user_id is None
        assert r.vk_notifications is False


class TestErrorReport:
    """Тесты валидации ErrorReport."""

    def test_valid_report(self):
        """Корректный отчёт."""
        r = ErrorReport(message="Something failed")
        assert r.message == "Something failed"
        assert r.source == "frontend"

    def test_custom_source(self):
        """Можно указать кастомный source."""
        r = ErrorReport(message="Error", source="backend")
        assert r.source == "backend"

    def test_empty_message_fails(self):
        """Пустое сообщение — ошибка (Pydantic)."""
        # message is required, not providing it raises error
        with pytest.raises(ValidationError):
            ErrorReport()
