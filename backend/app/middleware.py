"""
Middleware для мультитенантности.

TenantMiddleware — определяет заведение по vk_group_id из каждого запроса
и кладёт объект Venue в request.state.venue.

Логика:
    1. Читаем vk_group_id из заголовка X-VK-Group-ID или query-параметра group_id
    2. Проверяем LRU-кэш (TTL 5 минут, до 200 заведений)
    3. Если не в кэше — запрашиваем из БД
    4. Если не найдено — возвращаем 404
    5. Если найдено — кладём venue в request.state и продолжаем

Исключения (проходят без проверки tenant):
    - /api/health
    - /api/metrics
    - /docs, /redoc, /openapi.json
"""

from __future__ import annotations

import time
import logging
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Venue

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Простой LRU-кэш с TTL
# ─────────────────────────────────────────────────────────────────────────────

class _TTLCache:
    """
    Простой кэш с TTL и ограничением по размеру.
    Не требует внешних зависимостей.

    При превышении max_size удаляет самую старую запись.
    """

    def __init__(self, max_size: int = 200, ttl_seconds: int = 300):
        self._store: dict[int, tuple[Any, float]] = {}  # key → (value, expire_at)
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
            # Удаляем самую старую запись
            oldest_key = next(iter(self._store))
            del self._store[oldest_key]
        self._store[key] = (value, time.monotonic() + self._ttl)

    def invalidate(self, key: int) -> None:
        """Явно сбросить кэш для конкретного заведения (при обновлении конфига)."""
        self._store.pop(key, None)


# Глобальный кэш — один на весь процесс
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
}


def _is_exempt(path: str) -> bool:
    """Возвращает True если путь не требует проверки tenant."""
    return path in _EXEMPT_PATHS or path.startswith("/api/venue/register")


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
            return await call_next(request)

        # 1. Получаем group_id
        raw = (
            request.headers.get("X-VK-Group-ID")
            or request.query_params.get("group_id")
        )

        if not raw:
            # group_id не передан — продолжаем без venue
            # (эндпоинты которым он нужен сами вернут ошибку через get_venue())
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

        # 3. Если не в кэше — идём в БД
        if venue is None:
            db: Session = SessionLocal()
            try:
                venue = (
                    db.query(Venue)
                    .filter(Venue.vk_group_id == group_id, Venue.is_active == True)
                    .first()
                )
            finally:
                db.close()

            if venue is not None:
                _venue_cache.set(group_id, venue)
                logger.debug("Venue %d loaded from DB and cached", group_id)
            else:
                logger.debug("Venue with group_id=%d not found", group_id)

        # 4. Кладём venue в request.state (может быть None если не зарегистрировано)
        request.state.venue = venue

        return await call_next(request)


# ─────────────────────────────────────────────────────────────────────────────
# Публичные утилиты
# ─────────────────────────────────────────────────────────────────────────────

def invalidate_venue_cache(vk_group_id: int) -> None:
    """
    Сбросить кэш для заведения.
    Вызывать после обновления конфига через PATCH /api/venue/config.
    """
    _venue_cache.invalidate(vk_group_id)
    logger.info("Cache invalidated for vk_group_id=%d", vk_group_id)