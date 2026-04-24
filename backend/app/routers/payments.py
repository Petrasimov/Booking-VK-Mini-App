"""
Роутер платежей (ЮKassa).

Эндпоинты:
  POST /api/payments/create   — создать платёж → вернуть ссылку на оплату
  POST /api/payments/webhook  — обработать callback от ЮKassa
  GET  /api/payments/history  — история платежей заведения

Настройка (Часть II — после регистрации в ЮKassa):
  В backend/.env добавить:
    YOOKASSA_SHOP_ID=ваш_shop_id
    YOOKASSA_SECRET_KEY=ваш_secret_key

До настройки — все эндпоинты возвращают демо-ответы (sandbox режим).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.models import Payment, Venue
from app.plan_limits import PLAN_LIMITS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["Платежи"])

# ─────────────────────────────────────────────
# Конфигурация ЮKassa
# ─────────────────────────────────────────────

YOOKASSA_SHOP_ID   = os.getenv("YOOKASSA_SHOP_ID",   "")
YOOKASSA_SECRET    = os.getenv("YOOKASSA_SECRET_KEY", "")
SANDBOX_MODE       = not (YOOKASSA_SHOP_ID and YOOKASSA_SECRET)

# Цены тарифов (₽)
PLAN_PRICES = {
    "standard": 499,
    "pro":      1299,
}

# ─────────────────────────────────────────────
# Dependencies
# ─────────────────────────────────────────────

def require_venue(request: Request) -> Venue:
    venue = getattr(request.state, "venue", None)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue_not_found")
    return venue


# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────

class CreatePaymentRequest(BaseModel):
    plan:   str  # standard | pro
    months: int = 1


# ─────────────────────────────────────────────
# POST /api/payments/create
# ─────────────────────────────────────────────

@router.post("/create", summary="Создать платёж")
async def create_payment(
    body:    CreatePaymentRequest,
    request: Request,
    db:      AsyncSession = Depends(get_db),
):
    """
    Создаёт платёж в ЮKassa и возвращает ссылку на оплату.

    В sandbox-режиме (ключи не настроены):
      - Возвращает демо-ответ с mock payment_url
      - Платёж сохраняется в БД со статусом pending

    После настройки ключей ЮKassa:
      - Создаёт реальный платёж через API ЮKassa
      - Возвращает настоящую ссылку на страницу оплаты
    """
    venue = require_venue(request)

    if body.plan not in PLAN_PRICES:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {body.plan}")

    if body.months < 1 or body.months > 12:
        raise HTTPException(status_code=400, detail="months must be between 1 and 12")

    amount = PLAN_PRICES[body.plan] * body.months

    # Сохраняем платёж в БД
    payment = Payment(
        venue_id = venue.id,
        amount   = amount,
        plan     = body.plan,
        months   = body.months,
        status   = "pending",
    )
    db.add(payment)
    await db.flush()  # получаем id

    if SANDBOX_MODE:
        # Демо-режим: возвращаем mock ссылку
        logger.info(
            "SANDBOX: Payment #%d created for venue %d plan=%s amount=%d",
            payment.id, venue.id, body.plan, amount,
        )
        payment.yookassa_id = f"sandbox_{payment.id}_{uuid.uuid4().hex[:8]}"
        await db.commit()

        return {
            "status":      "created",
            "payment_id":  payment.id,
            "amount":      amount,
            "plan":        body.plan,
            "months":      body.months,
            "payment_url": f"https://yookassa.ru/demo?payment_id={payment.id}",
            "sandbox":     True,
            "note":        "Настройте YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY для реальных платежей",
        }

    # Реальный режим: создаём платёж через ЮKassa SDK
    try:
        from yookassa import Configuration, Payment as YKPayment

        Configuration.account_id = YOOKASSA_SHOP_ID
        Configuration.secret_key  = YOOKASSA_SECRET

        yk_payment = YKPayment.create({
            "amount": {
                "value":    f"{amount}.00",
                "currency": "RUB",
            },
            "confirmation": {
                "type":       "redirect",
                "return_url": f"https://vk.com/app{os.getenv('VK_APP_ID', '')}",
            },
            "capture":     True,
            "description": f"Тариф {body.plan} × {body.months} мес — {venue.name}",
            "metadata": {
                "payment_id": str(payment.id),
                "venue_id":   str(venue.id),
                "plan":       body.plan,
                "months":     str(body.months),
            },
        }, uuid.uuid4().hex)

        payment.yookassa_id = yk_payment.id
        await db.commit()

        logger.info(
            "Payment #%d created in YooKassa: yk_id=%s venue=%d plan=%s amount=%d",
            payment.id, yk_payment.id, venue.id, body.plan, amount,
        )

        return {
            "status":      "created",
            "payment_id":  payment.id,
            "amount":      amount,
            "plan":        body.plan,
            "months":      body.months,
            "payment_url": yk_payment.confirmation.confirmation_url,
            "sandbox":     False,
        }

    except Exception as e:
        logger.error("YooKassa payment creation failed: %s", e)
        payment.status = "canceled"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Payment creation failed: {str(e)}")


# ─────────────────────────────────────────────
# POST /api/payments/webhook
# ─────────────────────────────────────────────

@router.post("/webhook", summary="Webhook от ЮKassa", include_in_schema=False)
async def payment_webhook(
    request: Request,
    db:      AsyncSession = Depends(get_db),
):
    """
    Обрабатывает callback от ЮKassa.

    При payment.succeeded:
      - Обновляет статус Payment → succeeded
      - Устанавливает venue.plan и venue.plan_expires_at

    Верификация подписи через HMAC-SHA256.
    В sandbox-режиме подпись не проверяется.
    """
    body_bytes = await request.body()

    # Верификация подписи (только в реальном режиме)
    if not SANDBOX_MODE:
        signature = request.headers.get("Content-HMAC")
        if not signature:
            raise HTTPException(status_code=400, detail="Missing signature")

        expected = hmac.new(
            YOOKASSA_SECRET.encode(),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            logger.warning("Invalid webhook signature")
            raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        event = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("event")
    obj        = event.get("object", {})

    logger.info("Webhook received: event=%s yk_id=%s", event_type, obj.get("id"))

    if event_type == "payment.succeeded":
        yk_id    = obj.get("id")
        metadata = obj.get("metadata", {})

        payment_id = metadata.get("payment_id")
        venue_id   = metadata.get("venue_id")
        plan       = metadata.get("plan")
        months     = int(metadata.get("months", 1))

        if not all([payment_id, venue_id, plan]):
            logger.error("Webhook: missing metadata in payment %s", yk_id)
            return {"status": "ok"}

        # Обновляем Payment
        payment = (await db.execute(
            select(Payment).where(Payment.id == int(payment_id))
        )).scalar_one_or_none()

        if payment:
            payment.status       = "succeeded"
            payment.completed_at = datetime.utcnow()

        # Обновляем тариф заведения
        venue = (await db.execute(
            select(Venue).where(Venue.id == int(venue_id))
        )).scalar_one_or_none()

        if venue:
            # Продлеваем от текущей даты окончания или от сейчас
            base = venue.plan_expires_at
            if not base or base < datetime.utcnow():
                base = datetime.utcnow()

            venue.plan            = plan
            venue.plan_expires_at = base + timedelta(days=30 * months)

            # Сбрасываем кэш middleware
            from app.middleware import invalidate_venue_cache
            invalidate_venue_cache(venue.vk_group_id)

            logger.info(
                "Plan updated: venue=%d plan=%s expires=%s",
                venue.id, plan, venue.plan_expires_at,
            )

        await db.commit()

    elif event_type == "payment.canceled":
        yk_id      = obj.get("id")
        payment_id = obj.get("metadata", {}).get("payment_id")
        if payment_id:
            payment = (await db.execute(
                select(Payment).where(Payment.id == int(payment_id))
            )).scalar_one_or_none()
            if payment:
                payment.status = "canceled"
                await db.commit()

        logger.info("Payment canceled: yk_id=%s", yk_id)

    return {"status": "ok"}


# ─────────────────────────────────────────────
# GET /api/payments/history
# ─────────────────────────────────────────────

@router.get("/history", summary="История платежей заведения")
async def payment_history(
    request: Request,
    db:      AsyncSession = Depends(get_db),
):
    """Возвращает историю платежей текущего заведения."""
    venue = require_venue(request)

    payments = (await db.execute(
        select(Payment)
        .where(Payment.venue_id == venue.id)
        .order_by(Payment.created_at.desc())
        .limit(50)
    )).scalars().all()

    return {
        "payments": [
            {
                "id":           p.id,
                "amount":       float(p.amount),
                "plan":         p.plan,
                "months":       p.months,
                "status":       p.status,
                "created_at":   p.created_at.isoformat() if p.created_at else None,
                "completed_at": p.completed_at.isoformat() if p.completed_at else None,
            }
            for p in payments
        ]
    }


# ─────────────────────────────────────────────
# GET /api/payments/sandbox-activate (только для разработки)
# ─────────────────────────────────────────────

@router.post("/sandbox-activate", summary="[DEV] Активировать тариф без оплаты")
async def sandbox_activate(
    request: Request,
    db:      AsyncSession = Depends(get_db),
):
    """
    Только для разработки и тестирования!
    Активирует тариф без реальной оплаты.
    Работает только в sandbox-режиме (ключи ЮKassa не настроены).
    """
    if not SANDBOX_MODE:
        raise HTTPException(status_code=403, detail="Only available in sandbox mode")

    venue = require_venue(request)
    body  = await request.json()
    plan  = body.get("plan", "standard")
    months = int(body.get("months", 1))

    if plan not in PLAN_PRICES:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {plan}")

    venue.plan            = plan
    venue.plan_expires_at = datetime.utcnow() + timedelta(days=30 * months)

    db.add(Payment(
        venue_id    = venue.id,
        yookassa_id = f"sandbox_manual_{uuid.uuid4().hex[:8]}",
        amount      = PLAN_PRICES[plan] * months,
        plan        = plan,
        months      = months,
        status      = "succeeded",
        completed_at = datetime.utcnow(),
    ))
    await db.commit()

    from app.middleware import invalidate_venue_cache
    invalidate_venue_cache(venue.vk_group_id)

    logger.info(
        "SANDBOX: Plan activated for venue %d: plan=%s expires=%s",
        venue.id, plan, venue.plan_expires_at,
    )

    return {
        "status":       "activated",
        "plan":         plan,
        "months":       months,
        "expires_at":   venue.plan_expires_at.isoformat(),
        "sandbox":      True,
    }