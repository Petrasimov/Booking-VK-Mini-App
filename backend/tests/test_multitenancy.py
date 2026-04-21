"""
Тесты мультитенантности.

Проверяет:
  - Изоляцию данных между заведениями
  - Работу TenantMiddleware
  - Эндпоинт GET /api/config
  - Регистрацию заведения
  - Шаблоны категорий
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.models import Venue, VenueRole, Reservation
from app.venue_templates import get_default_config, VENUE_CATEGORIES


# ─────────────────────────────────────────────
# Фикстуры: два тестовых заведения
# ─────────────────────────────────────────────

@pytest_asyncio.fixture
async def venue_a(async_db):
    """Заведение А — кафе."""
    venue = Venue(
        vk_group_id=111111,
        name="Кафе Альфа",
        category="cafe",
        config=get_default_config("cafe"),
        owner_vk_id=1001,
        plan="free",
    )
    async_db.add(venue)
    await async_db.commit()
    await async_db.refresh(venue)
    return venue


@pytest_asyncio.fixture
async def venue_b(async_db):
    """Заведение Б — барбершоп."""
    venue = Venue(
        vk_group_id=222222,
        name="Барбершоп Бета",
        category="barbershop",
        config=get_default_config("barbershop"),
        owner_vk_id=2002,
        plan="standard",
    )
    async_db.add(venue)
    await async_db.commit()
    await async_db.refresh(venue)
    return venue


@pytest_asyncio.fixture
async def reservation_a(async_db, venue_a):
    """Бронь в заведении А."""
    from datetime import date, time
    r = Reservation(
        venue_id=venue_a.id,
        name="Гость Альфа",
        guests=2,
        phone="79001112233",
        date=date(2026, 6, 1),
        time=time(12, 0),
    )
    async_db.add(r)
    await async_db.commit()
    await async_db.refresh(r)
    return r


@pytest_asyncio.fixture
async def reservation_b(async_db, venue_b):
    """Бронь в заведении Б."""
    from datetime import date, time
    r = Reservation(
        venue_id=venue_b.id,
        name="Гость Бета",
        guests=1,
        phone="79009998877",
        date=date(2026, 6, 1),
        time=time(14, 0),
    )
    async_db.add(r)
    await async_db.commit()
    await async_db.refresh(r)
    return r


# ─────────────────────────────────────────────
# Тест 1: изоляция данных
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_two_venues_isolated(async_db, venue_a, venue_b, reservation_a, reservation_b):
    """Заведение А не видит брони заведения Б и наоборот."""
    result_a = await async_db.execute(
        select(Reservation).where(Reservation.venue_id == venue_a.id)
    )
    bookings_a = result_a.scalars().all()

    result_b = await async_db.execute(
        select(Reservation).where(Reservation.venue_id == venue_b.id)
    )
    bookings_b = result_b.scalars().all()

    assert len(bookings_a) == 1
    assert len(bookings_b) == 1
    assert bookings_a[0].name == "Гость Альфа"
    assert bookings_b[0].name == "Гость Бета"

    ids_a = {r.venue_id for r in bookings_a}
    ids_b = {r.venue_id for r in bookings_b}
    assert ids_a.isdisjoint(ids_b)


# ─────────────────────────────────────────────
# Тест 2: Middleware — нет group_id
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_config_without_group_id(async_client: AsyncClient):
    """GET /api/config без X-VK-Group-ID возвращает is_registered: false."""
    response = await async_client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data["is_registered"] is False


# ─────────────────────────────────────────────
# Тест 3: Middleware — незарегистрированный group_id
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_config_unknown_group_id(async_client: AsyncClient):
    """GET /api/config с неизвестным group_id возвращает is_registered: false."""
    response = await async_client.get(
        "/api/config",
        headers={"X-VK-Group-ID": "999999999"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_registered"] is False


# ─────────────────────────────────────────────
# Тест 4: GET /api/config для зарегистрированного заведения
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_config_registered_venue(async_client: AsyncClient, venue_a):
    """GET /api/config с известным group_id возвращает корректный конфиг."""
    response = await async_client.get(
        "/api/config",
        headers={"X-VK-Group-ID": str(venue_a.vk_group_id)}
    )
    assert response.status_code == 200
    data = response.json()

    assert data["is_registered"] is True
    assert data["venue_id"] == venue_a.id
    assert data["name"] == "Кафе Альфа"
    assert data["category"] == "cafe"
    assert data["plan"] == "free"
    assert "config" in data
    assert "time_slots" in data["config"]


# ─────────────────────────────────────────────
# Тест 5: Разные заведения получают разные конфиги
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_config_different_venues(async_client: AsyncClient, venue_a, venue_b):
    """Два разных group_id возвращают данные своих заведений."""
    resp_a = await async_client.get(
        "/api/config",
        headers={"X-VK-Group-ID": str(venue_a.vk_group_id)}
    )
    resp_b = await async_client.get(
        "/api/config",
        headers={"X-VK-Group-ID": str(venue_b.vk_group_id)}
    )

    data_a = resp_a.json()
    data_b = resp_b.json()

    assert data_a["venue_id"] != data_b["venue_id"]
    assert data_a["category"] == "cafe"
    assert data_b["category"] == "barbershop"
    assert data_a["name"] == "Кафе Альфа"
    assert data_b["name"] == "Барбершоп Бета"


# ─────────────────────────────────────────────
# Тест 6: Регистрация нового заведения
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_new_venue(async_client: AsyncClient, async_db):
    """POST /api/venue/register создаёт новое заведение."""
    response = await async_client.post(
        "/api/venue/register",
        json={
            "name": "Новый Барбершоп",
            "category": "barbershop",
            "timezone": "Europe/Moscow",
        },
        headers={
            "X-VK-Group-ID": "333333",
            "X-VK-User-ID":  "5005",
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "registered"
    assert data["name"] == "Новый Барбершоп"
    assert data["category"] == "barbershop"

    venue = (await async_db.execute(
        select(Venue).where(Venue.vk_group_id == 333333)
    )).scalar_one_or_none()
    assert venue is not None
    assert venue.owner_vk_id == 5005
    assert venue.plan == "free"


# ─────────────────────────────────────────────
# Тест 7: Повторная регистрация — 409
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_duplicate_venue(async_client: AsyncClient, venue_a):
    """POST /api/venue/register с существующим group_id возвращает 409."""
    response = await async_client.post(
        "/api/venue/register",
        json={"name": "Дубликат", "category": "cafe"},
        headers={
            "X-VK-Group-ID": str(venue_a.vk_group_id),
            "X-VK-User-ID":  "1001",
        }
    )
    assert response.status_code == 409


# ─────────────────────────────────────────────
# Тест 8: GET /api/templates
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_templates(async_client: AsyncClient):
    """GET /api/templates возвращает все 8 категорий."""
    response = await async_client.get("/api/templates")
    assert response.status_code == 200
    data = response.json()

    assert "templates" in data
    assert len(data["templates"]) == len(VENUE_CATEGORIES)

    categories = [t["category"] for t in data["templates"]]
    for cat in VENUE_CATEGORIES:
        assert cat in categories


# ─────────────────────────────────────────────
# Тест 9: GET /api/templates/{category}
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_template_cafe(async_client: AsyncClient):
    """GET /api/templates/cafe возвращает корректный шаблон."""
    response = await async_client.get("/api/templates/cafe")
    assert response.status_code == 200
    data = response.json()

    assert data["category"] == "cafe"
    assert "config" in data
    assert "time_slots" in data["config"]
    assert "fields" in data["config"]
    assert data["config"]["fields"]["guests"]["enabled"] is True


@pytest.mark.asyncio
async def test_get_template_unknown(async_client: AsyncClient):
    """GET /api/templates/unknown возвращает 404."""
    response = await async_client.get("/api/templates/unknown_category")
    assert response.status_code == 404


# ─────────────────────────────────────────────
# Тест 10: venue_role создаётся при регистрации
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_venue_role_created_on_register(async_client: AsyncClient, async_db):
    """При регистрации заведения создаётся роль owner."""
    await async_client.post(
        "/api/venue/register",
        json={"name": "Тест Роль", "category": "other"},
        headers={
            "X-VK-Group-ID": "444444",
            "X-VK-User-ID":  "7007",
        }
    )

    venue = (await async_db.execute(
        select(Venue).where(Venue.vk_group_id == 444444)
    )).scalar_one_or_none()

    assert venue is not None

    role = (await async_db.execute(
        select(VenueRole).where(
            VenueRole.venue_id   == venue.id,
            VenueRole.vk_user_id == 7007,
        )
    )).scalar_one_or_none()

    assert role is not None
    assert role.role == "owner"