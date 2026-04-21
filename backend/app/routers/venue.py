"""
Роутер для управления заведениями.

Эндпоинты:
  GET  /api/templates          — список шаблонов категорий для онбординга
  GET  /api/templates/{cat}    — шаблон конфига для конкретной категории
  POST /api/venue/register     — регистрация нового заведения
  GET  /api/venue/me           — информация о своём заведении
  PATCH /api/venue/config      — обновить конфиг заведения
  POST /api/venue/verify-bot   — проверить что VK бот настроен
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.middleware import invalidate_venue_cache
from app.models import Venue, VenueRole
from app.schemas import (
    VenueRegisterRequest,
    VenueConfigUpdateRequest,
    VenueConfigResponse,
    PlanLimitsResponse,
)
from app.venue_templates import (
    VENUE_CATEGORIES,
    get_default_config,
    get_templates_list,
)
from app.plan_limits import PLAN_LIMITS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Заведение"])


# ─────────────────────────────────────────────
# Dependency: async сессия БД
# ─────────────────────────────────────────────

async def get_db():
    async with AsyncSessionLocal() as db:
        yield db


# ─────────────────────────────────────────────
# Dependencies: проверка роли
# ─────────────────────────────────────────────

def get_venue_or_none(request: Request) -> Venue | None:
    return getattr(request.state, "venue", None)


def require_venue(request: Request) -> Venue:
    venue = getattr(request.state, "venue", None)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue_not_found")
    return venue


def require_owner(request: Request) -> Venue:
    """Только владелец заведения (owner)."""
    venue = require_venue(request)
    vk_user_id = _get_vk_user_id(request)
    if vk_user_id != venue.owner_vk_id:
        raise HTTPException(status_code=403, detail="owner_required")
    return venue


def require_owner_or_manager(request: Request) -> Venue:
    """Владелец или менеджер заведения."""
    venue = require_venue(request)
    vk_user_id = _get_vk_user_id(request)
    if vk_user_id is None:
        raise HTTPException(status_code=401, detail="vk_user_id_required")
    return venue


def _get_vk_user_id(request: Request) -> int | None:
    """Читает vk_user_id из заголовка X-VK-User-ID."""
    raw = request.headers.get("X-VK-User-ID")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


# ─────────────────────────────────────────────
# GET /api/templates
# ─────────────────────────────────────────────

@router.get("/templates", summary="Список шаблонов категорий")
async def list_templates():
    """
    Возвращает список всех категорий бизнеса для экрана выбора в онбординге.
    Каждый элемент: category, label, icon, accent_color, welcome_text.
    """
    return {"templates": get_templates_list()}


# ─────────────────────────────────────────────
# GET /api/templates/{category}
# ─────────────────────────────────────────────

@router.get("/templates/{category}", summary="Шаблон конфига по категории")
async def get_template(category: str):
    """
    Возвращает конфиг по умолчанию для указанной категории.
    Используется в онбординге для предзаполнения настроек.
    """
    if category not in VENUE_CATEGORIES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown category '{category}'. Valid: {', '.join(VENUE_CATEGORIES)}",
        )
    return {"category": category, "config": get_default_config(category)}


# ─────────────────────────────────────────────
# POST /api/venue/register
# ─────────────────────────────────────────────

@router.post("/venue/register", summary="Зарегистрировать заведение")
async def register_venue(
    body: VenueRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Регистрирует новое заведение.

    vk_group_id берётся из заголовка X-VK-Group-ID (обязателен).
    vk_user_id (владелец) берётся из заголовка X-VK-User-ID (обязателен).

    Если заведение с таким vk_group_id уже существует — возвращает 409.
    """
    # Получаем group_id из заголовка (Middleware уже проверил формат)
    raw_group_id = request.headers.get("X-VK-Group-ID")
    if not raw_group_id:
        raise HTTPException(status_code=400, detail="X-VK-Group-ID header required")
    group_id = int(raw_group_id)

    # Получаем vk_user_id владельца
    vk_user_id = _get_vk_user_id(request)
    if not vk_user_id:
        raise HTTPException(status_code=400, detail="X-VK-User-ID header required")

    # Проверяем что заведение ещё не зарегистрировано
    existing = (await db.execute(
        select(Venue).where(Venue.vk_group_id == group_id)
    )).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Venue with this vk_group_id already registered",
        )

    # Берём конфиг: из запроса или шаблон по умолчанию
    config = body.config or get_default_config(body.category)

    venue = Venue(
        vk_group_id=group_id,
        name=body.name,
        category=body.category,
        config=config,
        timezone=body.timezone,
        address=body.address,
        phone=body.phone,
        owner_vk_id=vk_user_id,
        plan="free",
    )
    db.add(venue)
    await db.flush()  # получаем id до коммита

    # Создаём роль owner
    role = VenueRole(
        venue_id=venue.id,
        vk_user_id=vk_user_id,
        role="owner",
    )
    db.add(role)
    await db.commit()
    await db.refresh(venue)

    logger.info(
        "New venue registered: id=%d name='%s' category=%s group_id=%d owner=%d",
        venue.id, venue.name, venue.category, group_id, vk_user_id,
    )

    return {
        "status": "registered",
        "venue_id": venue.id,
        "name": venue.name,
        "category": venue.category,
        "plan": venue.plan,
    }


# ─────────────────────────────────────────────
# GET /api/venue/me
# ─────────────────────────────────────────────

@router.get("/venue/me", summary="Информация о своём заведении")
async def get_my_venue(venue: Venue = Depends(require_venue)):
    """Возвращает полную информацию о заведении текущего запроса."""
    return {
        "venue_id":      venue.id,
        "vk_group_id":   venue.vk_group_id,
        "name":          venue.name,
        "category":      venue.category,
        "timezone":      venue.timezone,
        "address":       venue.address,
        "phone":         venue.phone,
        "plan":          venue.plan,
        "plan_expires_at": venue.plan_expires_at,
        "is_active":     venue.is_active,
        "created_at":    venue.created_at,
        "config":        venue.config,
    }


# ─────────────────────────────────────────────
# PATCH /api/venue/config
# ─────────────────────────────────────────────

@router.patch("/venue/config", summary="Обновить конфиг заведения")
async def update_venue_config(
    body: VenueConfigUpdateRequest,
    request: Request,
    venue: Venue = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Обновляет конфиг и/или основные поля заведения.
    Только для owner.
    После обновления сбрасывает кэш middleware.
    """
    venue.config = body.config
    if body.name:
        venue.name = body.name
    if body.address is not None:
        venue.address = body.address
    if body.phone is not None:
        venue.phone = body.phone
    if body.timezone:
        venue.timezone = body.timezone
    venue.updated_at = datetime.utcnow()

    db.add(venue)
    await db.commit()
    await db.refresh(venue)

    # Сбрасываем кэш — следующий запрос загрузит свежие данные
    invalidate_venue_cache(venue.vk_group_id)

    logger.info("Venue %d config updated by owner %d", venue.id, venue.owner_vk_id)

    return {"status": "updated", "venue_id": venue.id}


# ─────────────────────────────────────────────
# POST /api/venue/verify-bot
# ─────────────────────────────────────────────

@router.post("/venue/verify-bot", summary="Проверить подключение VK бота")
async def verify_bot(
    venue: Venue = Depends(require_owner),
):
    """
    Проверяет что в конфиге заведения указаны vk_group_token и notifications_chat_id.
    Отправляет тестовое сообщение в чат.
    """
    token   = venue.config.get("vk_group_token")
    chat_id = venue.config.get("notifications_chat_id")

    if not token:
        return {"status": "error", "detail": "vk_group_token not set in config"}
    if not chat_id:
        return {"status": "error", "detail": "notifications_chat_id not set in config"}

    # Отправляем тестовое сообщение
    try:
        from app.vk_bot import send_vk_chat_message_with_token
        success = await send_vk_chat_message_with_token(
            token=token,
            chat_id=chat_id,
            message=f"✅ Бот успешно подключён к заведению «{venue.name}»!",
        )
        if success:
            logger.info("Bot verified for venue %d", venue.id)
            return {"status": "ok", "detail": "Test message sent successfully"}
        else:
            return {"status": "error", "detail": "Failed to send test message"}
    except Exception as e:
        logger.error("Bot verification failed for venue %d: %s", venue.id, e)
        return {"status": "error", "detail": str(e)}