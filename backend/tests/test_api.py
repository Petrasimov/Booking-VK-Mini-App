"""
Тесты API эндпоинтов: создание бронирования, отчёт об ошибке, health, метрики.
"""

import pytest
from unittest.mock import patch, AsyncMock


class TestCreateReservation:
    """Тесты POST /api/reservation."""

    @patch("app.main.send_waiters_new_reservation", new_callable=AsyncMock)
    @patch("app.main.send_vk_message", new_callable=AsyncMock)
    @patch("app.main.build_confirmation_message", return_value="test")
    def test_create_reservation_success(self, mock_build, mock_send, mock_waiters, client):
        """Успешное создание бронирования."""
        payload = {
            "name": "Иван",
            "guests": 2,
            "phone": "89001234567",
            "date": "2026-03-15",
            "time": "14:00",
        }
        response = client.post("/api/reservation", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Иван"
        assert data["guests"] == 2
        assert data["id"] is not None

    @patch("app.main.send_waiters_new_reservation", new_callable=AsyncMock)
    @patch("app.main.send_vk_message", new_callable=AsyncMock)
    @patch("app.main.build_confirmation_message", return_value="test")
    def test_create_reservation_with_comment(self, mock_build, mock_send, mock_waiters, client):
        """Бронирование с комментарием."""
        payload = {
            "name": "Мария",
            "guests": 4,
            "phone": "89001234567",
            "date": "2026-03-20",
            "time": "18:30",
            "comment": "У окна",
        }
        response = client.post("/api/reservation", json=payload)
        assert response.status_code == 200
        assert response.json()["comment"] == "У окна"

    def test_create_reservation_invalid_name(self, client):
        """Невалидное имя — 422."""
        payload = {
            "name": "X",
            "guests": 1,
            "phone": "89001234567",
            "date": "2026-03-15",
            "time": "14:00",
        }
        response = client.post("/api/reservation", json=payload)
        assert response.status_code == 422

    def test_create_reservation_invalid_phone(self, client):
        """Невалидный телефон — 422."""
        payload = {
            "name": "Иван",
            "guests": 1,
            "phone": "123",
            "date": "2026-03-15",
            "time": "14:00",
        }
        response = client.post("/api/reservation", json=payload)
        assert response.status_code == 422

    def test_create_reservation_missing_fields(self, client):
        """Нет обязательных полей — 422."""
        response = client.post("/api/reservation", json={})
        assert response.status_code == 422

    @patch("app.main.send_waiters_new_reservation", new_callable=AsyncMock)
    @patch("app.main.send_vk_message", new_callable=AsyncMock)
    @patch("app.main.build_confirmation_message", return_value="test")
    def test_duplicate_booking_returns_409(self, mock_build, mock_send, mock_waiters, client):
        """Повторное бронирование на тот же день — 409."""
        payload = {
            "name": "Иван",
            "guests": 2,
            "phone": "89001234567",
            "date": "2026-03-15",
            "time": "14:00",
        }
        # Первое бронирование — успешно
        response = client.post("/api/reservation", json=payload)
        assert response.status_code == 200

        # Второе с тем же телефоном и датой — конфликт
        response = client.post("/api/reservation", json=payload)
        assert response.status_code == 409

    @patch("app.main.send_waiters_new_reservation", new_callable=AsyncMock)
    @patch("app.main.send_vk_message", new_callable=AsyncMock)
    @patch("app.main.build_confirmation_message", return_value="test")
    def test_rate_limit(self, mock_build, mock_send, mock_waiters, client):
        """Rate limit: 4-й запрос за минуту — 429."""
        # Используем разные даты, чтобы не попасть на проверку дубликатов
        for i in range(3):
            payload = {
                "name": "Иван",
                "guests": 1,
                "phone": "89001234567",
                "date": f"2026-03-{15 + i}",
                "time": "14:00",
            }
            response = client.post("/api/reservation", json=payload)
            assert response.status_code == 200

        # 4-й запрос — rate limit
        response = client.post("/api/reservation", json={
            "name": "Иван",
            "guests": 1,
            "phone": "89001234567",
            "date": "2026-03-18",
            "time": "14:00",
        })
        assert response.status_code == 429


class TestErrorReport:
    """Тесты POST /api/error-report."""

    @patch("app.main.send_admin_notification", new_callable=AsyncMock)
    def test_report_error_success(self, mock_admin, client):
        """Успешная отправка отчёта об ошибке."""
        payload = {
            "message": "Test error",
            "details": "Some stack trace",
        }
        response = client.post("/api/error-report", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_report_error_missing_message(self, client):
        """Нет message — 422."""
        response = client.post("/api/error-report", json={})
        assert response.status_code == 422


class TestHealth:
    """Тесты GET /api/health."""

    def test_health_check(self, client):
        """Health check возвращает статус и uptime."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("ok", "degraded")
        assert "uptime_seconds" in data
        assert "pending_tasks" in data


class TestMetrics:
    """Тесты GET /api/metrics."""

    def test_metrics(self, client):
        """Метрики возвращают корректные поля."""
        response = client.get("/api/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "reservations_total" in data
        assert "reservations_today" in data
        assert "uptime_seconds" in data
