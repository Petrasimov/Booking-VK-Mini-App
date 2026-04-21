"""
FastAPI-приложение для системы бронирования столиков.

Эндпоинты:
  POST /api/reservation   — создание бронирования
  POST /api/error-report  — приём отчётов об ошибках с фронтенда
  GET  /api/health        — проверка работоспособности сервиса
  GET  /api/metrics       — метрики приложения
  GET  /api/metrics/prometheus — Prometheus-метрики (RPS, latency)

Защита:
  - Rate limiting: 3 запроса в минуту на IP (в PostgreSQL — не сбрасывается при рестарте)
  - Глобальный лимит: 60 запросов в минуту суммарно (in-memory)
  - Валидация входных данных через Pydantic
  - CORS ограничен доверенными источниками
  - Content Security Policy и security-заголовки
  - Лимит размера тела запроса (64 КБ)
  - Защита от дублирующих броней (один телефон + одна дата)

БД:
  Все FastAPI-эндпоинты используют AsyncSession (asyncpg) для неблокирующих вызовов.
  Планировщик и VK-бот используют синхронный SessionLocal (psycopg2) в отдельных процессах.
"""

from dotenv import load_dotenv
load_dotenv()

import logging
import os
import traceback
from datetime import datetime, timedelta, time as datetime_time, date as DateType

import sentry_sdk
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text, select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send

from app.schemas import ReservationCreate, ReservationResponse, ErrorReport
from app.database import SessionLocal, engine, Base, AsyncSessionLocal
from app.models import Reservation, ScheduledTask, ErrorLog, RateLimitEntry
from app.vk_bot import (
    send_vk_message,
    build_confirmation_message,
    send_waiters_new_reservation,
    send_admin_notification,
)

logger = logging.getLogger(__name__)

# Время старта приложения — используется в /api/health и /api/metrics
APP_START_TIME = datetime.utcnow()

# --- Создание таблиц в БД при старте (синхронно, только один раз) ---
try:
    Base.metadata.create_all(bind=engine)
except Exception as _db_init_err:
    logger.warning("Could not create DB tables at startup: %s", _db_init_err)

# --- Sentry (опционально — работает только при наличии SENTRY_DSN в .env) ---
SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=os.getenv("APP_ENV", "production"),
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
    )
    logger.info("Sentry initialized (environment=%s)", os.getenv("APP_ENV", "production"))

app = FastAPI(
    title="Shokoladnitsa Booking API",
    description="API для системы бронирования столиков кафе Shokoladnitsa (VK Mini App)",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# --- Prometheus метрики — GET /api/metrics/prometheus ---
Instrumentator().instrument(app).expose(app, endpoint="/api/metrics/prometheus")


# ===============================
# Middleware: заголовки безопасности (pure ASGI — без BaseHTTPMiddleware)
# ===============================
_CSP = (
    "default-src 'none'; "
    "script-src 'self' https://vk.com; "
    "style-src 'self' 'unsafe-inline' https://vk.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https://api.vk.com https://vk.com "
    "https://*.ngrok-free.app https://*.loca.lt; "
    "frame-src https://vk.com; "
    "font-src 'self' data:;"
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_api = scope.get("path", "").startswith("/api/")

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start" and is_api:
                headers = MutableHeaders(scope=message)
                headers["Content-Security-Policy"] = _CSP
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "SAMEORIGIN"
                headers["X-XSS-Protection"] = "1; mode=block"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            await send(message)

        await self.app(scope, receive, send_with_headers)


# ===============================
# Middleware: лимит размера тела запроса (pure ASGI)
# ===============================
MAX_BODY_SIZE = 64 * 1024  # 64 КБ


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length and int(content_length) > MAX_BODY_SIZE:
            response = JSONResponse(status_code=413, content={"detail": "Request too large"})
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)

# --- CORS: разрешены только доверенные источники ---
# В .env добавьте CORS_ORIGIN=https://ваш-домен.ru для production
_cors_extra = [o.strip() for o in os.getenv("CORS_ORIGIN", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://localhost:5173",
        *_cors_extra,
    ],
    allow_origin_regex=(
        r"https://("
        r".*\.ngrok-free\.dev"
        r"|.*\.loca\.lt"
        r"|.*\.trycloudflare\.com"
        r"|.*\.devtunnels\.ms"
        r")"
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ===============================
# Dependency: async сессия БД
# ===============================
async def get_db():
    """Создаёт AsyncSession на время запроса, закрывает после."""
    async with AsyncSessionLocal() as db:
        yield db


# ===============================
# Rate Limiting
# ===============================
RATE_LIMIT_PER_IP = 3    # Макс. запросов с одного IP за окно
RATE_LIMIT_GLOBAL = 60   # Макс. запросов суммарно за окно
RATE_WINDOW = 60          # Окно в секундах

# Глобальный лимит — in-memory (достаточно для общей защиты от DDoS)
_global_log: list[float] = []


async def check_rate_limit(request: Request, db: AsyncSession):
    """
    Проверяет лимиты запросов.

    Лимит на IP хранится в PostgreSQL — сохраняется между перезапусками сервера.
    Глобальный лимит хранится в памяти.
    Бросает HTTPException 429 при превышении.
    """
    client_ip = request.client.host
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=RATE_WINDOW)

    # Удаляем устаревшие записи (старше 2 окон) для экономии места в БД
    await db.execute(
        delete(RateLimitEntry).where(
            RateLimitEntry.ip == client_ip,
            RateLimitEntry.window_start < now - timedelta(seconds=RATE_WINDOW * 2),
        )
    )

    # Ищем запись для IP в текущем окне
    result = await db.execute(
        select(RateLimitEntry).where(
            RateLimitEntry.ip == client_ip,
            RateLimitEntry.window_start >= window_start,
        )
    )
    entry = result.scalar_one_or_none()

    if entry:
        if entry.count >= RATE_LIMIT_PER_IP:
            logger.warning(
                "Rate limit exceeded for IP %s (%d requests)", client_ip, entry.count
            )
            raise HTTPException(status_code=429, detail="Too many requests")
        entry.count += 1
    else:
        db.add(RateLimitEntry(ip=client_ip, window_start=now, count=1))

    await db.commit()

    # Глобальный лимит
    global _global_log
    now_ts = now.timestamp()
    _global_log = [t for t in _global_log if now_ts - t < RATE_WINDOW]

    if len(_global_log) >= RATE_LIMIT_GLOBAL:
        logger.warning("Global rate limit exceeded (%d requests)", len(_global_log))
        raise HTTPException(status_code=429, detail="Server is busy")

    _global_log.append(now_ts)


# ===============================
# Глобальный обработчик ошибок
# ===============================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Ловит все необработанные ошибки.
    Логирует, сохраняет в БД, отправляет админу в VK.
    Использует синхронную сессию (аварийный путь — не зависит от async engine).
    """
    error_text = f"{type(exc).__name__}: {exc}"
    stack = traceback.format_exc()

    logger.error(
        "Unhandled error on %s %s: %s\n%s",
        request.method, request.url.path, error_text, stack,
    )

    try:
        db = SessionLocal()
        db.add(ErrorLog(source="backend", level="error", message=error_text, details=stack))
        db.commit()
        db.close()
    except Exception as db_err:
        logger.error("Failed to save error to DB: %s", db_err)

    try:
        path = str(request.url.path)[:100]
        admin_msg = f"BACKEND ERROR\n\n{request.method} {path}\n{error_text[:400]}"
        await send_admin_notification(admin_msg)
    except Exception:
        pass

    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ===============================
# POST /api/reservation — создание бронирования
# ===============================
@app.post(
    "/api/reservation",
    response_model=ReservationResponse,
    summary="Создать бронирование",
    description=(
        "Создаёт новое бронирование столика.\n\n"
        "Шаги обработки:\n"
        "1. Проверяет rate limit (3 req/min на IP в PostgreSQL + 60 req/min глобально in-memory)\n"
        "2. Проверяет дубликат: тот же номер телефона на ту же дату → 409 Conflict\n"
        "3. Сохраняет запись в БД\n"
        "4. Уведомляет официантов в VK-чат\n"
        "5. Создаёт отложенные задачи: напоминание за час, фидбек на следующий день\n"
        "6. Если гость разрешил уведомления — отправляет подтверждение в VK ЛС"
    ),
    tags=["Бронирование"],
    responses={
        409: {"description": "Дублирующее бронирование (тот же телефон + та же дата)"},
        429: {"description": "Превышен rate limit"},
        413: {"description": "Тело запроса больше 64 КБ"},
    },
)
async def create_reservation(
    reservation: ReservationCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await check_rate_limit(request, db)

    # --- Проверка дубликата ---
    # phone уже нормализован (только цифры) валидатором Pydantic
    result = await db.execute(
        select(Reservation).where(
            Reservation.phone == reservation.phone,
            Reservation.date == reservation.date,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        logger.warning(
            "Duplicate booking attempt: phone=%s date=%s", reservation.phone, reservation.date
        )
        raise HTTPException(
            status_code=409,
            detail="Бронирование на этот день с таким телефоном уже существует",
        )

    logger.info(
        "New reservation: %s, %d guests, %s %s",
        reservation.name, reservation.guests, reservation.date, reservation.time,
    )

    # --- Сохраняем бронирование ---
    new_reservation = Reservation(**reservation.model_dump())
    db.add(new_reservation)
    await db.commit()
    await db.refresh(new_reservation)

    logger.info("Reservation #%d created", new_reservation.id)

    # --- Уведомляем официантов ---
    try:
        await send_waiters_new_reservation(
            name=reservation.name,
            guests=reservation.guests,
            phone=reservation.phone,
            date=str(reservation.date),
            time=reservation.time,
            reservation_id=new_reservation.id,
            comment=reservation.comment or "",
        )
        logger.info("Waiters notified about reservation #%d", new_reservation.id)
    except Exception as e:
        logger.error("Failed to notify waiters: %s", e)

    # --- Отложенные задачи ---
    visit_datetime = datetime.combine(new_reservation.date, new_reservation.time)

    # Запрос подтверждения прихода — в момент визита
    db.add(ScheduledTask(
        reservation_id=new_reservation.id,
        task_type="visit_confirmation",
        scheduled_at=visit_datetime,
    ))

    # Задачи для гостя (только если разрешил уведомления)
    if new_reservation.vk_user_id and new_reservation.vk_notifications:

        # Подтверждение бронирования — сразу в ЛС
        try:
            confirmation_msg = build_confirmation_message(
                name=new_reservation.name,
                date=str(new_reservation.date),
                time=new_reservation.time.strftime("%H:%M"),
                guests=new_reservation.guests,
            )
            await send_vk_message(new_reservation.vk_user_id, confirmation_msg)
            logger.info("Confirmation sent to VK user %d", new_reservation.vk_user_id)
        except Exception as e:
            logger.error(
                "Failed to send confirmation to VK user %d: %s", new_reservation.vk_user_id, e
            )

        # Напоминание за 1 час до визита
        reminder_time = visit_datetime - timedelta(hours=1)
        if reminder_time > datetime.now():
            db.add(ScheduledTask(
                reservation_id=new_reservation.id,
                task_type="reminder",
                scheduled_at=reminder_time,
            ))

        # Обратная связь — следующий день в 12:00
        feedback_time = datetime.combine(
            new_reservation.date + timedelta(days=1),
            datetime_time(12, 0),
        )
        db.add(ScheduledTask(
            reservation_id=new_reservation.id,
            task_type="feedback",
            scheduled_at=feedback_time,
        ))

    await db.commit()
    logger.info("Scheduled tasks created for reservation #%d", new_reservation.id)

    return new_reservation


# ===============================
# POST /api/error-report — приём ошибок с фронтенда
# ===============================
@app.post(
    "/api/error-report",
    summary="Отправить отчёт об ошибке",
    description=(
        "Принимает отчёт об ошибке с фронтенда (VK Mini App).\n\n"
        "Сохраняет запись в таблицу `error_log` и отправляет уведомление "
        "администратору в VK ЛС."
    ),
    tags=["Мониторинг"],
    responses={
        200: {"description": "Отчёт принят", "content": {"application/json": {"example": {"status": "ok"}}}},
    },
)
async def report_error(report: ErrorReport, db: AsyncSession = Depends(get_db)):
    logger.error("Frontend error: %s | %s", report.message, report.details or "no details")

    db.add(ErrorLog(
        source=report.source,
        level="error",
        message=report.message,
        details=report.details,
    ))
    await db.commit()

    try:
        admin_msg = f"FRONTEND ERROR\n\n{report.message}"
        if report.details:
            admin_msg += f"\n\n{report.details[:500]}"
        await send_admin_notification(admin_msg)
    except Exception:
        pass

    return {"status": "ok"}


# ===============================
# GET /api/health — проверка работоспособности
# ===============================
@app.get(
    "/api/health",
    summary="Проверка работоспособности",
    description=(
        "Возвращает текущий статус сервиса.\n\n"
        "Поля ответа:\n"
        "- `status` — `ok` если БД доступна, иначе `degraded`\n"
        "- `db` — результат пинга базы данных (`SELECT 1`)\n"
        "- `pending_tasks` — количество невыполненных задач планировщика\n"
        "- `uptime_seconds` — время работы приложения в секундах"
    ),
    tags=["Мониторинг"],
)
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.error("Health check DB error: %s", e)
        db_ok = False

    pending_tasks = (
        await db.execute(
            select(func.count()).select_from(ScheduledTask).where(ScheduledTask.completed == False)
        )
    ).scalar()
    uptime = int((datetime.utcnow() - APP_START_TIME).total_seconds())

    return {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "pending_tasks": pending_tasks,
        "uptime_seconds": uptime,
    }


# ===============================
# GET /api/metrics — метрики приложения
# ===============================
@app.get(
    "/api/metrics",
    summary="Метрики приложения",
    description=(
        "Возвращает агрегированные метрики для мониторинга дашборда.\n\n"
        "Поля ответа:\n"
        "- `reservations_total` — всего бронирований в БД\n"
        "- `reservations_today` — бронирований на сегодняшний день\n"
        "- `came` — гостей, отмеченных как пришедшие\n"
        "- `no_show` — гостей, отмеченных как не пришедшие\n"
        "- `errors_24h` — ошибок за последние 24 часа\n"
        "- `pending_tasks` — невыполненных задач планировщика\n"
        "- `uptime_seconds` — время работы приложения в секундах"
    ),
    tags=["Мониторинг"],
)
async def get_metrics(db: AsyncSession = Depends(get_db)):
    today = DateType.today()
    yesterday = datetime.utcnow() - timedelta(hours=24)

    total = (await db.execute(select(func.count()).select_from(Reservation))).scalar()
    today_count = (await db.execute(
        select(func.count()).select_from(Reservation).where(Reservation.date == today)
    )).scalar()
    came = (await db.execute(
        select(func.count()).select_from(Reservation).where(Reservation.appeared == True)
    )).scalar()
    no_show = (await db.execute(
        select(func.count()).select_from(Reservation).where(Reservation.appeared == False)
    )).scalar()
    errors = (await db.execute(
        select(func.count()).select_from(ErrorLog).where(ErrorLog.created_at >= yesterday)
    )).scalar()
    pending = (await db.execute(
        select(func.count()).select_from(ScheduledTask).where(ScheduledTask.completed == False)
    )).scalar()
    uptime = int((datetime.utcnow() - APP_START_TIME).total_seconds())

    return {
        "reservations_total": total,
        "reservations_today": today_count,
        "came": came,
        "no_show": no_show,
        "errors_24h": errors,
        "pending_tasks": pending,
        "uptime_seconds": uptime,
    }
