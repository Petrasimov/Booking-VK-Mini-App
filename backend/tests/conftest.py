"""
Фикстуры для тестов: тестовая БД (SQLite + aiosqlite), клиент FastAPI.

Важно:
- load_dotenv() вызывается ДО любых from app.* импортов
- Используется async SQLite (sqlite+aiosqlite) для совместимости с AsyncSession
- setup_database пересоздаёт таблицы перед каждым тестом
- TenantMiddleware патчится для использования тестовой БД

Фикстуры:
  client        — синхронный TestClient (для существующих тестов)
  db_session    — синхронная SQLite сессия (для тестов моделей)
  async_client  — асинхронный AsyncClient (для тестов мультитенантности)
  async_db      — асинхронная SQLite сессия (для async тестов)
"""

import os
import pytest
import pytest_asyncio
from dotenv import load_dotenv

# Загружаем .env до импорта app.*, чтобы os.getenv("DB_PASSWORD") не был None
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from app.database import Base
from app.main import app
from app.deps import get_db


# ─────────────────────────────────────────────
# SQLite engines
# ─────────────────────────────────────────────

SYNC_DATABASE_URL = "sqlite:///./test.db"
sync_engine = create_engine(
    SYNC_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSyncSessionLocal = sessionmaker(bind=sync_engine)

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
test_async_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingAsyncSessionLocal = async_sessionmaker(
    test_async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ─────────────────────────────────────────────
# Создание/удаление таблиц — только через sync engine
# (aiosqlite использует тот же файл test.db)
# ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_database():
    """Создаёт таблицы перед каждым тестом, удаляет после."""
    Base.metadata.create_all(bind=sync_engine)
    yield
    Base.metadata.drop_all(bind=sync_engine)


# ─────────────────────────────────────────────
# Патч TenantMiddleware для использования тестовой БД
# ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_middleware_session():
    """
    Заменяет фабрику сессий в TenantMiddleware на тестовую SQLite.
    Без этого middleware ходит в реальную PostgreSQL и не находит тестовые данные.
    """
    import app.middleware as mw
    original = mw._session_factory
    mw._session_factory = TestingAsyncSessionLocal
    yield
    mw._session_factory = original


# ─────────────────────────────────────────────
# Синхронные фикстуры (существующие тесты)
# ─────────────────────────────────────────────

@pytest.fixture
def client():
    """Синхронный HTTP-клиент для тестирования API."""
    from app.main import _global_log
    _global_log.clear()

    async def override_get_db():
        async with TestingAsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def db_session():
    """Синхронная SQLite сессия для прямого тестирования ORM-моделей."""
    db = TestingSyncSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────────
# Асинхронные фикстуры (тесты мультитенантности)
# ─────────────────────────────────────────────

@pytest_asyncio.fixture
async def async_db():
    """Асинхронная SQLite сессия для async тестов."""
    async with TestingAsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def async_client():
    """Асинхронный HTTP-клиент для async тестов."""
    from app.main import _global_log
    _global_log.clear()

    async def override_get_db():
        async with TestingAsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()