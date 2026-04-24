"""
Тесты панели владельца.

Проверяет:
  GET  /api/admin/bookings      — список броней с фильтрами
  PATCH /api/admin/bookings/{id} — обновление статуса
  GET  /api/admin/stats          — статистика
  GET  /api/admin/export/csv     — CSV экспорт
"""

import pytest
import pytest_asyncio
from datetime import date, time, timedelta
from httpx import AsyncClient
from sqlalchemy import select

from app.models import Venue, Reservation
from app.venue_templates import get_default_config


# ─────────────────────────────────────────────
# Фикстуры
# ─────────────────────────────────────────────

@pytest_asyncio.fixture
async def standard_venue(async_db):
    venue = Venue(
        vk_group_id=77001,
        name="Тест Стандарт",
        category="cafe",
        config=get_default_config("cafe"),
        owner_vk_id=9001,
        plan="standard",
    )
    async_db.add(venue)
    await async_db.commit()
    await async_db.refresh(venue)
    return venue


@pytest_asyncio.fixture
async def free_venue(async_db):
    venue = Venue(
        vk_group_id=77002,
        name="Тест Фри",
        category="cafe",
        config=get_default_config("cafe"),
        owner_vk_id=9002,
        plan="free",
    )
    async_db.add(venue)
    await async_db.commit()
    await async_db.refresh(venue)
    return venue


@pytest_asyncio.fixture
async def bookings_set(async_db, standard_venue):
    """Создаёт набор броней для тестов."""
    today = date.today()
    reservations = [
        Reservation(venue_id=standard_venue.id, name="Гость 1", guests=2,
                    phone="79001000001", date=today, time=time(10,0),
                    appeared=True,  extra_data={"zone": "Терраса"}),
        Reservation(venue_id=standard_venue.id, name="Гость 2", guests=1,
                    phone="79001000002", date=today, time=time(12,0),
                    appeared=False, extra_data={}),
        Reservation(venue_id=standard_venue.id, name="Гость 3", guests=3,
                    phone="79001000003", date=today, time=time(14,0),
                    appeared=None,  extra_data={"zone": "VIP"}),
    ]
    for r in reservations:
        async_db.add(r)
    await async_db.commit()
    return reservations


# ─────────────────────────────────────────────
# Тест 1: список броней возвращает все записи
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_bookings_list(async_client: AsyncClient, standard_venue, bookings_set):
    """GET /api/admin/bookings возвращает брони заведения."""
    response = await async_client.get(
        "/api/admin/bookings",
        headers={
            "X-VK-Group-ID": str(standard_venue.vk_group_id),
            "X-VK-User-ID":  str(standard_venue.owner_vk_id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


# ─────────────────────────────────────────────
# Тест 2: фильтр по статусу appeared
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_bookings_filter_appeared(
    async_client: AsyncClient, standard_venue, bookings_set
):
    """Фильтр appeared=true возвращает только пришедших."""
    response = await async_client.get(
        "/api/admin/bookings?appeared=true",
        headers={
            "X-VK-Group-ID": str(standard_venue.vk_group_id),
            "X-VK-User-ID":  str(standard_venue.owner_vk_id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Гость 1"


@pytest.mark.asyncio
async def test_admin_bookings_filter_null(
    async_client: AsyncClient, standard_venue, bookings_set
):
    """Фильтр appeared=null возвращает только ожидающих."""
    response = await async_client.get(
        "/api/admin/bookings?appeared=null",
        headers={
            "X-VK-Group-ID": str(standard_venue.vk_group_id),
            "X-VK-User-ID":  str(standard_venue.owner_vk_id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Гость 3"


# ─────────────────────────────────────────────
# Тест 3: обновление статуса брони
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_booking_status(
    async_client: AsyncClient, async_db, standard_venue, bookings_set
):
    """PATCH /api/admin/bookings/{id} обновляет appeared."""
    # Находим бронь с appeared=None
    booking = next(r for r in bookings_set if r.appeared is None)

    response = await async_client.patch(
        f"/api/admin/bookings/{booking.id}",
        json={"appeared": True},
        headers={
            "X-VK-Group-ID": str(standard_venue.vk_group_id),
            "X-VK-User-ID":  str(standard_venue.owner_vk_id),
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "updated"

    # Проверяем в БД
    await async_db.refresh(booking)
    assert booking.appeared is True


# ─────────────────────────────────────────────
# Тест 4: нельзя обновить чужую бронь
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_booking_wrong_venue(
    async_client: AsyncClient, standard_venue, free_venue, bookings_set
):
    """Нельзя обновить бронь другого заведения."""
    booking = bookings_set[0]

    response = await async_client.patch(
        f"/api/admin/bookings/{booking.id}",
        json={"appeared": True},
        headers={
            "X-VK-Group-ID": str(free_venue.vk_group_id),
            "X-VK-User-ID":  str(free_venue.owner_vk_id),
        },
    )
    assert response.status_code == 404


# ─────────────────────────────────────────────
# Тест 5: статистика
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_stats(async_client: AsyncClient, standard_venue, bookings_set):
    """GET /api/admin/stats возвращает корректные метрики."""
    response = await async_client.get(
        "/api/admin/stats?period=30d",
        headers={
            "X-VK-Group-ID": str(standard_venue.vk_group_id),
            "X-VK-User-ID":  str(standard_venue.owner_vk_id),
        },
    )
    assert response.status_code == 200
    data = response.json()

    assert data["total"]   == 3
    assert data["guests"]  == 6   # 2+1+3
    assert data["came"]    == 1
    assert data["no_show"] == 1
    assert "daily"          in data
    assert "popular_hours"  in data


# ─────────────────────────────────────────────
# Тест 6: CSV экспорт на Standard
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_csv_export_standard(async_client: AsyncClient, standard_venue, bookings_set):
    """CSV экспорт доступен на Standard тарифе."""
    response = await async_client.get(
        "/api/admin/export/csv",
        headers={
            "X-VK-Group-ID": str(standard_venue.vk_group_id),
            "X-VK-User-ID":  str(standard_venue.owner_vk_id),
        },
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")

    content = response.content.decode("utf-8-sig")
    assert "Гость 1" in content
    assert "Гость 2" in content
    assert "Терраса" in content   # extra_data.zone


# ─────────────────────────────────────────────
# Тест 7: CSV экспорт заблокирован на Free
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_csv_export_free_blocked(async_client: AsyncClient, free_venue):
    """CSV экспорт недоступен на Free тарифе → 402."""
    response = await async_client.get(
        "/api/admin/export/csv",
        headers={
            "X-VK-Group-ID": str(free_venue.vk_group_id),
            "X-VK-User-ID":  str(free_venue.owner_vk_id),
        },
    )
    assert response.status_code == 402


# ─────────────────────────────────────────────
# Тест 8: пагинация
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_bookings_pagination(
    async_client: AsyncClient, async_db, standard_venue
):
    """Пагинация работает корректно."""
    today = date.today()
    for i in range(5):
        async_db.add(Reservation(
            venue_id=standard_venue.id, name=f"Гость {i}",
            guests=1, phone=f"7900200000{i}",
            date=today, time=time(10+i, 0), extra_data={},
        ))
    await async_db.commit()

    # Страница 1 — 2 записи
    r1 = await async_client.get(
        "/api/admin/bookings?page=1&page_size=2",
        headers={
            "X-VK-Group-ID": str(standard_venue.vk_group_id),
            "X-VK-User-ID":  str(standard_venue.owner_vk_id),
        },
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["total"]   == 5
    assert d1["pages"]   == 3
    assert len(d1["items"]) == 2

    # Страница 3 — 1 запись
    r3 = await async_client.get(
        "/api/admin/bookings?page=3&page_size=2",
        headers={
            "X-VK-Group-ID": str(standard_venue.vk_group_id),
            "X-VK-User-ID":  str(standard_venue.owner_vk_id),
        },
    )
    assert r3.status_code == 200
    assert len(r3.json()["items"]) == 1


# ─────────────────────────────────────────────
# Тест 9: изоляция — владелец видит только свои брони
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_bookings_isolated(
    async_client: AsyncClient, async_db, standard_venue, free_venue
):
    """Владелец видит только брони своего заведения."""
    today = date.today()

    async_db.add(Reservation(
        venue_id=standard_venue.id, name="Мой гость",
        guests=1, phone="79003000001",
        date=today, time=time(10,0), extra_data={},
    ))
    async_db.add(Reservation(
        venue_id=free_venue.id, name="Чужой гость",
        guests=1, phone="79003000002",
        date=today, time=time(10,0), extra_data={},
    ))
    await async_db.commit()

    response = await async_client.get(
        "/api/admin/bookings",
        headers={
            "X-VK-Group-ID": str(standard_venue.vk_group_id),
            "X-VK-User-ID":  str(standard_venue.owner_vk_id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Мой гость"