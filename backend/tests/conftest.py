"""
Фикстуры для тестов: тестовая БД (SQLite + aiosqlite), клиент FastAPI.

Важно:
- load_dotenv() вызывается ДО любых from app.* импортов
- Используется async SQLite (sqlite+aiosqlite) для совместимости с AsyncSession
- setup_database пересоздаёт таблицы перед каждым тестом
"""

import os
import pytest
from dotenv import load_dotenv

# Загружаем .env до импорта app.*, чтобы os.getenv("DB_PASSWORD") не был None
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from fastapi.testclient import TestClient

from app.database import Base
from app.main import app, get_db


# SQLite (sync) — для тестов моделей напрямую (без HTTP слоя)
SYNC_DATABASE_URL = "sqlite:///./test.db"
sync_engine = create_engine(SYNC_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSyncSessionLocal = sessionmaker(bind=sync_engine)

# SQLite (aiosqlite) — для тестов API через FastAPI AsyncSession
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


@pytest.fixture(autouse=True)
def setup_database():
    """Создаёт таблицы перед каждым тестом, удаляет после.

    Инициализирует оба engine: синхронный (для db_session)
    и асинхронный (для client/API-тестов).
    """
    import asyncio

    # Синхронный engine: создаём таблицы напрямую (для тестов моделей)
    Base.metadata.create_all(bind=sync_engine)

    # Асинхронный engine: создаём таблицы через run_sync
    async def _async_setup():
        async with test_async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def _async_teardown():
        async with test_async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    asyncio.run(_async_setup())
    yield
    Base.metadata.drop_all(bind=sync_engine)
    asyncio.run(_async_teardown())


@pytest.fixture
def client():
    """HTTP-клиент для тестирования API с async SQLite override."""
    # Сброс глобального rate limit между тестами
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
    """Синхронная сессия SQLite для прямого тестирования ORM-моделей."""
    db = TestingSyncSessionLocal()
    try:
        yield db
    finally:
        db.close()
