"""
Benchmark-тесты латентности отдельных эндпоинтов (pytest-benchmark).

Запуск:
    pytest tests/test_performance.py -v --benchmark-min-rounds=100

Каждый бенчмарк выполняет 100 итераций запроса через FastAPI TestClient
(in-process, без реального сетевого стека) и выводит min/max/mean/stddev.

Внешние вызовы VK замокированы — замеряем только логику приложения и SQLite.
"""

import os
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from unittest.mock import patch, AsyncMock

# Фикстуры client и setup_database подхватываются из conftest.py автоматически.

# ---------------------------------------------------------------------------
# Вспомогательные данные
# ---------------------------------------------------------------------------

# Базовая нагрузка для бенчмарков бронирования.
# Дата вынесена в будущее, чтобы не спотыкаться о check на прошедшие даты.
_BENCH_COUNTER = 0  # инкремент обеспечивает уникальность телефона


def _unique_payload(base_phone_suffix: int) -> dict:
    """Возвращает payload с уникальным телефоном (нет 409)."""
    phone = f"9{base_phone_suffix:09d}"
    return {
        "name": "Анна Бенчмарк",
        "guests": 2,
        "phone": phone,
        "date": "2027-06-01",
        "time": "18:00",
        "comment": None,
        "vk_user_id": None,
        "vk_notifications": False,
    }


# ---------------------------------------------------------------------------
# Бенчмарки
# ---------------------------------------------------------------------------

class TestBenchmarkReservation:
    """Замер латентности POST /api/reservation (in-process через TestClient)."""

    @patch("app.main.send_waiters_new_reservation", new_callable=AsyncMock)
    @patch("app.main.send_vk_message", new_callable=AsyncMock)
    @patch("app.main.send_admin_notification", new_callable=AsyncMock)
    def test_benchmark_post_reservation(
        self, mock_admin, mock_send, mock_waiters, client, benchmark
    ):
        """
        Benchmark: POST /api/reservation — 100 раундов.

        Каждый раунд использует уникальный телефон, чтобы избежать 409.
        Глобальный rate limit (_global_log) не сбрасывается между раундами,
        поэтому бенчмарк намеренно проверяет путь, включая запись в rate_limit.

        Ориентиры (SQLite, in-process):
          - p99 < 50 ms  → хорошо для dev-окружения
          - mean < 20 ms → норма для SQLite, на PostgreSQL будет выше ~5-10ms
        """
        counter = [0]  # изменяемое замыкание

        # Сброс глобального лога перед серией, чтобы не упереться в 429
        from app.main import _global_log
        _global_log.clear()

        def run_one():
            counter[0] += 1
            payload = _unique_payload(counter[0])
            response = client.post("/api/reservation", json=payload)
            # 200 — успех, 429 — rate limit исчерпан (при большом числе раундов)
            assert response.status_code in (200, 429), (
                f"Unexpected status {response.status_code}: {response.text}"
            )

        benchmark.pedantic(run_one, rounds=100, warmup_rounds=5)


class TestBenchmarkHealth:
    """Замер латентности GET /api/health (in-process через TestClient)."""

    def test_benchmark_get_health(self, client, benchmark):
        """
        Benchmark: GET /api/health — 100 раундов.

        Health check выполняет SELECT 1 и COUNT по ScheduledTask.
        На PostgreSQL добавьте ~1-3 ms сетевого оверхеда.

        Ориентиры:
          - mean < 10 ms  → хорошо
          - p99  < 30 ms  → допустимо для мониторинга
        """

        def run_one():
            response = client.get("/api/health")
            assert response.status_code == 200

        benchmark.pedantic(run_one, rounds=100, warmup_rounds=5)


class TestBenchmarkMetrics:
    """Замер латентности GET /api/metrics (in-process через TestClient)."""

    def test_benchmark_get_metrics(self, client, benchmark):
        """
        Benchmark: GET /api/metrics — 100 раундов.

        Метрики выполняют 6 COUNT-запросов. На PostgreSQL с реальными данными
        индексы (phone+date, date, appeared, completed) обеспечивают O(1) count.

        Ориентиры:
          - mean < 15 ms  → хорошо
          - p99  < 50 ms  → допустимо
        """

        def run_one():
            response = client.get("/api/metrics")
            assert response.status_code == 200

        benchmark.pedantic(run_one, rounds=100, warmup_rounds=5)


class TestBenchmarkComparison:
    """Сравнительный бенчмарк всех трёх эндпоинтов в одном прогоне."""

    @patch("app.main.send_waiters_new_reservation", new_callable=AsyncMock)
    @patch("app.main.send_vk_message", new_callable=AsyncMock)
    @patch("app.main.send_admin_notification", new_callable=AsyncMock)
    def test_benchmark_all_endpoints_sequential(
        self, mock_admin, mock_send, mock_waiters, client, benchmark
    ):
        """
        Benchmark: один раунд = 1×POST reservation + 1×GET health + 1×GET metrics.

        Имитирует типичную нагрузку: пользователь бронирует, сервис мониторинга
        опрашивает health/metrics параллельно.
        """
        counter = [1_000_000]  # начинаем с большого числа, чтобы не пересечься с другими тестами

        from app.main import _global_log
        _global_log.clear()

        def run_one():
            counter[0] += 1
            payload = _unique_payload(counter[0])
            r1 = client.post("/api/reservation", json=payload)
            assert r1.status_code in (200, 429)

            r2 = client.get("/api/health")
            assert r2.status_code == 200

            r3 = client.get("/api/metrics")
            assert r3.status_code == 200

        benchmark.pedantic(run_one, rounds=100, warmup_rounds=3)
