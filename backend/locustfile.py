"""
Locust load test для Shokoladnitsa Booking API.

Запуск (веб-интерфейс):
    cd backend
    locust -f locustfile.py --host http://localhost:8001

Запуск без UI (headless):
    locust -f locustfile.py --host http://localhost:8001 \
           --headless -u 50 -r 10 --run-time 60s

Сценарии:
    BookingUser  (80% трафика) — бронирует столик через POST /api/reservation
    HealthChecker (20% трафика) — проверяет GET /api/health

    AdminUser — отдельный класс, опрашивает GET /api/metrics каждые 30 с

Тестовые данные:
    - Случайные русские имена (50 вариантов)
    - Случайные 10-значные телефоны (начинаются с 9)
    - Даты: сегодня+1 … сегодня+30
    - Времена: 12:00–20:00 (только популярные слоты)
    - Гости: 1–6

Примечание:
    vk_user_id=null, vk_notifications=false — VK API не вызывается.
    Дублирующие брони (один phone+date) вернут 429 / 409 — это ожидаемо при
    длительном прогоне; Locust считает их как допустимые ответы.
"""

import random
from datetime import date, timedelta

from locust import HttpUser, task, between, constant

# ---------------------------------------------------------------------------
# Пул тестовых данных
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "Александр", "Алексей", "Андрей", "Антон", "Артём",
    "Виктор", "Владимир", "Дмитрий", "Евгений", "Иван",
    "Игорь", "Илья", "Кирилл", "Константин", "Максим",
    "Михаил", "Никита", "Николай", "Олег", "Павел",
    "Анастасия", "Анна", "Валентина", "Валерия", "Виктория",
    "Екатерина", "Елена", "Ирина", "Кристина", "Ксения",
    "Людмила", "Мария", "Надежда", "Наталья", "Ольга",
    "Светлана", "Татьяна", "Юлия", "Алина", "Дарья",
]

LAST_NAMES = [
    "Иванов", "Петров", "Сидоров", "Смирнов", "Кузнецов",
    "Попов", "Волков", "Новиков", "Морозов", "Лебедев",
    "Козлов", "Николаев", "Орлов", "Андреев", "Макаров",
    "Иванова", "Петрова", "Сидорова", "Смирнова", "Кузнецова",
]

TIMES = ["12:00", "13:00", "14:00", "15:00", "18:00", "19:00", "20:00"]

TODAY = date.today()


def random_name() -> str:
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    return f"{first} {last}"


def random_phone() -> str:
    """10-значный номер, начинается с 9."""
    return f"9{random.randint(100_000_000, 999_999_999)}"


def random_date() -> str:
    """Случайная дата в диапазоне [+1, +30] дней от сегодня."""
    offset = random.randint(1, 30)
    return (TODAY + timedelta(days=offset)).isoformat()


def random_guests() -> int:
    return random.randint(1, 6)


def random_comment() -> str | None:
    options = [None, None, None, "У окна", "Тихое место", "Детский стул", "Аллергия на орехи"]
    return random.choice(options)


def make_reservation_payload() -> dict:
    """Генерирует валидный payload для POST /api/reservation."""
    return {
        "name": random_name(),
        "guests": random_guests(),
        "phone": random_phone(),
        "date": random_date(),
        "time": random.choice(TIMES),
        "comment": random_comment(),
        "vk_user_id": None,         # Не вызывает VK API
        "vk_notifications": False,  # Не создаёт лишних ScheduledTask
    }


# ---------------------------------------------------------------------------
# Сценарии пользователей
# ---------------------------------------------------------------------------

class BookingUser(HttpUser):
    """
    Основной сценарий (80% нагрузки).

    Пользователь открывает мини-приложение и бронирует столик.
    Соотношение @task: booking(4) : health(1) = 80% : 20%.

    wait_time = between(1, 3) — пауза 1-3 с между действиями,
    имитирует время заполнения формы.
    """

    wait_time = between(1, 3)

    @task(4)
    def create_reservation(self):
        """POST /api/reservation — создание бронирования."""
        payload = make_reservation_payload()
        with self.client.post(
            "/api/reservation",
            json=payload,
            # 409 (дубликат) и 429 (rate limit) — ожидаемые при нагрузке,
            # помечаем как успешные, чтобы не сбивать статистику ошибок.
            catch_response=True,
            name="POST /api/reservation",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code in (409, 429):
                # Ожидаемый ответ при нагрузочном тестировании
                response.success()
            else:
                response.failure(
                    f"Unexpected status {response.status_code}: {response.text[:200]}"
                )

    @task(1)
    def check_health(self):
        """GET /api/health — проверка работоспособности."""
        with self.client.get(
            "/api/health",
            catch_response=True,
            name="GET /api/health",
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("status") not in ("ok", "degraded"):
                    response.failure(f"Unexpected health status: {data}")
                else:
                    response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")


class HealthChecker(HttpUser):
    """
    Вспомогательный сценарий (~20% пользователей).

    Чистый health-checker: только GET /api/health.
    Имитирует внешний мониторинг (uptime-robot, etc.).
    """

    wait_time = between(1, 3)

    @task
    def check_health(self):
        """GET /api/health."""
        with self.client.get(
            "/api/health",
            catch_response=True,
            name="GET /api/health (checker)",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")


class AdminUser(HttpUser):
    """
    Сценарий администратора.

    Опрашивает GET /api/metrics каждые 30 секунд.
    Имитирует дашборд администратора или систему мониторинга.
    """

    wait_time = constant(30)

    @task
    def get_metrics(self):
        """GET /api/metrics — метрики приложения."""
        with self.client.get(
            "/api/metrics",
            catch_response=True,
            name="GET /api/metrics",
        ) as response:
            if response.status_code == 200:
                data = response.json()
                required_keys = {
                    "reservations_total", "reservations_today",
                    "errors_24h", "pending_tasks", "uptime_seconds",
                }
                missing = required_keys - set(data.keys())
                if missing:
                    response.failure(f"Missing keys in metrics: {missing}")
                else:
                    response.success()
            else:
                response.failure(f"Metrics endpoint failed: {response.status_code}")
