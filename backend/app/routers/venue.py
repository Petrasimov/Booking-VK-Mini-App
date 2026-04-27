"""
Роутер для управления заведениями.

Эндпоинты:
  GET   /api/templates              — список шаблонов категорий для онбординга
  GET   /api/templates/{cat}        — шаблон конфига для конкретной категории
  POST  /api/venue/register         — регистрация нового заведения
  GET   /api/venue/me               — информация о своём заведении
  PATCH /api/venue/config           — обновить конфиг заведения
  POST  /api/venue/verify-bot       — проверить что VK бот настроен

  Панель владельца:
  GET   /api/admin/bookings         — список броней с фильтрами и пагинацией
  PATCH /api/admin/bookings/{id}    — обновить статус брони (appeared/cancel)
  GET   /api/admin/stats            — статистика заведения
  GET   /api/admin/export/csv       — экспорт броней в CSV (Standard+ only)
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, extract, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.middleware import invalidate_venue_cache
from app.models import Venue, VenueRole, Reservation, VenueStatsDaily
from app.plan_limits import PLAN_LIMITS
from app.schemas import (
    VenueRegisterRequest,
    VenueConfigUpdateRequest,
)
from app.venue_templates import (
    VENUE_CATEGORIES,
    get_default_config,
    get_templates_list,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Заведение"])


# ─────────────────────────────────────────────
# Dependencies
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
    raw = request.headers.get("X-VK-User-ID")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _get_history_cutoff(venue: Venue) -> date | None:
    """Возвращает дату начала доступной истории по тарифу."""
    limits = PLAN_LIMITS.get(venue.plan, PLAN_LIMITS["free"])
    days = limits.get("history_days")
    if days is None:
        return None  # безлимит
    return date.today() - __import__("datetime").timedelta(days=days)


# ─────────────────────────────────────────────
# GET /api/templates
# ─────────────────────────────────────────────

@router.get("/templates", summary="Список шаблонов категорий")
async def list_templates():
    """Возвращает все категории бизнеса для экрана выбора в онбординге."""
    return {"templates": get_templates_list()}


# ─────────────────────────────────────────────
# GET /api/templates/{category}
# ─────────────────────────────────────────────

@router.get("/templates/{category}", summary="Шаблон конфига по категории")
async def get_template(category: str):
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
    raw_group_id = request.headers.get("X-VK-Group-ID")
    if not raw_group_id:
        raise HTTPException(status_code=400, detail="X-VK-Group-ID header required")
    group_id = int(raw_group_id)

    vk_user_id = _get_vk_user_id(request)
    if not vk_user_id:
        raise HTTPException(status_code=400, detail="X-VK-User-ID header required")

    existing = (await db.execute(
        select(Venue).where(Venue.vk_group_id == group_id)
    )).scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=409, detail="Venue with this vk_group_id already registered")

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
    await db.flush()

    db.add(VenueRole(venue_id=venue.id, vk_user_id=vk_user_id, role="owner"))
    await db.commit()
    await db.refresh(venue)

    logger.info(
        "New venue registered: id=%d name='%s' category=%s group_id=%d owner=%d",
        venue.id, venue.name, venue.category, group_id, vk_user_id,
    )

    return {"status": "registered", "venue_id": venue.id, "name": venue.name,
            "category": venue.category, "plan": venue.plan}


# ─────────────────────────────────────────────
# GET /api/venue/me
# ─────────────────────────────────────────────

@router.get("/venue/me", summary="Информация о своём заведении")
async def get_my_venue(venue: Venue = Depends(require_venue)):
    return {
        "venue_id":       venue.id,
        "vk_group_id":    venue.vk_group_id,
        "name":           venue.name,
        "category":       venue.category,
        "timezone":       venue.timezone,
        "address":        venue.address,
        "phone":          venue.phone,
        "plan":           venue.plan,
        "plan_expires_at": venue.plan_expires_at,
        "is_active":      venue.is_active,
        "created_at":     venue.created_at,
        "config":         venue.config,
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
    venue.config = body.config
    if body.name:      venue.name     = body.name
    if body.address is not None: venue.address  = body.address
    if body.phone   is not None: venue.phone    = body.phone
    if body.timezone: venue.timezone = body.timezone
    venue.updated_at = datetime.utcnow()

    db.add(venue)
    await db.commit()
    await db.refresh(venue)

    invalidate_venue_cache(venue.vk_group_id)
    logger.info("Venue %d config updated by owner %d", venue.id, venue.owner_vk_id)
    return {"status": "updated", "venue_id": venue.id}


# ─────────────────────────────────────────────
# POST /api/venue/verify-bot
# ─────────────────────────────────────────────

@router.post("/venue/verify-bot", summary="Проверить подключение VK бота")
async def verify_bot(venue: Venue = Depends(require_owner)):
    token   = venue.config.get("vk_group_token")
    chat_id = venue.config.get("notifications_chat_id")

    if not token:
        return {"status": "error", "detail": "vk_group_token not set in config"}
    if not chat_id:
        return {"status": "error", "detail": "notifications_chat_id not set in config"}

    try:
        from app.vk_bot import send_vk_chat_message_with_token
        success = await send_vk_chat_message_with_token(
            token=token, chat_id=chat_id,
            message=f"✅ Бот успешно подключён к заведению «{venue.name}»!",
        )
        if success:
            return {"status": "ok", "detail": "Test message sent successfully"}
        return {"status": "error", "detail": "Failed to send test message"}
    except Exception as e:
        logger.error("Bot verification failed for venue %d: %s", venue.id, e)
        return {"status": "error", "detail": str(e)}


# ─────────────────────────────────────────────
# GET /api/admin/bookings — список броней
# ─────────────────────────────────────────────

@router.get("/admin/bookings", summary="Список броней заведения")
async def get_admin_bookings(
    request: Request,
    db: AsyncSession       = Depends(get_db),
    venue: Venue           = Depends(require_owner_or_manager),
    page: int              = Query(1,    ge=1,   description="Страница"),
    page_size: int         = Query(20,   ge=1,   le=100),
    date_from: date | None = Query(None, description="Фильтр: с даты YYYY-MM-DD"),
    date_to:   date | None = Query(None, description="Фильтр: по дату YYYY-MM-DD"),
    appeared: str | None   = Query(None, description="Фильтр: true | false | null"),
):
    """
    Возвращает список броней заведения с пагинацией и фильтрами.
    Учитывает тарифный лимит истории.
    """
    cutoff = _get_history_cutoff(venue)

    filters = [Reservation.venue_id == venue.id]
    if cutoff:
        filters.append(Reservation.date >= cutoff)
    if date_from:
        filters.append(Reservation.date >= date_from)
    if date_to:
        filters.append(Reservation.date <= date_to)
    if appeared == "true":
        filters.append(Reservation.appeared == True)
    elif appeared == "false":
        filters.append(Reservation.appeared == False)
    elif appeared == "null":
        filters.append(Reservation.appeared == None)

    total = (await db.execute(
        select(func.count()).select_from(Reservation).where(and_(*filters))
    )).scalar() or 0

    items = (await db.execute(
        select(Reservation)
        .where(and_(*filters))
        .order_by(Reservation.date.desc(), Reservation.time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     (total + page_size - 1) // page_size,
        "items": [
            {
                "id":         r.id,
                "name":       r.name,
                "guests":     r.guests,
                "phone":      r.phone,
                "date":       str(r.date),
                "time":       r.time.strftime("%H:%M") if r.time else None,
                "comment":    r.comment,
                "extra_data": r.extra_data,
                "appeared":   r.appeared,
                "check":      r.check,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in items
        ],
    }


# ─────────────────────────────────────────────
# PATCH /api/admin/bookings/{booking_id}
# ─────────────────────────────────────────────

@router.patch("/admin/bookings/{booking_id}", summary="Обновить статус брони")
async def update_booking_status(
    booking_id: int,
    request:    Request,
    db:         AsyncSession = Depends(get_db),
    venue:      Venue        = Depends(require_owner_or_manager),
):
    """
    Обновляет поля appeared и check у брони.
    Тело запроса: { "appeared": true/false/null, "check": 1500 }
    Только для owner и manager.
    """
    body = await request.json()

    reservation = (await db.execute(
        select(Reservation).where(
            Reservation.id       == booking_id,
            Reservation.venue_id == venue.id,
        )
    )).scalar_one_or_none()

    if not reservation:
        raise HTTPException(status_code=404, detail="Booking not found")

    if "appeared" in body:
        val = body["appeared"]
        reservation.appeared = bool(val) if val is not None else None

    if "check" in body and body["check"] is not None:
        reservation.check = int(body["check"])

    db.add(reservation)
    await db.commit()

    logger.info("Booking #%d updated by venue %d", booking_id, venue.id)
    return {"status": "updated", "booking_id": booking_id}


# ─────────────────────────────────────────────
# GET /api/admin/stats — статистика
# ─────────────────────────────────────────────

@router.get("/admin/stats", summary="Статистика заведения")
async def get_admin_stats(
    request:    Request,
    db:         AsyncSession = Depends(get_db),
    venue:      Venue        = Depends(require_owner_or_manager),
    period:     str          = Query("30d", description="Период: 7d | 30d | 90d | all"),
):
    """
    Возвращает агрегированную статистику заведения.
    Для периодов в пределах истории тарифа — из таблицы reservation.
    Для более глубоких периодов — из venue_stats_daily.
    """
    # Определяем период запроса
    period_days = {"7d": 7, "30d": 30, "90d": 90}.get(period)
    cutoff = _get_history_cutoff(venue)

    # Статистика из Hot-таблицы (reservation)
    hot_filters = [Reservation.venue_id == venue.id]
    if period_days:
        from datetime import timedelta
        hot_filters.append(
            Reservation.date >= date.today() - __import__("datetime").timedelta(days=period_days)
        )
    if cutoff:
        hot_filters.append(Reservation.date >= cutoff)

    total = (await db.execute(
        select(func.count()).select_from(Reservation).where(and_(*hot_filters))
    )).scalar() or 0

    guests = (await db.execute(
        select(func.sum(Reservation.guests)).where(and_(*hot_filters))
    )).scalar() or 0

    came = (await db.execute(
        select(func.count()).select_from(Reservation).where(
            and_(*hot_filters, Reservation.appeared == True)
        )
    )).scalar() or 0

    no_show = (await db.execute(
        select(func.count()).select_from(Reservation).where(
            and_(*hot_filters, Reservation.appeared == False)
        )
    )).scalar() or 0

    # Брони по дням (для графика)
    from sqlalchemy import cast, String
    daily_rows = (await db.execute(
        select(
            Reservation.date,
            func.count().label("bookings"),
            func.sum(Reservation.guests).label("guests"),
        )
        .where(and_(*hot_filters))
        .group_by(Reservation.date)
        .order_by(Reservation.date)
    )).all()

    # Популярные часы
    hour_rows = (await db.execute(
        select(
            func.extract("hour", Reservation.time).label("hour"),
            func.count().label("count"),
        )
        .where(and_(*hot_filters))
        .group_by(func.extract("hour", Reservation.time))
        .order_by(func.count().desc())
        .limit(5)
    )).all()

    return {
        "period":   period,
        "total":    total,
        "guests":   guests,
        "came":     came,
        "no_show":  no_show,
        "conversion": round(came / total * 100, 1) if total > 0 else 0,
        "daily": [
            {"date": str(row.date), "bookings": row.bookings, "guests": row.guests or 0}
            for row in daily_rows
        ],
        "popular_hours": [
            {"hour": int(row.hour), "count": row.count}
            for row in hour_rows
            if row.hour is not None
        ],
    }


# ─────────────────────────────────────────────
# GET /api/admin/export/csv — CSV экспорт
# ─────────────────────────────────────────────

@router.get("/admin/export/csv", summary="Экспорт броней в CSV")
async def export_bookings_csv(
    request: Request,
    db:      AsyncSession = Depends(get_db),
    venue:   Venue        = Depends(require_owner_or_manager),
    appeared: str | None  = Query(None, description="Фильтр: true | false | null"),
):
    """
    Экспортирует брони заведения в CSV файл с учётом фильтра appeared.
    Доступно только на тарифе Standard и Pro.
    """
    limits = PLAN_LIMITS.get(venue.plan, PLAN_LIMITS["free"])
    if not limits.get("export", False):
        raise HTTPException(
            status_code=402,
            detail="CSV экспорт доступен на тарифах Standard и Pro",
        )

    cutoff = _get_history_cutoff(venue)
    filters = [Reservation.venue_id == venue.id]
    if cutoff:
        filters.append(Reservation.date >= cutoff)
    if appeared == "true":
        filters.append(Reservation.appeared == True)
    elif appeared == "false":
        filters.append(Reservation.appeared == False)
    elif appeared == "null":
        filters.append(Reservation.appeared == None)

    reservations = (await db.execute(
        select(Reservation)
        .where(and_(*filters))
        .order_by(Reservation.date.desc(), Reservation.time)
    )).scalars().all()

    # Собираем все ключи extra_data для заголовков
    extra_keys: list[str] = []
    for r in reservations:
        for k in (r.extra_data or {}).keys():
            if k not in extra_keys:
                extra_keys.append(k)

    # Генерируем CSV в памяти
    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM для Excel

    fieldnames = ["ID", "Имя", "Гостей", "Телефон", "Дата", "Время",
                  "Комментарий", "Пришёл", "Чек", "Создано"] + extra_keys

    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for r in reservations:
        row = {
            "ID":          r.id,
            "Имя":         r.name,
            "Гостей":      r.guests,
            "Телефон":     r.phone,
            "Дата":        str(r.date),
            "Время":       r.time.strftime("%H:%M") if r.time else "",
            "Комментарий": r.comment or "",
            "Пришёл":      ("Да" if r.appeared else "Нет") if r.appeared is not None else "",
            "Чек":         r.check or "",
            "Создано":     r.created_at.strftime("%d.%m.%Y %H:%M") if r.created_at else "",
        }
        for k in extra_keys:
            row[k] = (r.extra_data or {}).get(k, "")
        writer.writerow(row)

    output.seek(0)
    filename = f"bookings_{venue.id}_{date.today()}.csv"

    logger.info("CSV export for venue %d: %d rows", venue.id, len(reservations))

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )