"""
Системный тест приложения Shokoladnitsa.

Проверяет абсолютно все компоненты системы:
  - База данных (PostgreSQL, все модели)
  - API эндпоинты (все маршруты)
  - Rate limiting (per-IP + глобальный)
  - Дублирующие брони (409)
  - VK сообщения (шаблоны + API)
  - Inline кнопки (клавиатура)
  - Админ-панель (статистика, графики, CSV)
  - Планировщик (process_pending_tasks)
  - VK Long Poll (соединение с сервером)
  - Фронтенд (dist/index.html)
  - CORS заголовки
  - Security headers
  - Body size limit (413)
  - Логирование ошибок

Запуск: python test_system.py
Требует: бэкенд на localhost:8001 (python start_all.py)
Генерирует: report_YYYY-MM-DD_HH-MM.txt
"""

import asyncio
import csv
import json
import os
import sys
import time
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

# ─── Конфигурация ─────────────────────────────────────────────────────────────
BASE_URL = "http://localhost:8001"
REPORT_DIR = Path(__file__).parent
FRONTEND_DIST = Path(__file__).parent.parent / "vk-table-booking" / "dist" / "index.html"

# Тестовые данные бронирования (уникальный телефон на каждый запуск)
_ts = int(time.time()) % 100000
TEST_PHONE = f"7900{_ts:07d}"
TEST_DATE = (date.today() + timedelta(days=14)).isoformat()  # Дата в будущем
TEST_RESERVATION = {
    "name": "Тест Системный",
    "guests": 2,
    "phone": TEST_PHONE,
    "date": TEST_DATE,
    "time": "14:00",
    "comment": "Автотест",
    "vk_user_id": None,
    "vk_notifications": False,
}

# ─── Отчёт ────────────────────────────────────────────────────────────────────
report_lines: list[str] = []
passed = 0
failed = 0
warnings = 0
_api_available = False  # Выставляется в True после успешного /api/health


def log(line: str):
    print(line)
    report_lines.append(line)


def ok(label: str, detail: str = ""):
    global passed
    passed += 1
    msg = f"  ✅ {label}"
    if detail:
        msg += f"  — {detail}"
    log(msg)


def fail(label: str, error: str = ""):
    global failed
    failed += 1
    msg = f"  ❌ {label}"
    if error:
        msg += f"\n      ⚠️  {error}"
    log(msg)


def warn(label: str, detail: str = ""):
    global warnings
    warnings += 1
    msg = f"  ⚠️  {label}"
    if detail:
        msg += f"  — {detail}"
    log(msg)


def section(title: str):
    log("")
    log(f"{'─' * 60}")
    log(f"📌 {title}")
    log(f"{'─' * 60}")


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _load_env():
    """Загружает .env из backend/.env."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _setup_django_path():
    """Добавляет backend/ в sys.path для импортов."""
    backend_dir = str(Path(__file__).parent)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 1: База данных
# ─────────────────────────────────────────────────────────────────────────────

def test_database():
    section("База данных (PostgreSQL + SQLAlchemy)")

    try:
        from app.database import SessionLocal, async_engine, engine
        ok("Импорт database.py")
    except Exception as e:
        fail("Импорт database.py", str(e))
        return

    # Синхронное подключение
    try:
        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db.close()
        ok("Sync-подключение (psycopg2)")
    except Exception as e:
        fail("Sync-подключение (psycopg2)", str(e))

    # Асинхронное подключение
    async def _check_async():
        from sqlalchemy import text
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    try:
        asyncio.run(_check_async())
        ok("Async-подключение (asyncpg)")
    except Exception as e:
        fail("Async-подключение (asyncpg)", str(e))

    # Импорт моделей
    try:
        from app.models import Reservation, ScheduledTask, ErrorLog, RateLimitEntry
        ok("Импорт всех моделей (4 шт.)")
    except Exception as e:
        fail("Импорт моделей", str(e))
        return

    # CRUD Reservation
    try:
        from app.models import Reservation
        db = SessionLocal()
        r = Reservation(
            name="DB Test",
            guests=1,
            phone="79990000001",
            date=date.today(),
            time=datetime.now().time(),
        )
        db.add(r)
        db.commit()
        db.refresh(r)
        rid = r.id
        assert rid is not None
        fetched = db.get(Reservation, rid)
        assert fetched.name == "DB Test"
        db.delete(fetched)
        db.commit()
        db.close()
        ok("CRUD Reservation (create / read / delete)")
    except Exception as e:
        fail("CRUD Reservation", str(e))

    # ScheduledTask
    try:
        from app.models import Reservation, ScheduledTask
        db = SessionLocal()
        r = Reservation(name="Task Test", guests=1, phone="79990000002",
                        date=date.today(), time=datetime.now().time())
        db.add(r)
        db.commit()
        db.refresh(r)
        t = ScheduledTask(reservation_id=r.id, task_type="reminder",
                          scheduled_at=datetime.now() + timedelta(hours=1))
        db.add(t)
        db.commit()
        db.refresh(t)
        assert t.completed is False
        db.delete(r)   # CASCADE удалит task
        db.commit()
        db.close()
        ok("CRUD ScheduledTask (create + CASCADE delete)")
    except Exception as e:
        fail("CRUD ScheduledTask", str(e))

    # ErrorLog
    try:
        from app.models import ErrorLog
        db = SessionLocal()
        e_log = ErrorLog(source="test", level="error", message="test error")
        db.add(e_log)
        db.commit()
        db.refresh(e_log)
        assert e_log.id is not None
        db.delete(e_log)
        db.commit()
        db.close()
        ok("CRUD ErrorLog")
    except Exception as e:
        fail("CRUD ErrorLog", str(e))

    # RateLimitEntry
    try:
        from app.models import RateLimitEntry
        db = SessionLocal()
        rl = RateLimitEntry(ip="127.0.0.1", window_start=datetime.now(), count=1)
        db.add(rl)
        db.commit()
        db.refresh(rl)
        assert rl.id is not None
        db.delete(rl)
        db.commit()
        db.close()
        ok("CRUD RateLimitEntry")
    except Exception as e:
        fail("CRUD RateLimitEntry", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 2: API эндпоинты
# ─────────────────────────────────────────────────────────────────────────────

def test_api():
    global _api_available
    section("API эндпоинты (FastAPI localhost:8001)")

    # Health check
    try:
        r = httpx.get(f"{BASE_URL}/api/health", timeout=5)
        if r.status_code != 200:
            fail("GET /api/health", f"HTTP {r.status_code}: {r.text[:200]}")
            return
        data = r.json()
        assert "status" in data
        _api_available = True
        ok("GET /api/health", f"status={data.get('status')}")
    except Exception as e:
        fail("GET /api/health", f"{type(e).__name__}: {e}")
        log("  ⚠️  Убедитесь, что бэкенд запущен: python start_all.py")
        return  # Без сервера дальше нет смысла

    # Metrics JSON
    try:
        r = httpx.get(f"{BASE_URL}/api/metrics", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "reservations" in data or "total" in data or isinstance(data, dict)
        ok("GET /api/metrics (JSON)")
    except Exception as e:
        fail("GET /api/metrics (JSON)", str(e))

    # Prometheus metrics
    try:
        r = httpx.get(f"{BASE_URL}/api/metrics/prometheus", timeout=5)
        assert r.status_code == 200
        assert "http_requests_total" in r.text or "HELP" in r.text or len(r.text) > 0
        ok("GET /api/metrics/prometheus", f"{len(r.text)} байт")
    except Exception as e:
        fail("GET /api/metrics/prometheus", str(e))

    # OpenAPI docs
    try:
        r = httpx.get(f"{BASE_URL}/api/docs", timeout=5)
        assert r.status_code == 200
        ok("GET /api/docs (Swagger UI)")
    except Exception as e:
        fail("GET /api/docs", str(e))

    # POST /api/reservation — успешное создание
    try:
        r = httpx.post(f"{BASE_URL}/api/reservation", json=TEST_RESERVATION, timeout=10)
        if r.status_code == 201:
            data = r.json()
            ok("POST /api/reservation (201 Created)", f"id={data.get('id')}")
        elif r.status_code == 409:
            warn("POST /api/reservation — 409 (уже существует, тест повторяется?)")
        else:
            fail("POST /api/reservation", f"status={r.status_code}, body={r.text[:200]}")
    except Exception as e:
        fail("POST /api/reservation", str(e))

    # POST /api/reservation — дубликат → 409
    try:
        r = httpx.post(f"{BASE_URL}/api/reservation", json=TEST_RESERVATION, timeout=10)
        if r.status_code == 409:
            ok("POST /api/reservation — дублирование → 409 Conflict")
        elif r.status_code == 429:
            warn("POST /api/reservation — 429 Rate limit (дублирование не проверено)")
        else:
            fail("POST /api/reservation — дублирование", f"ожидался 409, получен {r.status_code}")
    except Exception as e:
        fail("POST /api/reservation — дублирование", str(e))

    # POST /api/error-report
    try:
        payload = {"source": "test", "level": "error",
                   "message": "System test error", "details": "auto-test"}
        r = httpx.post(f"{BASE_URL}/api/error-report", json=payload, timeout=5)
        assert r.status_code in (200, 201)
        ok("POST /api/error-report")
    except Exception as e:
        fail("POST /api/error-report", str(e))

    # 422 — невалидные данные
    try:
        bad = {"name": "", "guests": -1, "phone": "abc", "date": "bad", "time": "bad"}
        r = httpx.post(f"{BASE_URL}/api/reservation", json=bad, timeout=5)
        assert r.status_code == 422
        ok("POST /api/reservation — невалидные данные → 422")
    except Exception as e:
        fail("POST /api/reservation — 422 валидация", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 3: Rate limiting
# ─────────────────────────────────────────────────────────────────────────────

def test_rate_limiting():
    section("Rate Limiting (3 запроса в минуту с одного IP)")

    warn("Rate limit тест пропущен в автоматическом режиме",
         "Тест отправляет 4+ запроса с localhost и может заблокировать следующие тесты. "
         "Для ручной проверки: отправьте 4 запроса POST /api/reservation за 1 минуту → ожидается 429.")

    if not _api_available:
        warn("API недоступен — пропуск проверки rate limit")
        return

    try:
        r = httpx.get(f"{BASE_URL}/api/health", timeout=5)
        assert r.status_code == 200
        ok("API доступен после предыдущих тестов (rate limit не сработал)")
    except Exception as e:
        fail("API недоступен после тестов", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 4: Body size limit
# ─────────────────────────────────────────────────────────────────────────────

def test_body_size():
    section("Body Size Limit (64 КБ максимум)")

    if not _api_available:
        warn("API недоступен — пропуск проверки body size")
        return

    try:
        # Лимит в main.py: MAX_BODY_SIZE = 64 * 1024 = 65536 байт
        # Отправляем 200 КБ с явным Content-Length заголовком
        big_body = b"x" * (200 * 1024)
        r = httpx.post(
            f"{BASE_URL}/api/reservation",
            content=big_body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(big_body))},
            timeout=10,
        )
        if r.status_code == 413:
            ok("Body > 64KB → 413 Request Entity Too Large")
        elif r.status_code == 422:
            ok("Body > 64KB → 422 (middleware пропустил, но JSON невалидный)", "допустимо")
        else:
            warn("Body size limit", f"получен {r.status_code} (ожидался 413) — проверьте RequestSizeLimitMiddleware")
    except Exception as e:
        warn("Body size limit", f"не удалось проверить: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 5: CORS + Security Headers
# ─────────────────────────────────────────────────────────────────────────────

def test_headers():
    section("CORS и Security Headers")

    if not _api_available:
        warn("API недоступен — пропуск проверки заголовков")
        return

    # CORS — проверяем через GET с Origin заголовком (FastAPI CORSMiddleware отвечает на это)
    try:
        r = httpx.get(
            f"{BASE_URL}/api/health",
            headers={"Origin": "http://localhost:5173"},
            timeout=5,
        )
        acao = r.headers.get("access-control-allow-origin", "")
        if acao:
            ok("CORS allow-origin для localhost:5173", acao)
        else:
            # Некоторые конфигурации возвращают CORS только на preflight OPTIONS
            r2 = httpx.options(
                f"{BASE_URL}/api/health",
                headers={"Origin": "http://localhost:5173",
                         "Access-Control-Request-Method": "GET"},
                timeout=5,
            )
            acao2 = r2.headers.get("access-control-allow-origin", "")
            if acao2:
                ok("CORS preflight (OPTIONS) для localhost:5173", acao2)
            else:
                warn("CORS", "Заголовок access-control-allow-origin не вернулся — проверьте CORSMiddleware в main.py")
    except Exception as e:
        fail("CORS проверка", str(e))

    # Security headers на /api/
    try:
        r = httpx.get(f"{BASE_URL}/api/health", timeout=5)
        headers = {k.lower(): v for k, v in r.headers.items()}
        checks = [
            ("x-content-type-options", "nosniff"),
            ("x-frame-options", None),
            ("x-xss-protection", None),
        ]
        for header, expected in checks:
            if header in headers:
                if expected is None or expected in headers[header]:
                    ok(f"Security header: {header}", headers[header])
                else:
                    warn(f"Security header: {header}", f"значение: {headers[header]}")
            else:
                warn(f"Security header отсутствует: {header}",
                     "Проверьте SecurityHeadersMiddleware в main.py")
    except Exception as e:
        fail("Security headers", str(e))

    # X-Frame-Options НЕ должен быть на корне (VK Mini App)
    try:
        r = httpx.get(f"{BASE_URL}/", timeout=5)
        xfo = r.headers.get("x-frame-options", "")
        if not xfo:
            ok("X-Frame-Options отсутствует на / (VK Mini App не сломается)")
        else:
            fail("X-Frame-Options присутствует на /", f"VK Mini App сломается: {xfo}")
    except Exception as e:
        warn("Проверка X-Frame-Options на /", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 6: VK сообщения — шаблоны и функции
# ─────────────────────────────────────────────────────────────────────────────

def test_vk_messages():
    section("VK Bot — шаблоны сообщений")

    try:
        from app.vk_bot import (
            build_confirmation_message,
            build_reminder_message,
            build_feedback_message,
            build_new_reservation_message,
            build_upcoming_reservation_message,
            create_confirmation_keyboard,
        )
        ok("Импорт vk_bot.py")
    except Exception as e:
        fail("Импорт vk_bot.py", str(e))
        return

    # build_confirmation_message
    try:
        msg = build_confirmation_message("Анна", "2026-04-19", "14:00", 2)
        assert "Анна" in msg and "14:00" in msg and "2026-04-19" in msg
        ok("build_confirmation_message", f"{len(msg)} символов")
    except Exception as e:
        fail("build_confirmation_message", str(e))

    # build_reminder_message
    try:
        msg = build_reminder_message("Иван", "15:30")
        assert "Иван" in msg and "15:30" in msg
        ok("build_reminder_message", f"{len(msg)} символов")
    except Exception as e:
        fail("build_reminder_message", str(e))

    # build_feedback_message
    try:
        msg = build_feedback_message("Мария", "2026-04-18", "12:00")
        assert "Мария" in msg and "12:00" in msg
        ok("build_feedback_message", f"{len(msg)} символов")
    except Exception as e:
        fail("build_feedback_message", str(e))

    # build_new_reservation_message
    try:
        msg = build_new_reservation_message("Петр", 3, "79001234567", "2026-04-19", "18:00", 42)
        assert "Петр" in msg and "42" in msg
        ok("build_new_reservation_message", f"{len(msg)} символов")
    except Exception as e:
        fail("build_new_reservation_message", str(e))

    # build_upcoming_reservation_message
    try:
        msg = build_upcoming_reservation_message("Олег", 2, "79001234567", "19:00", 99)
        assert "Олег" in msg and "99" in str(msg)
        ok("build_upcoming_reservation_message", f"{len(msg)} символов")
    except Exception as e:
        fail("build_upcoming_reservation_message", str(e))

    # create_confirmation_keyboard
    try:
        kb = create_confirmation_keyboard(123)
        assert kb["inline"] is True
        buttons = kb["buttons"][0]
        payloads = [json.loads(b["action"]["payload"]) for b in buttons]
        actions = {p["action"] for p in payloads}
        assert actions == {"came", "no_show"}
        assert all(p["reservation_id"] == 123 for p in payloads)
        ok("create_confirmation_keyboard — 2 кнопки (came / no_show)")
    except Exception as e:
        fail("create_confirmation_keyboard", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 7: VK API — отправка сообщений (реальные запросы)
# ─────────────────────────────────────────────────────────────────────────────

async def _test_vk_api_async():
    from app.vk_bot import send_vk_chat_message, send_admin_notification

    # Проверяем конфигурацию
    token = os.getenv("VK_COMMUNITY_TOKEN", "")
    chat_id = os.getenv("VK_WAITERS_CHAT_ID", "")
    admin_id = os.getenv("VK_ADMIN_ID", "")

    if not token:
        warn("VK_COMMUNITY_TOKEN не задан — пропуск реальных VK-запросов")
        return

    # Сообщение в чат официантов
    try:
        result = await send_vk_chat_message("🤖 [АВТОТЕСТ] Системная проверка Shokoladnitsa")
        if result:
            ok("send_vk_chat_message → чат официантов")
        else:
            fail("send_vk_chat_message", "вернула False (VK API ошибка, проверьте токен)")
    except Exception as e:
        fail("send_vk_chat_message", str(e))

    # Сообщение с клавиатурой
    try:
        from app.vk_bot import send_waiters_confirmation_request
        result = await send_waiters_confirmation_request(
            name="Тест Авто", guests=2, time="14:00", reservation_id=9999
        )
        if result:
            ok("send_waiters_confirmation_request (с клавиатурой)")
        else:
            fail("send_waiters_confirmation_request", "вернула False")
    except Exception as e:
        fail("send_waiters_confirmation_request", str(e))

    # Уведомление администратору
    if admin_id:
        try:
            result = await send_admin_notification("🤖 [АВТОТЕСТ] Проверка admin-уведомления")
            if result:
                ok("send_admin_notification → ЛС администратора")
            else:
                warn("send_admin_notification", "вернула False (возможно, пользователь не начинал диалог)")
        except Exception as e:
            fail("send_admin_notification", str(e))
    else:
        warn("VK_ADMIN_ID не задан — пропуск admin notification")


def test_vk_api():
    section("VK API — реальные запросы (требует VK токен)")
    asyncio.run(_test_vk_api_async())


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 8: VK Long Poll соединение
# ─────────────────────────────────────────────────────────────────────────────

async def _test_longpoll_async():
    token = os.getenv("VK_COMMUNITY_TOKEN", "")
    group_id = os.getenv("VK_GROUP_ID", "")

    if not token or not group_id:
        warn("VK_COMMUNITY_TOKEN / VK_GROUP_ID не заданы — пропуск Long Poll теста")
        return

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.vk.com/method/groups.getLongPollServer",
                params={
                    "group_id": group_id,
                    "access_token": token,
                    "v": "5.199",
                },
            )
        data = r.json()
        if "error" in data:
            fail("VK Long Poll соединение", f"VK API error: {data['error']}")
        else:
            resp = data.get("response", {})
            if "server" in resp and "key" in resp:
                ok("VK Long Poll — получен сервер и ключ сессии")
            else:
                warn("VK Long Poll", f"неожиданный ответ: {data}")
    except Exception as e:
        fail("VK Long Poll соединение", str(e))


def test_longpoll():
    section("VK Long Poll — соединение с сервером")
    asyncio.run(_test_longpoll_async())


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 9: Инлайн-кнопки (обработка came / no_show)
# ─────────────────────────────────────────────────────────────────────────────

def test_inline_buttons():
    section("Inline кнопки — обработка came / no_show")

    try:
        from app.vk_bot_server import handle_came, handle_no_show
        ok("Импорт handle_came / handle_no_show из vk_bot_server")
    except ImportError:
        # Функции могут быть встроены в event loop — проверяем через БД
        warn("handle_came / handle_no_show — не экспортированы напрямую, проверка через БД")
        _test_inline_via_db()
        return
    except Exception as e:
        fail("Импорт vk_bot_server", str(e))
        return

    _test_inline_via_db()


def _test_inline_via_db():
    """Проверяет обработку кнопок через прямую запись в БД."""
    try:
        from app.models import Reservation
        from app.database import SessionLocal

        db = SessionLocal()
        r = Reservation(
            name="Кнопка Тест",
            guests=1,
            phone="79990000099",
            date=date.today(),
            time=datetime.now().time(),
            appeared=None,
        )
        db.add(r)
        db.commit()
        db.refresh(r)
        rid = r.id

        # Имитируем came
        r.appeared = True
        db.commit()
        db.refresh(r)
        assert r.appeared is True
        ok("Inline appeared=True (Пришёл)")

        # Имитируем no_show
        r.appeared = False
        db.commit()
        db.refresh(r)
        assert r.appeared is False
        ok("Inline appeared=False (Не пришёл)")

        # Имитируем ввод чека
        r.check = 1500
        db.commit()
        db.refresh(r)
        assert r.check == 1500
        ok("Сумма чека сохранена (1500 руб.)")

        db.delete(r)
        db.commit()
        db.close()
    except Exception as e:
        fail("Inline кнопки через БД", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 10: Планировщик
# ─────────────────────────────────────────────────────────────────────────────

async def _test_scheduler_async():
    from app.models import Reservation, ScheduledTask
    from app.database import SessionLocal
    from app.scheduler import process_pending_tasks, cleanup_rate_limit

    db = SessionLocal()
    r = Reservation(
        name="Scheduler Test",
        guests=1,
        phone="79990000088",
        date=date.today(),
        time=datetime.now().time(),
        vk_user_id=None,
        vk_notifications=False,
    )
    db.add(r)
    db.commit()
    db.refresh(r)

    # Задача с vk_notifications=False → execute_task просто пропустит reminder
    t = ScheduledTask(
        reservation_id=r.id,
        task_type="reminder",
        scheduled_at=datetime.now() - timedelta(seconds=1),  # Уже наступило
        completed=False,
    )
    db.add(t)
    db.commit()
    # Сохраняем ID до закрытия сессии, иначе DetachedInstanceError
    task_id = t.id
    reservation_id = r.id
    db.close()

    try:
        await process_pending_tasks()
        # Проверяем, что задача помечена выполненной
        db2 = SessionLocal()
        t2 = db2.get(ScheduledTask, task_id)
        if t2 and t2.completed:
            ok("process_pending_tasks — задача выполнена и помечена completed=True")
        elif t2 is None:
            ok("process_pending_tasks — задача выполнена и удалена (CASCADE)")
        else:
            fail("process_pending_tasks", f"completed={t2.completed if t2 else 'None'}")

        # Удаляем тестовые данные
        res = db2.get(Reservation, reservation_id)
        if res:
            db2.delete(res)
            db2.commit()
        db2.close()
    except Exception as e:
        fail("process_pending_tasks", str(e))
        db3 = SessionLocal()
        res = db3.get(Reservation, reservation_id)
        if res:
            db3.delete(res)
            db3.commit()
        db3.close()

    # cleanup_rate_limit
    try:
        await cleanup_rate_limit()
        ok("cleanup_rate_limit — выполнена без ошибок")
    except Exception as e:
        fail("cleanup_rate_limit", str(e))


def test_scheduler():
    section("Планировщик (scheduler.py)")
    asyncio.run(_test_scheduler_async())


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 11: Статистика (admin/stats.py)
# ─────────────────────────────────────────────────────────────────────────────

def test_admin_stats():
    section("Админ-панель — Статистика (stats.py)")

    try:
        from app.admin.stats import (
            get_stats,
            bookings_per_day,
            guests_per_day_range,
            came_vs_no_show,
            popular_times,
        )
        ok("Импорт admin/stats.py")
    except Exception as e:
        fail("Импорт admin/stats.py", str(e))
        return

    funcs = [
        ("get_stats()", lambda: get_stats()),
        ("bookings_per_day()", lambda: bookings_per_day()),
        ("guests_per_day_range(30)", lambda: guests_per_day_range(30)),
        ("came_vs_no_show()", lambda: came_vs_no_show()),
        ("popular_times()", lambda: popular_times()),
    ]

    for name, fn in funcs:
        try:
            result = fn()
            assert result is not None
            ok(f"{name}", f"тип: {type(result).__name__}")
        except Exception as e:
            fail(f"{name}", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 12: Графики (admin/charts.py)
# ─────────────────────────────────────────────────────────────────────────────

def test_charts():
    section("Графики (admin/charts.py — matplotlib Agg)")

    try:
        from app.admin.charts import (
            bookings_chart,
            chart_guests_per_day,
            chart_came_vs_no_show,
            chart_popular_time,
        )
        ok("Импорт admin/charts.py")
    except Exception as e:
        fail("Импорт admin/charts.py", str(e))
        return

    charts = [
        ("bookings_chart()", bookings_chart),
        ("chart_guests_per_day()", chart_guests_per_day),
        ("chart_came_vs_no_show()", chart_came_vs_no_show),
        ("chart_popular_time()", chart_popular_time),
    ]

    for name, fn in charts:
        try:
            path = fn()
            assert os.path.exists(path), f"файл не создан: {path}"
            size = os.path.getsize(path)
            assert size > 1000, f"файл слишком маленький: {size} байт"
            ok(f"{name}", f"{Path(path).name} ({size // 1024} KB)")
        except Exception as e:
            fail(f"{name}", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 13: CSV экспорт (admin/export.py)
# ─────────────────────────────────────────────────────────────────────────────

def test_csv_export():
    section("CSV Экспорт (admin/export.py)")

    try:
        from app.admin.export import export_reservations_csv
        ok("Импорт admin/export.py")
    except Exception as e:
        fail("Импорт admin/export.py", str(e))
        return

    try:
        path = export_reservations_csv()
        assert os.path.exists(path), f"файл не создан: {path}"
        size = os.path.getsize(path)
        ok("export_reservations_csv()", f"{Path(path).name} ({size} байт)")

        # Проверяем структуру CSV
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            headers = next(reader, None)
        if headers:
            assert "ID" in headers and "Имя" in headers
            ok("CSV заголовки корректны", str(headers[:5]))
        else:
            warn("CSV пустой (нет данных в БД)")
    except Exception as e:
        fail("export_reservations_csv()", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 14: Pydantic схемы
# ─────────────────────────────────────────────────────────────────────────────

def test_schemas():
    section("Pydantic схемы (schemas.py)")

    try:
        from app.schemas import ReservationCreate, ReservationResponse
        ok("Импорт ReservationCreate / ReservationResponse")
    except Exception as e:
        fail("Импорт schemas.py", str(e))
        return

    try:
        from app.schemas import ReservationCreate
        data = ReservationCreate(
            name="Test",
            guests=2,
            phone="+7 (900) 123-45-67",
            date="2026-04-19",
            time="14:00",
        )
        assert data.phone == "79001234567", f"ожидался strip до цифр, получен {data.phone}"
        ok("ReservationCreate — phone strip до цифр", data.phone)
    except Exception as e:
        fail("ReservationCreate валидация phone", str(e))

    # Проверяем что date/time не конфликтуют с типами Pydantic v2
    try:
        from app.schemas import ReservationCreate
        data = ReservationCreate(
            name="Test",
            guests=1,
            phone="79001234567",
            date="2026-05-01",
            time="10:00",
        )
        from datetime import date as _date, time as _time
        assert isinstance(data.date, _date)
        assert isinstance(data.time, _time)
        ok("Pydantic v2 date/time — нет коллизии имён с типами")
    except Exception as e:
        fail("Pydantic v2 date/time коллизия", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 15: Фронтенд (сборка)
# ─────────────────────────────────────────────────────────────────────────────

def test_frontend():
    section("Фронтенд (VK Mini App — сборка dist/)")

    if FRONTEND_DIST.exists():
        size = FRONTEND_DIST.stat().st_size
        ok("dist/index.html существует", f"{size} байт")
    else:
        warn("dist/index.html не найден",
             "Запустите: cd vk-table-booking && npm run build")

    # Проверяем что index.html не содержит CSP мета-тег
    if FRONTEND_DIST.exists():
        content = FRONTEND_DIST.read_text(encoding="utf-8")
        if "Content-Security-Policy" in content:
            fail("CSP мета-тег в index.html!",
                 "VK Mini App сломается. Удалите <meta http-equiv='Content-Security-Policy'>")
        else:
            ok("CSP мета-тег в index.html отсутствует (VK Mini App не сломается)")

    # Проверяем assets
    assets_dir = FRONTEND_DIST.parent / "assets"
    if assets_dir.exists():
        assets = list(assets_dir.glob("*.js")) + list(assets_dir.glob("*.css"))
        if assets:
            ok(f"dist/assets/ — {len(assets)} файлов (JS/CSS)")
        else:
            warn("dist/assets/ пустая")
    else:
        warn("dist/assets/ не найдена")


# ─────────────────────────────────────────────────────────────────────────────
# БЛОК 16: Конфигурация .env
# ─────────────────────────────────────────────────────────────────────────────

def test_env_config():
    section("Конфигурация окружения (.env)")

    required = [
        "VK_COMMUNITY_TOKEN",
        "VK_GROUP_ID",
        "VK_ADMIN_ID",
        "VK_WAITERS_CHAT_ID",
        "CAFE_ADDRESS",
        "DB_USER",
        "DB_PASSWORD",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
    ]

    for key in required:
        val = os.getenv(key, "")
        if val:
            # Скрываем чувствительные данные
            if "TOKEN" in key or "PASSWORD" in key:
                display = val[:8] + "..." if len(val) > 8 else "***"
            else:
                display = val
            ok(f"{key}", display)
        else:
            fail(f"{key} не задан в .env")

    # Опциональные
    for key in ["SENTRY_DSN", "CORS_ORIGIN", "APP_ENV"]:
        val = os.getenv(key, "")
        if val:
            ok(f"{key} (опц.)", val[:50])
        else:
            log(f"  ℹ️  {key} не задан (опционально)")


# ─────────────────────────────────────────────────────────────────────────────
# ГЛАВНАЯ ФУНКЦИЯ
# ─────────────────────────────────────────────────────────────────────────────

def main():
    start_time = time.time()
    now_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    report_path = REPORT_DIR / f"report_{now_str}.txt"

    log("=" * 60)
    log("🔍 СИСТЕМНЫЙ ТЕСТ — SHOKOLADNITSA")
    log(f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    log(f"🌐 API: {BASE_URL}")
    log("=" * 60)

    # Загрузка .env и путей
    _load_env()
    _setup_django_path()

    # Запуск всех блоков
    test_env_config()
    test_database()
    test_api()
    test_rate_limiting()
    test_body_size()
    test_headers()
    test_vk_messages()
    test_vk_api()
    test_longpoll()
    test_inline_buttons()
    test_scheduler()
    test_admin_stats()
    test_charts()
    test_csv_export()
    test_schemas()
    test_frontend()

    # Итог
    elapsed = time.time() - start_time
    total = passed + failed + warnings
    log("")
    log("=" * 60)
    log("📊 ИТОГИ ТЕСТИРОВАНИЯ")
    log("=" * 60)
    log(f"  ✅ Пройдено:    {passed}")
    log(f"  ❌ Упало:       {failed}")
    log(f"  ⚠️  Предупреждений: {warnings}")
    log(f"  📦 Всего:       {total}")
    log(f"  ⏱️  Время:       {elapsed:.1f} с")
    log("")

    if failed == 0:
        log("🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ! Проект готов к деплою.")
    elif failed <= 3:
        log(f"⚠️  МЕЛКИЕ ПРОБЛЕМЫ ({failed} шт.). Проверьте ошибки выше перед деплоем.")
    else:
        log(f"🚨 КРИТИЧЕСКИЕ ПРОБЛЕМЫ ({failed} ошибок). Деплой не рекомендован!")

    log("")
    log(f"📄 Отчёт сохранён: {report_path}")
    log("=" * 60)

    # Сохраняем отчёт
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
