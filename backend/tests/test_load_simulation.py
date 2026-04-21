"""
Async load simulation — замер производительности без запущенного сервера.

Использует asyncio + httpx.AsyncClient против реального сервера на localhost:8001.
Если сервер недоступен — тест пропускается (pytest.skip).

Запуск как pytest-тест:
    pytest tests/test_load_simulation.py -v -s

Запуск как standalone-скрипт (выводит отчёт в stdout):
    python tests/test_load_simulation.py

Метрики:
    - p50, p90, p99 латентности в миллисекундах
    - RPS (requests per second)
    - Error rate (%)
    - Потребление памяти до/после (через tracemalloc или psutil)

Константы для выбора размера сервера:
    SERVER_SIZING_GUIDE — руководство по интерпретации результатов.
"""

from __future__ import annotations

import asyncio
import random
import statistics
import sys
import time
import tracemalloc
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Руководство по выбору сервера на основе результатов нагрузочного теста
# ---------------------------------------------------------------------------

SERVER_SIZING_GUIDE = """
=========================================
 РУКОВОДСТВО ПО ВЫБОРУ СЕРВЕРА
=========================================

Интерпретация результатов (50 одновременных запросов):

  p99 < 200 ms  -> 1 vCPU / 512 MB RAM достаточно для < 100 одновременных пользователей
  p99 < 500 ms  -> 1 vCPU / 1 GB RAM для ~200 одновременных пользователей
  p99 > 500 ms  -> 2 vCPU / 2 GB RAM рекомендуется

Дополнительные компоненты:
  PostgreSQL:    +200 MB RAM (отдельный процесс или managed DB)
  VK Long Poll:  +50 MB RAM  (процесс vk_bot_server.py)
  Scheduler:     +30 MB RAM  (процесс scheduler.py)

Запас:
  Добавьте 20% к расчётным цифрам для ОС и прочих процессов.

Пример: p99=150ms, 50 concurrent -> минимум 1 vCPU / 512 MB API + 200 MB PG = ~750 MB итого.
Рекомендация: сервер 1 vCPU / 1 GB (с запасом).

RPS ориентиры (на основе теста):
  < 10 RPS   -> узкое место, проверьте индексы БД и N+1 запросы
  10–50 RPS  -> норма для MVP с одним воркером (uvicorn --workers 1)
  > 50 RPS   -> добавьте --workers 2-4 (по числу vCPU) или gunicorn
=========================================
"""

# ---------------------------------------------------------------------------
# Конфигурация теста
# ---------------------------------------------------------------------------

BASE_URL = "http://localhost:8001"
CONCURRENT_USERS = 50       # одновременных POST /api/reservation
SEQUENTIAL_REQUESTS = 100   # последовательных GET /api/health
CONNECT_TIMEOUT = 5.0       # секунды ожидания подключения
REQUEST_TIMEOUT = 10.0      # секунды ожидания ответа

TODAY = date.today()

TIMES = ["12:00", "13:00", "14:00", "15:00", "18:00", "19:00", "20:00"]

FIRST_NAMES = [
    "Александр", "Мария", "Дмитрий", "Анна", "Сергей",
    "Екатерина", "Алексей", "Наталья", "Андрей", "Ольга",
]


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def make_unique_payload(index: int) -> dict:
    """
    Генерирует payload с уникальным телефоном и датой.

    index используется как seed уникальности, чтобы исключить 409 Conflict.
    vk_notifications=False — не тригерит VK API-вызовы на сервере.
    """
    # Уникальный телефон: 9 + 9 цифр, используем index как часть номера
    phone = f"9{(200_000_000 + index):09d}"
    # Уникальная дата из диапазона [+1, +30] — циклически по индексу
    date_offset = (index % 30) + 1
    visit_date = (TODAY + timedelta(days=date_offset)).isoformat()
    name = f"{random.choice(FIRST_NAMES)} Нагрузка"

    return {
        "name": name,
        "guests": random.randint(1, 6),
        "phone": phone,
        "date": visit_date,
        "time": random.choice(TIMES),
        "comment": None,
        "vk_user_id": None,
        "vk_notifications": False,
    }


def percentile(data: list[float], p: float) -> float:
    """Возвращает p-й процентиль списка (0 < p <= 100)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    index = (p / 100) * (len(sorted_data) - 1)
    lower = int(index)
    upper = min(lower + 1, len(sorted_data) - 1)
    frac = index - lower
    return sorted_data[lower] + frac * (sorted_data[upper] - sorted_data[lower])


def format_report(
    endpoint: str,
    concurrency: str,
    total: int,
    latencies_ms: list[float],
    errors: int,
    total_time_s: float,
    mem_before_mb: float,
    mem_after_mb: float,
) -> str:
    """Форматирует отчёт в виде ASCII-таблицы."""
    rps = total / total_time_s if total_time_s > 0 else 0
    error_pct = (errors / total * 100) if total > 0 else 0

    p50 = percentile(latencies_ms, 50)
    p90 = percentile(latencies_ms, 90)
    p99 = percentile(latencies_ms, 99)
    p_max = max(latencies_ms) if latencies_ms else 0
    mean = statistics.mean(latencies_ms) if latencies_ms else 0

    delta_mb = mem_after_mb - mem_before_mb
    delta_sign = "+" if delta_mb >= 0 else ""

    return f"""
=========================================
PERFORMANCE REPORT — Shokoladnitsa API
=========================================
Endpoint:         {endpoint}
Concurrent users: {concurrency}
Total requests:   {total}

Latency (ms):
  mean: {mean:>7.1f} ms
  p50:  {p50:>7.1f} ms
  p90:  {p90:>7.1f} ms
  p99:  {p99:>7.1f} ms
  max:  {p_max:>7.1f} ms

Throughput:
  RPS:  {rps:>7.1f} req/sec
  Time: {total_time_s:>7.2f} s total

Errors: {errors} / {total} ({error_pct:.1f}%)

Memory:
  Before: {mem_before_mb:>6.1f} MB
  After:  {mem_after_mb:>6.1f} MB
  Delta:  {delta_sign}{delta_mb:.1f} MB
=========================================
{_size_recommendation(p99)}"""


def _size_recommendation(p99_ms: float) -> str:
    """Возвращает рекомендацию по размеру сервера на основе p99."""
    if p99_ms < 200:
        return "Sizing: 1 vCPU / 512 MB RAM достаточно для < 100 concurrent users"
    elif p99_ms < 500:
        return "Sizing: 1 vCPU / 1 GB RAM для ~200 concurrent users"
    else:
        return "Sizing: 2 vCPU / 2 GB RAM рекомендуется (p99 > 500 ms)"


def get_memory_mb() -> float:
    """
    Возвращает текущее потребление памяти процессом в МБ.

    Использует psutil если доступен, иначе tracemalloc.
    """
    try:
        import psutil
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)
    except ImportError:
        # Фолбэк: tracemalloc (только heap Python, не RSS)
        if not tracemalloc.is_tracing():
            tracemalloc.start()
        snapshot = tracemalloc.take_snapshot()
        total_bytes = sum(stat.size for stat in snapshot.statistics("lineno"))
        return total_bytes / (1024 * 1024)


# ---------------------------------------------------------------------------
# Основные тест-функции
# ---------------------------------------------------------------------------

async def _check_server_available() -> bool:
    """Проверяет доступность сервера. Возвращает True если сервер отвечает."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/api/health")
            return response.status_code < 600  # сервер жив при любом HTTP-ответе
    except Exception:
        return False


async def run_concurrent_reservations(n: int = CONCURRENT_USERS) -> dict:
    """
    Запускает n одновременных POST /api/reservation.

    Возвращает словарь с латентностями, ошибками и временем выполнения.
    """
    import httpx

    tracemalloc.start()
    mem_before = get_memory_mb()

    payloads = [make_unique_payload(i) for i in range(n)]
    latencies: list[float] = []
    errors = 0

    async def single_request(client: httpx.AsyncClient, idx: int) -> None:
        nonlocal errors
        start = time.perf_counter()
        try:
            response = await client.post(
                f"{BASE_URL}/api/reservation",
                json=payloads[idx],
                timeout=REQUEST_TIMEOUT,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

            # 200 — успех; 409/429 — ожидаемые при нагрузке, не считаем ошибкой
            if response.status_code not in (200, 409, 429):
                errors += 1
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)
            errors += 1

    wall_start = time.perf_counter()
    async with httpx.AsyncClient() as client:
        tasks = [single_request(client, i) for i in range(n)]
        await asyncio.gather(*tasks)
    wall_time = time.perf_counter() - wall_start

    mem_after = get_memory_mb()
    tracemalloc.stop()

    return {
        "latencies_ms": latencies,
        "errors": errors,
        "total": n,
        "wall_time_s": wall_time,
        "mem_before_mb": mem_before,
        "mem_after_mb": mem_after,
    }


async def run_sequential_health(n: int = SEQUENTIAL_REQUESTS) -> dict:
    """
    Запускает n последовательных GET /api/health.

    Последовательные запросы показывают базовую латентность без конкуренции.
    """
    import httpx

    mem_before = get_memory_mb()
    latencies: list[float] = []
    errors = 0

    wall_start = time.perf_counter()
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for _ in range(n):
            start = time.perf_counter()
            try:
                response = await client.get(f"{BASE_URL}/api/health")
                elapsed_ms = (time.perf_counter() - start) * 1000
                latencies.append(elapsed_ms)
                if response.status_code != 200:
                    errors += 1
            except Exception:
                elapsed_ms = (time.perf_counter() - start) * 1000
                latencies.append(elapsed_ms)
                errors += 1
    wall_time = time.perf_counter() - wall_start

    mem_after = get_memory_mb()

    return {
        "latencies_ms": latencies,
        "errors": errors,
        "total": n,
        "wall_time_s": wall_time,
        "mem_before_mb": mem_before,
        "mem_after_mb": mem_after,
    }


# ---------------------------------------------------------------------------
# pytest-тесты
# ---------------------------------------------------------------------------

def test_concurrent_reservation_performance():
    """
    50 одновременных POST /api/reservation против реального сервера.

    Пропускается если сервер недоступен.
    Мягкое assertions: тест падает только если p99 > 5000 ms (явная деградация).
    """
    import pytest

    available = asyncio.run(_check_server_available())
    if not available:
        pytest.skip(
            f"Server not running at {BASE_URL}. "
            "Start with: python -m uvicorn app.main:app --port 8001"
        )

    result = asyncio.run(run_concurrent_reservations(CONCURRENT_USERS))

    report = format_report(
        endpoint="POST /api/reservation",
        concurrency=f"{CONCURRENT_USERS} (concurrent)",
        total=result["total"],
        latencies_ms=result["latencies_ms"],
        errors=result["errors"],
        total_time_s=result["wall_time_s"],
        mem_before_mb=result["mem_before_mb"],
        mem_after_mb=result["mem_after_mb"],
    )
    print(report)
    print(SERVER_SIZING_GUIDE)

    # Жёсткое ограничение: p99 не должен превышать 5 секунд
    # (если превышает — сервер явно перегружен или завис)
    p99 = percentile(result["latencies_ms"], 99)
    assert p99 < 5000, (
        f"p99 latency {p99:.0f}ms превысил порог 5000ms. "
        "Проверьте нагрузку на PostgreSQL и количество воркеров uvicorn."
    )

    # Error rate не должен превышать 20%
    # (409/429 не считаются ошибками, см. single_request)
    error_rate = result["errors"] / result["total"]
    assert error_rate < 0.20, (
        f"Error rate {error_rate:.1%} превысил 20%. "
        "Проверьте логи сервера."
    )


def test_sequential_health_performance():
    """
    100 последовательных GET /api/health против реального сервера.

    Пропускается если сервер недоступен.
    """
    import pytest

    available = asyncio.run(_check_server_available())
    if not available:
        pytest.skip(
            f"Server not running at {BASE_URL}. "
            "Start with: python -m uvicorn app.main:app --port 8001"
        )

    result = asyncio.run(run_sequential_health(SEQUENTIAL_REQUESTS))

    report = format_report(
        endpoint="GET /api/health",
        concurrency="1 (sequential)",
        total=result["total"],
        latencies_ms=result["latencies_ms"],
        errors=result["errors"],
        total_time_s=result["wall_time_s"],
        mem_before_mb=result["mem_before_mb"],
        mem_after_mb=result["mem_after_mb"],
    )
    print(report)

    # Health check должен отвечать быстро даже последовательно
    p99 = percentile(result["latencies_ms"], 99)
    assert p99 < 1000, (
        f"Health check p99 {p99:.0f}ms > 1000ms. "
        "SELECT 1 не должен занимать больше секунды."
    )

    assert result["errors"] == 0, (
        f"{result['errors']} ошибок в health check. Сервер деградировал?"
    )


# ---------------------------------------------------------------------------
# Standalone-запуск: python tests/test_load_simulation.py
# ---------------------------------------------------------------------------

async def _main():
    """Точка входа при запуске как скрипта."""
    print("Checking server availability...")
    available = await _check_server_available()
    if not available:
        print(f"ERROR: Server not available at {BASE_URL}")
        print("Start with: python -m uvicorn app.main:app --port 8001")
        sys.exit(1)

    print(f"Server is up. Running load simulation...\n")

    # --- Тест 1: 50 concurrent POST /api/reservation ---
    print(f"[1/2] Running {CONCURRENT_USERS} concurrent POST /api/reservation...")
    result1 = await run_concurrent_reservations(CONCURRENT_USERS)
    report1 = format_report(
        endpoint="POST /api/reservation",
        concurrency=f"{CONCURRENT_USERS} (concurrent)",
        total=result1["total"],
        latencies_ms=result1["latencies_ms"],
        errors=result1["errors"],
        total_time_s=result1["wall_time_s"],
        mem_before_mb=result1["mem_before_mb"],
        mem_after_mb=result1["mem_after_mb"],
    )
    print(report1)

    # --- Тест 2: 100 sequential GET /api/health ---
    print(f"\n[2/2] Running {SEQUENTIAL_REQUESTS} sequential GET /api/health...")
    result2 = await run_sequential_health(SEQUENTIAL_REQUESTS)
    report2 = format_report(
        endpoint="GET /api/health",
        concurrency="1 (sequential)",
        total=result2["total"],
        latencies_ms=result2["latencies_ms"],
        errors=result2["errors"],
        total_time_s=result2["wall_time_s"],
        mem_before_mb=result2["mem_before_mb"],
        mem_after_mb=result2["mem_after_mb"],
    )
    print(report2)

    # --- Итоговое руководство ---
    print(SERVER_SIZING_GUIDE)


if __name__ == "__main__":
    asyncio.run(_main())
