"""
Тесты ORM-моделей: создание записей, значения по умолчанию.
"""

from datetime import date, time
from app.models import Reservation, ScheduledTask, ErrorLog


class TestReservationModel:
    """Тесты модели Reservation."""

    def test_create_reservation(self, db_session):
        """Создание бронирования и чтение из БД."""
        r = Reservation(
            name="Иван",
            guests=3,
            phone="9001234567",
            date=date(2026, 3, 15),
            time=time(14, 0),
        )
        db_session.add(r)
        db_session.commit()
        db_session.refresh(r)

        assert r.id is not None
        assert r.name == "Иван"
        assert r.guests == 3
        assert r.appeared is None  # не отмечено по умолчанию
        assert r.check is None
        assert r.vk_notifications is False

    def test_reservation_with_vk(self, db_session):
        """Бронирование с VK-данными."""
        r = Reservation(
            name="Мария",
            guests=2,
            phone="9001234567",
            date=date(2026, 3, 20),
            time=time(18, 30),
            vk_user_id=12345,
            vk_notifications=True,
        )
        db_session.add(r)
        db_session.commit()

        assert r.vk_user_id == 12345
        assert r.vk_notifications is True

    def test_mark_appeared(self, db_session):
        """Отметка о приходе и сумме чека."""
        r = Reservation(
            name="Тест",
            guests=1,
            phone="9001234567",
            date=date(2026, 3, 15),
            time=time(12, 0),
        )
        db_session.add(r)
        db_session.commit()

        r.appeared = True
        r.check = 1500
        db_session.commit()

        assert r.appeared is True
        assert r.check == 1500


class TestScheduledTaskModel:
    """Тесты модели ScheduledTask."""

    def test_create_task(self, db_session):
        """Создание отложенной задачи."""
        from datetime import datetime
        task = ScheduledTask(
            reservation_id=1,
            task_type="reminder",
            scheduled_at=datetime(2026, 3, 15, 13, 0),
        )
        db_session.add(task)
        db_session.commit()

        assert task.id is not None
        assert task.completed is False

    def test_complete_task(self, db_session):
        """Выполнение задачи."""
        from datetime import datetime
        task = ScheduledTask(
            reservation_id=1,
            task_type="feedback",
            scheduled_at=datetime(2026, 3, 16, 12, 0),
        )
        db_session.add(task)
        db_session.commit()

        task.completed = True
        db_session.commit()
        assert task.completed is True


class TestErrorLogModel:
    """Тесты модели ErrorLog."""

    def test_create_error_log(self, db_session):
        """Создание лога ошибки."""
        err = ErrorLog(
            source="frontend",
            level="error",
            message="Test error message",
            details="Stack trace here",
        )
        db_session.add(err)
        db_session.commit()

        assert err.id is not None
        assert err.source == "frontend"
        assert err.created_at is not None
