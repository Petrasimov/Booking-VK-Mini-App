"""
Middleware для мультитенантности.

TenantMiddleware — определяет заведение по vk_group_id из каждого запроса
и кладёт объект Venue в request.state.venue.

Логика:
    1. Читаем vk_group_id из заголовка X-VK-Group-ID или query-параметра group_id
    2. Проверяем LRU-кэш (TTL 5 минут, до 200 заведений)
    3. Если не в кэше — запрашиваем из AsyncSession
    4. Если не найдено — venue остаётся None (не 404, эндпоинты сами решают)
    5. Если найдено — кладём venue в request.state и продолжаем

Исключения (проходят без проверки tenant):
    - /api/health
    - /api/metrics
    - /docs, /redoc, /openapi.json
    - /api/venue/register
"""

from __future__ import annotations

import time
import logging
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware

from app.models import Venue

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Patchable session factory — заменяется в тестах на SQLite
# ─────────────────────────────────────────────────────────────────────────────

def _get_async_session_factory() -> async_sessionmaker:
    """
    Возвращает фабрику сессий.
    Lazy import чтобы избежать циклических импортов.
    В тестах заменяется через: middleware._session_factory = TestingFactory
    """
    from app.database import AsyncSessionLocal
    return AsyncSessionLocal


# Модуль-уровневая переменная — заменяема в тестах
_session_factory: async_sessionmaker | None = None


def _get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = _get_async_session_factory()
    return _session_factory


# ─────────────────────────────────────────────────────────────────────────────
# Простой LRU-кэш с TTL
# ─────────────────────────────────────────────────────────────────────────────

class _TTLCache:
    """Простой кэш с TTL и ограничением по размеру."""

    def __init__(self, max_size: int = 200, ttl_seconds: int = 300):
        self._store: dict[int, tuple[Any, float]] = {}
        self._max_size   = max_size
        self._ttl        = ttl_seconds

    def get(self, key: int) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expire_at = entry
        if time.monotonic() > expire_at:
            del self._store[key]
            return None
        return value

    def set(self, key: int, value: Any) -> None:
        if len(self._store) >= self._max_size:
            oldest_key = next(iter(self._store))
            del self._store[oldest_key]
        self._store[key] = (value, time.monotonic() + self._ttl)

    def invalidate(self, key: int) -> None:
        """Явно сбросить кэш для заведения (при обновлении конфига)."""
        self._store.pop(key, None)


# Глобальный кэш
_venue_cache = _TTLCache(max_size=200, ttl_seconds=300)


# ─────────────────────────────────────────────────────────────────────────────
# Пути, которые не требуют проверки tenant
# ─────────────────────────────────────────────────────────────────────────────

_EXEMPT_PATHS = {
    "/api/health",
    "/api/metrics",
    "/api/metrics/prometheus",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
}


def _is_exempt(path: str) -> bool:
    if path in _EXEMPT_PATHS:
        return True
    if path.startswith("/api/venue/register"):
        return True
    if path.startswith("/api/templates"):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# TenantMiddleware
# ─────────────────────────────────────────────────────────────────────────────

class TenantMiddleware(BaseHTTPMiddleware):
    """
    Определяет заведение по vk_group_id и добавляет его в request.state.venue.

    vk_group_id читается из (в порядке приоритета):
        1. Заголовок:      X-VK-Group-ID: 123456789
        2. Query-параметр: ?group_id=123456789
    """

    async def dispatch(self, request: Request, call_next):
        # Пропускаем служебные пути
        if _is_exempt(request.url.path):
            request.state.venue = None
            return await call_next(request)

        # 1. Получаем group_id
        raw = (
            request.headers.get("X-VK-Group-ID")
            or request.query_params.get("group_id")
        )

        if not raw:
            request.state.venue = None
            return await call_next(request)

        try:
            group_id = int(raw)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_group_id", "detail": "group_id must be an integer"},
            )

        # 2. Проверяем кэш
        venue = _venue_cache.get(group_id)

        # 3. Если не в кэше — идём в БД (async)
        if venue is None:
            try:
                factory = _get_session_factory()
                async with factory() as db:
                    result = await db.execute(
                        select(Venue).where(
                            Venue.vk_group_id == group_id,
                            Venue.is_active == True,
                        )
                    )
                    venue = result.scalar_one_or_none()

                if venue is not None:
                    _venue_cache.set(group_id, venue)
                    logger.debug("Venue %d loaded from DB and cached", group_id)
                else:
                    logger.debug("Venue with group_id=%d not found", group_id)
            except Exception as e:
                logger.error("TenantMiddleware DB error for group_id=%d: %s", group_id, e)
                venue = None

        # 4. Кладём venue в request.state (может быть None)
        request.state.venue = venue

        return await call_next(request)


# ─────────────────────────────────────────────────────────────────────────────
# Публичные утилиты
# ─────────────────────────────────────────────────────────────────────────────

def invalidate_venue_cache(vk_group_id: int) -> None:
    """Сбросить кэш для заведения после обновления конфига."""
    _venue_cache.invalidate(vk_group_id)
    logger.info("Cache invalidated for vk_group_id=%d", vk_group_id)