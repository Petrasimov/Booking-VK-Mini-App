"""
Фикстуры для тестов.

Используем один файл test.db для sync и async движков.
В setup_database: drop_all → create_all (вместо удаления файла).
Это гарантирует чистое состояние даже если файл заблокирован aiosqlite на Windows.
"""

import os
import pytest
import pytest_asyncio
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from app.database import Base
from app.main import app
from app.deps import get_db

# ─────────────────────────────────────────────
# Оба движка на один файл
# ─────────────────────────────────────────────

TEST_DB_FILE = "./test.db"
SYNC_URL     = f"sqlite:///{TEST_DB_FILE}"
ASYNC_URL    = f"sqlite+aiosqlite:///{TEST_DB_FILE}"

sync_engine = create_engine(
    SYNC_URL,
    connect_args={"check_same_thread": False},
)

test_async_engine = create_async_engine(
    ASYNC_URL,
    connect_args={"check_same_thread": False},
)

TestingSyncSessionLocal = sessionmaker(bind=sync_engine, autoflush=True)

TestingAsyncSessionLocal = async_sessionmaker(
    test_async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ─────────────────────────────────────────────
# Сброс и пересоздание БД перед каждым тестом
# ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_database():
    """
    drop_all → create_all перед каждым тестом.
    Не удаляем файл (он может быть заблокирован aiosqlite на Windows).
    drop_all очищает все таблицы и индексы, create_all создаёт заново.
    """
    # Сбрасываем пул соединений синхронного движка
    sync_engine.dispose()

    # Удаляем всё что есть в БД (если файл существует)
    try:
        Base.metadata.drop_all(bind=sync_engine)
    except Exception:
        pass

    # Пересоздаём таблицы
    Base.metadata.create_all(bind=sync_engine)

    yield

    # Очищаем после теста
    try:
        Base.metadata.drop_all(bind=sync_engine)
    except Exception:
        pass
    sync_engine.dispose()


# ─────────────────────────────────────────────
# Патч middleware
# ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_middleware_session():
    """Подменяет фабрику сессий в TenantMiddleware на тестовую."""
    import app.middleware as mw
    original = mw._session_factory
    mw._session_factory = TestingAsyncSessionLocal
    mw._venue_cache._store.clear()
    yield
    mw._session_factory = original
    mw._venue_cache._store.clear()


# ─────────────────────────────────────────────
# Синхронные фикстуры
# ─────────────────────────────────────────────

@pytest.fixture
def client():
    """Синхронный HTTP-клиент."""
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
    """Синхронная сессия для тестов моделей."""
    db = TestingSyncSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────────
# Асинхронные фикстуры
# ─────────────────────────────────────────────

@pytest_asyncio.fixture
async def async_db():
    """Асинхронная сессия для async тестов."""
    async with TestingAsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def async_client():
    """Асинхронный HTTP-клиент."""
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