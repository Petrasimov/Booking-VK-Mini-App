#!/usr/bin/env python3
"""
test.py — Полная проверка бэкенда Shokoladnitsa
================================================
Тестирует ВСЕ функции приложения:
  1. API эндпоинты (health, metrics, reservation, error-report)
  2. Защита: дубликаты (409), валидация (422), rate limit (429), размер тела (413)
  3. VK Bot — шаблоны сообщений и клавиатуры
  4. Admin — статистика, графики, экспорт CSV
  5. База данных — подключение, модели, счётчики
  6. Pydantic схемы — валидация и нормализация

Требования:
  - FastAPI сервер запущен: cd backend && uvicorn app.main:app --reload --port 8001
  - Виртуальное окружение активно (pip install -r requirements.txt)

Запуск:
  cd backend
  python test.py
"""

import json
import os
import sys
import time
import logging
from datetime import date, timedelta

from dotenv import load_dotenv
load_dotenv()

# Отключаем лишние логи из модулей приложения
logging.disable(logging.CRITICAL)

# ═══════════════════════════════════
# Цвета терминала
# ═══════════════════════════════════
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

BASE_URL = "http://localhost:8001"

# Счётчики результатов
_passed = 0
_failed = 0
_warned = 0
_skipped = 0


def ok(name: str, detail: str = ""):
    global _passed
    _passed += 1
    detail_str = f"  {DIM}{detail}{RESET}" if detail else ""
    print(f"  {GREEN}✅ {name}{RESET}{detail_str}")


def fail(name: str, reason: str = ""):
    global _failed
    _failed += 1
    reason_str = f" — {RED}{reason}{RESET}" if reason else ""
    print(f"  {RED}❌ {name}{reason_str}")


def warn(name: str, reason: str = ""):
    global _warned
    _warned += 1
    reason_str = f" — {YELLOW}{reason}{RESET}" if reason else ""
    print(f"  {YELLOW}⚠️  {name}{reason_str}")


def skip(name: str, reason: str = ""):
    global _skipped
    _skipped += 1
    print(f"  {DIM}⏭  {name} (пропущен: {reason}){RESET}")


def section(title: str):
    print(f"\n{BOLD}{BLUE}{'─' * 52}{RESET}")
    print(f"{BOLD}{BLUE}  {title}{RESET}")
    print(f"{BOLD}{BLUE}{'─' * 52}{RESET}")


def check_server() -> bool:
    """Проверяет доступность FastAPI сервера."""
    try:
        import httpx
        r = httpx.get(f"{BASE_URL}/api/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# ═══════════════════════════════════
# 1. API Эндпоинты
# ═══════════════════════════════════
def test_api_endpoints(server_ok: bool):
    section("1. API Эндпоинты (HTTP запросы)")

    if not server_ok:
        skip("Все API тесты", "сервер недоступен")
        return None

    import httpx

    # ── GET /api/health ──────────────────
    try:
        r = httpx.get(f"{BASE_URL}/api/health", timeout=5)
        data = r.json()
        if r.status_code == 200 and "status" in data:
            ok("GET /api/health → 200", f"status={data['status']}, db={data.get('db')}, pending_tasks={data.get('pending_tasks')}")
            if not data.get("db"):
                warn("  БД недоступна (status=degraded)")
        else:
            fail("GET /api/health", f"status={r.status_code}")
    except Exception as e:
        fail("GET /api/health", str(e))

    # ── GET /api/metrics ─────────────────
    try:
        r = httpx.get(f"{BASE_URL}/api/metrics", timeout=5)
        data = r.json()
        required = ["reservations_total", "reservations_today", "came", "no_show",
                    "errors_24h", "pending_tasks", "uptime_seconds"]
        missing = [k for k in required if k not in data]
        if r.status_code == 200 and not missing:
            ok("GET /api/metrics → 200", f"total={data['reservations_total']}, today={data['reservations_today']}")
        else:
            fail("GET /api/metrics", f"status={r.status_code}, missing={missing}")
    except Exception as e:
        fail("GET /api/metrics", str(e))

    # ── POST /api/reservation (valid) ────
    # Используем дату далеко в будущем, чтобы не было конфликтов
    future_date_1 = (date.today() + timedelta(days=365)).isoformat()
    future_date_2 = (date.today() + timedelta(days=366)).isoformat()
    future_date_3 = (date.today() + timedelta(days=367)).isoformat()
    future_date_4 = (date.today() + timedelta(days=368)).isoformat()

    payload_1 = {
        "name": "Тест Тестов",
        "phone": "79001112233",
        "guests": 2,
        "date": future_date_1,
        "time": "14:00",
        "comment": "Тестовая бронь №1",
        "vk_notifications": False,
    }

    reservation_id = None
    try:
        r = httpx.post(f"{BASE_URL}/api/reservation", json=payload_1, timeout=10)
        if r.status_code == 200:
            data = r.json()
            reservation_id = data.get("id")
            ok("POST /api/reservation (valid) → 200", f"id={reservation_id}, name={data.get('name')}")
        else:
            fail("POST /api/reservation (valid)", f"status={r.status_code}, body={r.text[:200]}")
    except Exception as e:
        fail("POST /api/reservation (valid)", str(e))

    # ── POST /api/reservation (дубликат 409) ──
    try:
        r = httpx.post(f"{BASE_URL}/api/reservation", json=payload_1, timeout=10)
        if r.status_code == 409:
            ok("POST /api/reservation (дубликат) → 409 Conflict")
        else:
            fail("Дубликат (409)", f"ожидалось 409, получено {r.status_code}")
    except Exception as e:
        fail("Дубликат (409)", str(e))

    # ── POST /api/reservation (невалидный 422) ──
    try:
        r = httpx.post(f"{BASE_URL}/api/reservation",
                       json={"name": "Без телефона и даты"}, timeout=5)
        if r.status_code == 422:
            ok("POST /api/reservation (невалидный) → 422 Validation Error")
        else:
            fail("Невалидный payload (422)", f"ожидалось 422, получено {r.status_code}")
    except Exception as e:
        fail("Невалидный payload (422)", str(e))

    # ── POST /api/reservation (3 запроса для rate limit) ──
    # Шлём ещё 2 запроса с другими датами, чтобы счётчик IP дошёл до 3
    payload_2 = {**payload_1, "date": future_date_2, "phone": "79001112234"}
    payload_3 = {**payload_1, "date": future_date_3, "phone": "79001112235"}
    payload_4 = {**payload_1, "date": future_date_4, "phone": "79001112236"}

    try:
        r2 = httpx.post(f"{BASE_URL}/api/reservation", json=payload_2, timeout=10)
        r3 = httpx.post(f"{BASE_URL}/api/reservation", json=payload_3, timeout=10)
        if r2.status_code == 200:
            ok("POST /api/reservation (бронь №2) → 200")
        else:
            warn("Бронь №2", f"status={r2.status_code}")
        if r3.status_code == 200:
            ok("POST /api/reservation (бронь №3) → 200")
        else:
            warn("Бронь №3", f"status={r3.status_code}")

        # Теперь 4й запрос должен получить 429 (per-IP лимит = 3)
        r4 = httpx.post(f"{BASE_URL}/api/reservation", json=payload_4, timeout=10)
        if r4.status_code == 429:
            ok("POST /api/reservation (4й запрос) → 429 Rate Limited")
        else:
            warn("Rate limit (429)", f"ожидалось 429, получено {r4.status_code} (лимит мог не сработать — ожидайте 60с)")
    except Exception as e:
        fail("Rate limit тест", str(e))

    # ── POST /api/reservation (тело > 64KB → 413) ──
    try:
        huge = {"name": "Тест", "phone": "79001234567", "guests": 1,
                "date": future_date_1, "time": "14:00",
                "comment": "x" * 70_000}
        r = httpx.post(f"{BASE_URL}/api/reservation", json=huge, timeout=5)
        if r.status_code == 413:
            ok("POST /api/reservation (64KB+) → 413 Request Too Large")
        else:
            warn("Body size limit (413)", f"ожидалось 413, получено {r.status_code}")
    except Exception as e:
        warn("Body size limit (413)", str(e))

    # ── POST /api/error-report ───────────
    try:
        r = httpx.post(f"{BASE_URL}/api/error-report", json={
            "message": "[TEST] Тестовая ошибка из test.py",
            "details": "Это тестовый отчёт об ошибке. Можно игнорировать.",
            "source": "test"
        }, timeout=5)
        if r.status_code == 200 and r.json().get("status") == "ok":
            ok("POST /api/error-report → 200")
        else:
            fail("POST /api/error-report", f"status={r.status_code}")
    except Exception as e:
        fail("POST /api/error-report", str(e))

    return reservation_id


# ═══════════════════════════════════
# 2. Pydantic схемы
# ═══════════════════════════════════
def test_schemas():
    section("2. Pydantic схемы — валидация")

    try:
        from app.schemas import ReservationCreate, ReservationResponse, ErrorReport
        from pydantic import ValidationError
    except ImportError as e:
        fail("Импорт схем", str(e))
        return

    # ── Нормализация телефона ──
    try:
        r = ReservationCreate(
            name="Иван Иванов",
            phone="+7 (900) 123-45-67",
            guests=2,
            date="2030-12-31",
            time="18:00",
        )
        if r.phone == "79001234567":
            ok("Нормализация телефона: '+7 (900) 123-45-67' → '79001234567'")
        else:
            fail("Нормализация телефона", f"получено '{r.phone}'")
    except ValidationError as e:
        fail("ReservationCreate (valid)", str(e)[:200])

    # ── Имя с допустимыми символами ──
    try:
        r = ReservationCreate(name="Анна-Мария", phone="79001234567",
                               guests=1, date="2030-12-31", time="18:00")
        ok("Имя с дефисом ('Анна-Мария') → допустимо")
    except ValidationError:
        fail("Имя с дефисом должно быть допустимым")

    # ── Имя с цифрами → ошибка ──
    try:
        ReservationCreate(name="Иван123", phone="79001234567",
                          guests=1, date="2030-12-31", time="18:00")
        fail("Имя с цифрами должно вызывать ValidationError")
    except ValidationError:
        ok("Имя 'Иван123' → ValidationError (цифры запрещены)")

    # ── Слишком короткое имя ──
    try:
        ReservationCreate(name="А", phone="79001234567",
                          guests=1, date="2030-12-31", time="18:00")
        fail("Имя из 1 символа должно вызывать ValidationError")
    except ValidationError:
        ok("Имя '1 символ' → ValidationError (минимум 2)")

    # ── Слишком короткий телефон ──
    try:
        ReservationCreate(name="Тест", phone="123",
                          guests=1, date="2030-12-31", time="18:00")
        fail("Телефон 3 цифры должен вызывать ValidationError")
    except ValidationError:
        ok("Телефон '123' → ValidationError (менее 10 цифр)")

    # ── Без телефона ──
    try:
        ReservationCreate(name="Тест", guests=1, date="2030-12-31", time="18:00")
        fail("Без телефона должна быть ValidationError")
    except ValidationError:
        ok("Без телефона → ValidationError (обязательное поле)")

    # ── guests ge=1 ──
    try:
        ReservationCreate(name="Тест", phone="79001234567",
                          guests=0, date="2030-12-31", time="18:00")
        fail("guests=0 должен вызывать ValidationError")
    except ValidationError:
        ok("guests=0 → ValidationError (минимум 1)")

    # ── guests le=20 ──
    try:
        ReservationCreate(name="Тест", phone="79001234567",
                          guests=21, date="2030-12-31", time="18:00")
        fail("guests=21 должен вызывать ValidationError")
    except ValidationError:
        ok("guests=21 → ValidationError (максимум 20)")

    # ── ErrorReport ──
    try:
        e = ErrorReport(message="Test error", details="Details", source="frontend")
        ok("ErrorReport схема → OK", f"source={e.source}")
    except Exception as ex:
        fail("ErrorReport", str(ex))


# ═══════════════════════════════════
# 3. VK Bot — шаблоны сообщений
# ═══════════════════════════════════
def test_vk_templates():
    section("3. VK Bot — шаблоны сообщений")

    try:
        from app.vk_bot import (
            build_confirmation_message,
            build_reminder_message,
            build_feedback_message,
            build_new_reservation_message,
            build_upcoming_reservation_message,
            create_confirmation_keyboard,
        )
    except ImportError as e:
        fail("Импорт vk_bot", str(e))
        return

    # ── build_confirmation_message ──
    msg = build_confirmation_message("Иван", "2026-03-15", "19:00", 3)
    checks = [("имя", "Иван" in msg), ("дата", "2026-03-15" in msg),
              ("время", "19:00" in msg), ("гости", "3" in msg)]
    all_ok = all(v for _, v in checks)
    if all_ok:
        ok("build_confirmation_message", "содержит: имя, дата, время, гости")
    else:
        missing = [k for k, v in checks if not v]
        fail("build_confirmation_message", f"не содержит: {missing}")

    # ── build_reminder_message ──
    msg = build_reminder_message("Мария", "19:00")
    if "Мария" in msg and "19:00" in msg:
        ok("build_reminder_message", "содержит: имя, время")
    else:
        fail("build_reminder_message", f"msg={msg[:100]}")

    # ── build_feedback_message ──
    msg = build_feedback_message("Пётр", "2026-03-15", "19:00")
    if "Пётр" in msg and "2026-03-15" in msg and "19:00" in msg:
        ok("build_feedback_message", "содержит: имя, дата, время")
    else:
        fail("build_feedback_message", f"msg={msg[:100]}")

    # ── build_new_reservation_message ──
    msg = build_new_reservation_message("Анна", 4, "79001111111", "2026-03-20", "18:00", 42)
    if "Анна" in msg and "79001111111" in msg and "42" in msg and "4" in msg:
        ok("build_new_reservation_message", "содержит: имя, телефон, гости, ID")
    else:
        fail("build_new_reservation_message", f"msg={msg[:150]}")

    # ── build_upcoming_reservation_message ──
    msg = build_upcoming_reservation_message("Сергей", 2, "79002222222", "20:00", 55)
    if "Сергей" in msg and "55" in msg:
        ok("build_upcoming_reservation_message", "содержит: имя, ID")
    else:
        fail("build_upcoming_reservation_message", f"msg={msg[:150]}")

    # ── create_confirmation_keyboard ──
    keyboard = create_confirmation_keyboard(42)
    flat_buttons = [b for row in keyboard.get("buttons", []) for b in row]
    labels = [b["action"]["label"] for b in flat_buttons]
    colors = [b.get("color") for b in flat_buttons]

    if "Пришёл" in labels and "Не пришёл" in labels:
        ok("create_confirmation_keyboard", "кнопки 'Пришёл' и 'Не пришёл' присутствуют")
    else:
        fail("create_confirmation_keyboard", f"labels={labels}")

    if "positive" in colors and "negative" in colors:
        ok("Цвета кнопок", "positive (зелёный) / negative (красный)")
    else:
        warn("Цвета кнопок", f"colors={colors}")

    # Проверка payload кнопок
    for btn in flat_buttons:
        try:
            payload = json.loads(btn["action"]["payload"])
            if payload.get("reservation_id") == 42 and payload.get("action"):
                ok(f"  Payload '{btn['action']['label']}'",
                   f"action={payload['action']}, reservation_id={payload['reservation_id']}")
            else:
                fail(f"  Payload '{btn['action']['label']}'", str(payload))
        except Exception as e:
            fail(f"  Payload '{btn['action']['label']}'", str(e))

    # ── inline=True проверка ──
    if keyboard.get("inline") is True:
        ok("Keyboard inline=True")
    else:
        fail("Keyboard inline", f"inline={keyboard.get('inline')}")


# ═══════════════════════════════════
# 4. Admin — статистика
# ═══════════════════════════════════
def test_admin_stats():
    section("4. Admin — статистика")

    try:
        from app.admin.stats import (
            get_stats, bookings_per_day, guests_per_day,
            came_vs_no_show, popular_times
        )
    except ImportError as e:
        fail("Импорт admin.stats", str(e))
        return

    # ── get_stats ──
    try:
        stats = get_stats()
        required = ["total", "total_guests", "came", "no_show", "avg_guests"]
        missing = [k for k in required if k not in stats]
        if not missing:
            ok("get_stats()", f"total={stats['total']}, came={stats['came']}, "
               f"no_show={stats['no_show']}, avg_guests={stats['avg_guests']:.2f}")
        else:
            fail("get_stats()", f"отсутствуют поля: {missing}")
    except Exception as e:
        fail("get_stats()", str(e))

    # ── bookings_per_day ──
    try:
        rows = bookings_per_day(days=30)
        ok("bookings_per_day(30)", f"{len(rows)} точек данных за 30 дней")
    except Exception as e:
        fail("bookings_per_day()", str(e))

    # ── guests_per_day ──
    try:
        today = date.today()
        data = guests_per_day(today.year, today.month)
        if "dates" in data and "guests" in data:
            ok("guests_per_day()", f"{len(data['dates'])} дней в текущем месяце")
        else:
            fail("guests_per_day()", f"неверный формат: {list(data.keys())}")
    except Exception as e:
        fail("guests_per_day()", str(e))

    # ── came_vs_no_show ──
    try:
        data = came_vs_no_show()
        if "came" in data and "no_show" in data:
            ok("came_vs_no_show()", f"came={data['came']}, no_show={data['no_show']}")
        else:
            fail("came_vs_no_show()", str(data))
    except Exception as e:
        fail("came_vs_no_show()", str(e))

    # ── popular_times ──
    try:
        data = popular_times()
        if "time" in data and "count" in data:
            ok("popular_times()", f"{len(data['time'])} временных слотов")
        else:
            fail("popular_times()", str(data))
    except Exception as e:
        fail("popular_times()", str(e))


# ═══════════════════════════════════
# 5. Admin — графики
# ═══════════════════════════════════
def test_admin_charts():
    section("5. Admin — генерация графиков")

    try:
        from app.admin.charts import (
            bookings_chart, chart_guests_per_day,
            chart_came_vs_no_show, chart_popular_time
        )
    except ImportError as e:
        fail("Импорт admin.charts", str(e))
        return

    charts = [
        ("bookings_chart()",        bookings_chart,        "Брони по дням"),
        ("chart_guests_per_day()",  chart_guests_per_day,  "Гости по дням"),
        ("chart_came_vs_no_show()", chart_came_vs_no_show, "Пришли vs Не пришли"),
        ("chart_popular_time()",    chart_popular_time,    "Популярное время"),
    ]

    for name, func, label in charts:
        try:
            path = func()
            if os.path.exists(path):
                size = os.path.getsize(path)
                ok(name, f"PNG сохранён: {os.path.basename(path)} ({size:,} bytes)")
            else:
                fail(name, "файл не создан")
        except Exception as e:
            fail(name, str(e))


# ═══════════════════════════════════
# 6. Admin — экспорт CSV
# ═══════════════════════════════════
def test_admin_export():
    section("6. Admin — экспорт CSV")

    try:
        from app.admin.export import export_reservations_csv
    except ImportError as e:
        fail("Импорт admin.export", str(e))
        return

    try:
        path = export_reservations_csv()
        if not os.path.exists(path):
            fail("export_reservations_csv()", "файл не создан")
            return

        size = os.path.getsize(path)
        ok("export_reservations_csv()", f"CSV сохранён: {size:,} bytes")

        # Проверяем заголовок
        with open(path, encoding="utf-8") as f:
            header = f.readline().strip()
            row_count = sum(1 for _ in f)

        expected_cols = ["ID", "Имя", "Гостей", "Телефон", "Дата", "Время"]
        missing_cols = [col for col in expected_cols if col not in header]
        if not missing_cols:
            ok("CSV заголовок", f"все колонки присутствуют: {header[:60]}...")
        else:
            warn("CSV заголовок", f"отсутствуют колонки: {missing_cols}")

        ok("Строки данных в CSV", f"{row_count} бронирований")

    except Exception as e:
        fail("export_reservations_csv()", str(e))


# ═══════════════════════════════════
# 7. База данных
# ═══════════════════════════════════
def test_database():
    section("7. База данных — модели и подключение")

    try:
        from app.database import SessionLocal
        from app.models import Reservation, ScheduledTask, ErrorLog, RateLimitEntry
        from sqlalchemy import text
    except ImportError as e:
        fail("Импорт database/models", str(e))
        return

    db = SessionLocal()
    try:
        # ── Подключение ──
        db.execute(text("SELECT 1"))
        ok("Подключение к БД", "SELECT 1 → OK")

        # ── Счётчики таблиц ──
        total     = db.query(Reservation).count()
        tasks     = db.query(ScheduledTask).count()
        pending   = db.query(ScheduledTask).filter(ScheduledTask.completed == False).count()
        errors    = db.query(ErrorLog).count()
        rate_ips  = db.query(RateLimitEntry).count()

        ok("Таблица reservations",    f"{total} записей")
        ok("Таблица scheduled_task",  f"{tasks} записей, pending={pending}")
        ok("Таблица error_log",       f"{errors} записей")
        ok("Таблица rate_limit",      f"{rate_ips} IP-записей")

        # ── Последняя бронь ──
        last = db.query(Reservation).order_by(Reservation.id.desc()).first()
        if last:
            ok("Последняя бронь",
               f"#{last.id} — {last.name}, {last.date}, {last.time}, {last.guests} гостей")
        else:
            warn("Таблица reservations пуста", "нет данных для проверки")

    except Exception as e:
        fail("БД ошибка", str(e))
    finally:
        db.close()


# ═══════════════════════════════════
# 8. VK Bot — конфигурация
# ═══════════════════════════════════
def test_vk_config():
    section("8. VK Bot — конфигурация (.env)")

    required_vars = {
        "VK_COMMUNITY_TOKEN": "токен сообщества",
        "VK_GROUP_ID":        "ID группы",
        "VK_ADMIN_ID":        "VK ID администратора",
        "VK_WAITERS_CHAT_ID": "peer_id чата официантов",
        "CAFE_ADDRESS":       "адрес кафе",
    }

    db_vars = {
        "DB_USER":     "пользователь PostgreSQL",
        "DB_PASSWORD": "пароль PostgreSQL",
        "DB_NAME":     "имя базы данных",
        "DB_HOST":     "хост PostgreSQL",
    }

    for var, desc in required_vars.items():
        val = os.getenv(var, "")
        if val:
            # Показываем первые 8 символов
            preview = val[:8] + "…" if len(val) > 8 else val
            ok(f"{var}", f"{desc}: {preview}")
        else:
            fail(f"{var} не задан", f"VK-бот не отправит {desc}")

    print()
    for var, desc in db_vars.items():
        val = os.getenv(var, "")
        if val:
            preview = val[:8] + "…" if len(val) > 8 else val
            ok(f"{var}", f"{desc}: {preview}")
        else:
            warn(f"{var} не задан", desc)


# ═══════════════════════════════════
# 9. Scheduler — логика задач
# ═══════════════════════════════════
def test_scheduler():
    section("9. Scheduler — типы задач")

    try:
        from app.scheduler import execute_task, process_pending_tasks
        from app.models import ScheduledTask, Reservation
        ok("Импорт scheduler", "execute_task, process_pending_tasks")
    except ImportError as e:
        fail("Импорт scheduler", str(e))
        return

    # Проверяем что все типы задач обрабатываются
    known_types = ["visit_confirmation", "reminder", "feedback"]
    try:
        import inspect
        source = inspect.getsource(execute_task)
        for task_type in known_types:
            if task_type in source:
                ok(f"task_type='{task_type}'", "обрабатывается в execute_task()")
            else:
                fail(f"task_type='{task_type}'", "не найден в execute_task()")
    except Exception as e:
        warn("Проверка типов задач", str(e))

    # Количество pending задач из БД
    try:
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            pending = db.query(ScheduledTask).filter(ScheduledTask.completed == False).count()
            ok("Pending tasks в БД", f"{pending} задач ожидает выполнения")
        finally:
            db.close()
    except Exception as e:
        warn("Pending tasks", str(e))


# ═══════════════════════════════════
# MAIN
# ═══════════════════════════════════
def main():
    print(f"\n{BOLD}{'═' * 52}")
    print("  ТЕСТ БЭКЕНДА — Shokoladnitsa")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═' * 52}{RESET}\n")

    # Проверяем доступность сервера
    print(f"{BOLD}Проверка FastAPI сервера на {BASE_URL}...{RESET}")
    server_ok = check_server()
    if server_ok:
        print(f"  {GREEN}Сервер доступен{RESET}\n")
    else:
        print(f"  {RED}Сервер недоступен{RESET}")
        print(f"  {YELLOW}Запустите: cd backend && uvicorn app.main:app --reload --port 8001{RESET}\n")

    # Запускаем все тесты
    test_api_endpoints(server_ok)
    test_schemas()
    test_vk_templates()
    test_admin_stats()
    test_admin_charts()
    test_admin_export()
    test_database()
    test_vk_config()
    test_scheduler()

    # ── Итог ──────────────────────────────
    total = _passed + _failed + _warned + _skipped
    print(f"\n{BOLD}{'═' * 52}")
    print(f"  ИТОГО: {total} проверок")
    print(f"  {GREEN}✅  Прошло:         {_passed}{RESET}")
    if _failed:
        print(f"  {RED}❌  Провалено:       {_failed}{RESET}")
    if _warned:
        print(f"  {YELLOW}⚠️   Предупреждений: {_warned}{RESET}")
    if _skipped:
        print(f"  {DIM}⏭   Пропущено:      {_skipped}{RESET}")
    print(f"{BOLD}{'═' * 52}{RESET}\n")

    if _failed:
        print(f"{RED}Некоторые тесты провалились. Проверьте вывод выше.{RESET}\n")
        sys.exit(1)
    else:
        print(f"{GREEN}Все тесты прошли успешно!{RESET}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
