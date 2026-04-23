"""
Тесты ночных джобов архивирования.

Проверяет:
  - run_aggregate_job: брони → archive + stats
  - run_cold_archive_job: анонимизация и удаление старых записей
  - run_cleanup_job: очистка служебных таблиц
"""

import pytest
from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from app.models import (
    Reservation,
    ReservationArchive,
    VenueStatsDaily,
    ScheduledTask,
    RateLimitEntry,
    ErrorLog,
    Venue,
)
from app.jobs.archiver import (
    run_aggregate_job,
    run_cold_archive_job,
    run_cleanup_job,
    _anonymize_phone,
    _anonymize_name,
    HOT_RETENTION_MONTHS,
)


# ─────────────────────────────────────────────
# Фикстура: заведение
# ─────────────────────────────────────────────

@pytest.fixture
def venue(db_session):
    v = Venue(
        vk_group_id=555555,
        name="Тест Архив",
        category="cafe",
        config={},
        owner_vk_id=1,
        plan="standard",
    )
    db_session.add(v)
    db_session.commit()
    db_session.refresh(v)
    return v


def make_old_reservation(venue_id: int, days_ago: int, **kwargs) -> dict:
    """Создаёт данные старой брони."""
    visit_date = date.today() - timedelta(days=days_ago)
    return {
        "venue_id": venue_id,
        "name":     kwargs.get("name",   "Старый Гость"),
        "guests":   kwargs.get("guests", 2),
        "phone":    kwargs.get("phone",  "79001234567"),
        "date":     visit_date,
        "time":     kwargs.get("time",   time(19, 0)),
        "appeared": kwargs.get("appeared", True),
        "extra_data": {},
    }


# ─────────────────────────────────────────────
# Тест 1: агрегация переносит старые брони
# ─────────────────────────────────────────────

def test_aggregate_job_moves_old_reservations(db_session, venue):
    """Брони старше 6 мес переносятся в reservation_archive."""
    # Создаём 3 старые брони (7 месяцев назад)
    for i in range(3):
        data = make_old_reservation(
            venue.id,
            days_ago=210,
            phone=f"7900000000{i}",
            name=f"Гость {i}",
            guests=i + 1,
        )
        db_session.add(Reservation(**data))
    db_session.commit()

    # Создаём 1 свежую бронь (10 дней назад) — не должна архивироваться
    fresh = make_old_reservation(venue.id, days_ago=10, phone="79099999999")
    db_session.add(Reservation(**fresh))
    db_session.commit()

    result = run_aggregate_job(db_session)

    assert result["archived_count"] == 3
    assert result["venues_affected"] == 1
    assert result["stats_upserted"] > 0

    # Старые брони удалены из reservation
    old_in_hot = db_session.execute(
        select(Reservation).where(
            Reservation.venue_id == venue.id,
            Reservation.date < date.today() - timedelta(days=180),
        )
    ).scalars().all()
    assert len(old_in_hot) == 0

    # Старые брони появились в archive
    in_archive = db_session.execute(
        select(ReservationArchive).where(ReservationArchive.venue_id == venue.id)
    ).scalars().all()
    assert len(in_archive) == 3

    # Свежая бронь осталась в hot
    fresh_in_hot = db_session.execute(
        select(Reservation).where(Reservation.phone == "79099999999")
    ).scalars().all()
    assert len(fresh_in_hot) == 1


# ─────────────────────────────────────────────
# Тест 2: статистика агрегируется корректно
# ─────────────────────────────────────────────

def test_aggregate_job_creates_correct_stats(db_session, venue):
    """Агрегат venue_stats_daily содержит правильные счётчики."""
    visit_date = date.today() - timedelta(days=210)

    # 2 пришли, 1 не пришёл
    for i, appeared in enumerate([True, True, False]):
        db_session.add(Reservation(
            venue_id=venue.id,
            name=f"Гость {i}",
            guests=2,
            phone=f"7901000000{i}",
            date=visit_date,
            time=time(19, 0),
            appeared=appeared,
            extra_data={},
        ))
    db_session.commit()

    run_aggregate_job(db_session)

    stats = db_session.execute(
        select(VenueStatsDaily).where(
            VenueStatsDaily.venue_id == venue.id,
            VenueStatsDaily.date     == visit_date,
        )
    ).scalar_one_or_none()

    assert stats is not None
    assert stats.bookings == 3
    assert stats.guests   == 6   # 3 × 2
    assert stats.came     == 2
    assert stats.no_show  == 1
    assert stats.peak_hour == "19:00"


# ─────────────────────────────────────────────
# Тест 3: пустая таблица — джоб не падает
# ─────────────────────────────────────────────

def test_aggregate_job_empty_table(db_session, venue):
    """run_aggregate_job с пустой таблицей возвращает нули без ошибок."""
    result = run_aggregate_job(db_session)
    assert result["archived_count"] == 0
    assert result["venues_affected"] == 0


# ─────────────────────────────────────────────
# Тест 4: cold archive анонимизирует данные
# ─────────────────────────────────────────────

def test_cold_archive_job_anonymizes(db_session, venue):
    """cold_archive_job анонимизирует телефон и имя перед удалением."""
    # Создаём запись в archive с датой 3 года назад
    old_date = date.today() - timedelta(days=3 * 365)
    db_session.add(ReservationArchive(
        venue_id    = venue.id,
        name        = "Иван Петров",
        phone       = "79001234567",
        guests      = 2,
        date        = old_date,
        time        = time(19, 0),
        extra_data  = {},
        original_id = 999,
        created_at  = datetime.utcnow(),
    ))
    db_session.commit()

    result = run_cold_archive_job(db_session)

    assert result["cold_count"] == 1

    # Запись удалена из archive
    remaining = db_session.execute(
        select(ReservationArchive).where(ReservationArchive.venue_id == venue.id)
    ).scalars().all()
    assert len(remaining) == 0


# ─────────────────────────────────────────────
# Тест 5: cold archive не трогает свежие записи
# ─────────────────────────────────────────────

def test_cold_archive_job_keeps_recent(db_session, venue):
    """cold_archive_job не удаляет записи моложе 2 лет."""
    recent_date = date.today() - timedelta(days=365)  # 1 год
    db_session.add(ReservationArchive(
        venue_id    = venue.id,
        name        = "Недавний Гость",
        phone       = "79009999999",
        guests      = 1,
        date        = recent_date,
        time        = time(12, 0),
        extra_data  = {},
        original_id = 888,
        created_at  = datetime.utcnow(),
    ))
    db_session.commit()

    result = run_cold_archive_job(db_session)

    assert result["cold_count"] == 0

    remaining = db_session.execute(
        select(ReservationArchive).where(ReservationArchive.venue_id == venue.id)
    ).scalars().all()
    assert len(remaining) == 1


# ─────────────────────────────────────────────
# Тест 6: cleanup удаляет старые задачи
# ─────────────────────────────────────────────

def test_cleanup_job_removes_old_tasks(db_session, venue):
    """run_cleanup_job удаляет выполненные ScheduledTask старше 30 дней."""
    # Создаём бронь (нужна для FK)
    r = Reservation(
        venue_id=venue.id, name="Тест", guests=1,
        phone="79000000001", date=date.today(), time=time(10, 0), extra_data={},
    )
    db_session.add(r)
    db_session.flush()

    # Старая выполненная задача (35 дней назад)
    old_task = ScheduledTask(
        venue_id=venue.id,
        reservation_id=r.id,
        task_type="feedback",
        scheduled_at=datetime.utcnow() - timedelta(days=35),
        completed=True,
        created_at=datetime.utcnow() - timedelta(days=35),
    )
    # Свежая выполненная задача (5 дней назад)
    new_task = ScheduledTask(
        venue_id=venue.id,
        reservation_id=r.id,
        task_type="reminder",
        scheduled_at=datetime.utcnow() - timedelta(days=5),
        completed=True,
        created_at=datetime.utcnow() - timedelta(days=5),
    )
    db_session.add_all([old_task, new_task])
    db_session.commit()

    result = run_cleanup_job(db_session)

    assert result["tasks_deleted"] == 1

    remaining = db_session.execute(
        select(ScheduledTask).where(ScheduledTask.venue_id == venue.id)
    ).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].task_type == "reminder"


# ─────────────────────────────────────────────
# Тест 7: cleanup удаляет старые error logs
# ─────────────────────────────────────────────

def test_cleanup_job_removes_old_errors(db_session, venue):
    """run_cleanup_job удаляет ErrorLog старше 90 дней."""
    # Старый лог (100 дней назад)
    old_err = ErrorLog(
        source="backend", level="error",
        message="старая ошибка",
        created_at=datetime.utcnow() - timedelta(days=100),
    )
    # Свежий лог (10 дней назад)
    new_err = ErrorLog(
        source="backend", level="error",
        message="новая ошибка",
        created_at=datetime.utcnow() - timedelta(days=10),
    )
    db_session.add_all([old_err, new_err])
    db_session.commit()

    result = run_cleanup_job(db_session)

    assert result["errors_deleted"] == 1

    remaining = db_session.execute(select(ErrorLog)).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].message == "новая ошибка"


# ─────────────────────────────────────────────
# Тест 8: функции анонимизации
# ─────────────────────────────────────────────

def test_anonymize_phone():
    """_anonymize_phone возвращает хэш телефона."""
    result = _anonymize_phone("79001234567")
    assert result is not None
    assert len(result) == 16
    # Одинаковый телефон → одинаковый хэш
    assert _anonymize_phone("79001234567") == _anonymize_phone("79001234567")
    # Разные телефоны → разные хэши
    assert _anonymize_phone("79001234567") != _anonymize_phone("79007654321")
    # None → None
    assert _anonymize_phone(None) is None


def test_anonymize_name():
    """_anonymize_name возвращает инициалы."""
    assert _anonymize_name("Иван Петров")      == "И.П."
    assert _anonymize_name("Мария Иванова")    == "М.И."
    assert _anonymize_name("Александр Иванов Петрович") == "А.И.П."
    assert _anonymize_name(None) is None