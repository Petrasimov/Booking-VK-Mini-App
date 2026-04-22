"""
Тесты универсальных категорий бизнеса.

Проверяет:
  - Бронирование с extra_data (мастер, услуга, зона)
  - Разные категории заведений
  - Тарифный лимит (free = 30 броней/мес)
  - extra_data сохраняется в БД
"""

import pytest
import pytest_asyncio
from datetime import date, time
from httpx import AsyncClient
from sqlalchemy import select

from app.models import Venue, Reservation
from app.venue_templates import get_default_config


# ─────────────────────────────────────────────
# Фикстуры заведений разных категорий
# ─────────────────────────────────────────────

@pytest_asyncio.fixture
async def cafe_venue(async_db):
    venue = Venue(
        vk_group_id=10001,
        name="Тест Кафе",
        category="cafe",
        config=get_default_config("cafe"),
        owner_vk_id=1,
        plan="free",
    )
    async_db.add(venue)
    await async_db.commit()
    await async_db.refresh(venue)
    return venue


@pytest_asyncio.fixture
async def barbershop_venue(async_db):
    config = get_default_config("barbershop")
    config["fields"]["master"]["options"] = ["Алексей", "Дмитрий"]
    config["fields"]["service"]["options"] = ["Стрижка", "Борода", "Комбо"]
    venue = Venue(
        vk_group_id=10002,
        name="Тест Барбершоп",
        category="barbershop",
        config=config,
        owner_vk_id=2,
        plan="standard",
    )
    async_db.add(venue)
    await async_db.commit()
    await async_db.refresh(venue)
    return venue


@pytest_asyncio.fixture
async def clinic_venue(async_db):
    config = get_default_config("clinic")
    config["fields"]["master"]["options"] = ["Врач Иванов", "Врач Петров"]
    config["fields"]["service"]["options"] = ["Первичный приём", "Повторный приём"]
    venue = Venue(
        vk_group_id=10003,
        name="Тест Клиника",
        category="clinic",
        config=config,
        owner_vk_id=3,
        plan="pro",
    )
    async_db.add(venue)
    await async_db.commit()
    await async_db.refresh(venue)
    return venue


# ─────────────────────────────────────────────
# Тест 1: бронирование кафе (с гостями и зоной)
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cafe_booking_with_guests_and_zone(async_client: AsyncClient, cafe_venue):
    """Бронь в кафе с полем guests и extra_data.zone."""
    response = await async_client.post(
        "/api/reservation",
        json={
            "name":       "Иван Петров",
            "guests":     3,
            "phone":      "79001234567",
            "date":       "2026-12-01",
            "time":       "19:00:00",
            "comment":    "У окна пожалуйста",
            "extra_data": {"zone": "Терраса"},
        },
        headers={"X-VK-Group-ID": str(cafe_venue.vk_group_id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Иван Петров"
    assert data["guests"] == 3


@pytest.mark.asyncio
async def test_cafe_booking_extra_data_saved(async_client: AsyncClient, async_db, cafe_venue):
    """extra_data сохраняется в БД корректно."""
    await async_client.post(
        "/api/reservation",
        json={
            "name":       "Мария Сидорова",
            "guests":     2,
            "phone":      "79009876543",
            "date":       "2026-12-02",
            "time":       "18:00:00",
            "extra_data": {"zone": "VIP", "comment_extra": "без аллергенов"},
        },
        headers={"X-VK-Group-ID": str(cafe_venue.vk_group_id)},
    )

    reservation = (await async_db.execute(
        select(Reservation).where(Reservation.phone == "79009876543")
    )).scalar_one_or_none()

    assert reservation is not None
    assert reservation.extra_data == {"zone": "VIP", "comment_extra": "без аллергенов"}
    assert reservation.venue_id == cafe_venue.id


# ─────────────────────────────────────────────
# Тест 2: бронирование барбершопа (мастер + услуга)
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_barbershop_booking_with_master_and_service(
    async_client: AsyncClient, async_db, barbershop_venue
):
    """Бронь в барбершопе с мастером и услугой."""
    response = await async_client.post(
        "/api/reservation",
        json={
            "name":       "Сергей Козлов",
            "guests":     1,
            "phone":      "79111234567",
            "date":       "2026-12-03",
            "time":       "10:30:00",
            "extra_data": {"master": "Алексей", "service": "Стрижка + борода"},
        },
        headers={"X-VK-Group-ID": str(barbershop_venue.vk_group_id)},
    )
    assert response.status_code == 200

    reservation = (await async_db.execute(
        select(Reservation).where(Reservation.phone == "79111234567")
    )).scalar_one_or_none()

    assert reservation is not None
    assert reservation.extra_data["master"]  == "Алексей"
    assert reservation.extra_data["service"] == "Стрижка + борода"
    assert reservation.venue_id == barbershop_venue.id


# ─────────────────────────────────────────────
# Тест 3: бронирование клиники (врач + тип приёма)
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_clinic_booking_with_doctor(
    async_client: AsyncClient, async_db, clinic_venue
):
    """Бронь в клинике с врачом и типом приёма."""
    response = await async_client.post(
        "/api/reservation",
        json={
            "name":       "Анна Новикова",
            "guests":     1,
            "phone":      "79221234567",
            "date":       "2026-12-04",
            "time":       "09:00:00",
            "extra_data": {"master": "Врач Иванов", "service": "Первичный приём"},
        },
        headers={"X-VK-Group-ID": str(clinic_venue.vk_group_id)},
    )
    assert response.status_code == 200

    reservation = (await async_db.execute(
        select(Reservation).where(Reservation.phone == "79221234567")
    )).scalar_one_or_none()

    assert reservation is not None
    assert reservation.extra_data["master"]  == "Врач Иванов"
    assert reservation.extra_data["service"] == "Первичный приём"


# ─────────────────────────────────────────────
# Тест 4: бронирование без extra_data
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_booking_without_extra_data(async_client: AsyncClient, cafe_venue):
    """Бронь без extra_data проходит корректно."""
    response = await async_client.post(
        "/api/reservation",
        json={
            "name":   "Пётр Смирнов",
            "guests": 1,
            "phone":  "79331234567",
            "date":   "2026-12-05",
            "time":   "12:00:00",
        },
        headers={"X-VK-Group-ID": str(cafe_venue.vk_group_id)},
    )
    assert response.status_code == 200


# ─────────────────────────────────────────────
# Тест 5: venue_id привязывается к брони
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reservation_gets_correct_venue_id(
    async_client: AsyncClient, async_db, cafe_venue, barbershop_venue
):
    """Брони из разных заведений получают правильные venue_id."""
    await async_client.post(
        "/api/reservation",
        json={
            "name": "Гость Кафе", "guests": 1,
            "phone": "79441111111", "date": "2026-12-06", "time": "13:00:00",
        },
        headers={"X-VK-Group-ID": str(cafe_venue.vk_group_id)},
    )
    await async_client.post(
        "/api/reservation",
        json={
            "name": "Гость Барбер", "guests": 1,
            "phone": "79442222222", "date": "2026-12-06", "time": "13:00:00",
        },
        headers={"X-VK-Group-ID": str(barbershop_venue.vk_group_id)},
    )

    r_cafe = (await async_db.execute(
        select(Reservation).where(Reservation.phone == "79441111111")
    )).scalar_one_or_none()

    r_barber = (await async_db.execute(
        select(Reservation).where(Reservation.phone == "79442222222")
    )).scalar_one_or_none()

    assert r_cafe   is not None
    assert r_barber is not None
    assert r_cafe.venue_id   == cafe_venue.id
    assert r_barber.venue_id == barbershop_venue.id
    assert r_cafe.venue_id   != r_barber.venue_id


# ─────────────────────────────────────────────
# Тест 6: тарифный лимит free = 30 броней
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_free_plan_booking_limit(async_client: AsyncClient, async_db, cafe_venue):
    """Free-тариф блокирует бронь при превышении 30/мес."""
    # Создаём 30 броней напрямую в БД (текущий месяц)
    from datetime import date as d
    today = d.today()

    for i in range(30):
        async_db.add(Reservation(
            venue_id=cafe_venue.id,
            name=f"Гость {i}",
            guests=1,
            phone=f"7900000{i:04d}",
            date=today,
            time=time(10, 0),
        ))
    await async_db.commit()

    # 31-я бронь должна быть заблокирована
    response = await async_client.post(
        "/api/reservation",
        json={
            "name":   "Лишний Гость",
            "guests": 1,
            "phone":  "79999999999",
            "date":   str(today),
            "time":   "11:00:00",
        },
        headers={"X-VK-Group-ID": str(cafe_venue.vk_group_id)},
    )
    assert response.status_code == 402
    assert "Лимит" in response.json()["detail"]


# ─────────────────────────────────────────────
# Тест 7: standard-тариф без лимита броней
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_standard_plan_no_booking_limit(async_client: AsyncClient, async_db, barbershop_venue):
    """Standard-тариф не блокирует брони (лимит = None)."""
    # Создаём 35 броней в текущем месяце
    from datetime import date as d
    today = d.today()

    for i in range(35):
        async_db.add(Reservation(
            venue_id=barbershop_venue.id,
            name=f"Клиент {i}",
            guests=1,
            phone=f"7800000{i:04d}",
            date=today,
            time=time(10, 0),
        ))
    await async_db.commit()

    # 36-я бронь должна пройти
    response = await async_client.post(
        "/api/reservation",
        json={
            "name":   "Новый Клиент",
            "guests": 1,
            "phone":  "78999999999",
            "date":   str(today),
            "time":   "11:00:00",
        },
        headers={"X-VK-Group-ID": str(barbershop_venue.vk_group_id)},
    )
    assert response.status_code == 200


# ─────────────────────────────────────────────
# Тест 8: шаблон барбершопа содержит нужные поля
# ─────────────────────────────────────────────

def test_barbershop_template_has_master_and_service():
    """Шаблон барбершопа содержит поля master и service."""
    config = get_default_config("barbershop")
    assert config["fields"]["master"]["enabled"]  is True
    assert config["fields"]["service"]["enabled"] is True
    assert config["fields"]["guests"]["enabled"]  is False


def test_cafe_template_has_guests_and_zone():
    """Шаблон кафе содержит поля guests и zone."""
    config = get_default_config("cafe")
    assert config["fields"]["guests"]["enabled"] is True
    assert config["fields"]["zone"]["enabled"]   is True
    assert config["fields"]["master"]["enabled"] is False


def test_clinic_template_has_service():
    """Шаблон клиники содержит поле service."""
    config = get_default_config("clinic")
    assert config["fields"]["service"]["enabled"] is True
    assert len(config["fields"]["service"]["options"]) > 0