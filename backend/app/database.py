"""
Модуль подключения к базе данных PostgreSQL.

Создаёт два engine:
  - sync engine (SessionLocal)    — используется в scheduler, vk_bot_server, admin
  - async engine (AsyncSessionLocal) — используется в FastAPI эндпоинтах

Все параметры берутся из переменных окружения (файл .env).
"""

import os
import logging
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

logger = logging.getLogger(__name__)

# --- Параметры подключения из переменных окружения ---
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")          # Обязательно — задаётся в .env
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "reservation")

if not DB_PASSWORD:
    logger.warning(
        "DB_PASSWORD не задан в .env — подключение к PostgreSQL может не работать. "
        "Добавьте строку DB_PASSWORD=... в backend/.env"
    )
    DB_PASSWORD = ""

# Кодируем пароль для безопасной подстановки в URL
encoded_password = quote_plus(DB_PASSWORD)

# --- Синхронный engine (psycopg2) — для scheduler, vk_bot_server, admin ---
DATABASE_URL = f"postgresql://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,   # Проверяет живость соединения перед использованием
        pool_size=10,         # Пул из 10 соединений
        max_overflow=20,      # До 20 дополнительных при пиковой нагрузке
    )
    SessionLocal = sessionmaker(bind=engine)
except Exception as _e:
    logger.warning("Sync PostgreSQL engine unavailable (%s) — using NullPool fallback for tests", _e)
    from sqlalchemy.pool import NullPool
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=NullPool)
    SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# --- Асинхронный engine (asyncpg) — для FastAPI эндпоинтов ---
ASYNC_DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

try:
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        echo=False,
    )
    AsyncSessionLocal = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
except Exception as _ae:
    logger.warning("Async PostgreSQL engine unavailable (%s) — using aiosqlite fallback for tests", _ae)
    async_engine = create_async_engine(
        "sqlite+aiosqlite:///./test.db",
        connect_args={"check_same_thread": False},
    )
    AsyncSessionLocal = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

logger.info("Database: %s@%s:%s/%s", DB_USER, DB_HOST, DB_PORT, DB_NAME)
