# ROADMAP — Универсальная система бронирования VK Mini App
> Стек: FastAPI · PostgreSQL · React · VKUI · TimeWeb VPS · Ubuntu 24.04
> Подход: **Local-first** — весь проект собирается локально, деплой в конце
> Инструменты: VS Code · GitHub · TimeWeb
> Обновлён: апрель 2026

---

## Содержание

- [Рабочий процесс](#рабочий-процесс)
- [Рекомендуемый сервер TimeWeb](#рекомендуемый-сервер-timeweb)
- [ЧАСТЬ I — Локальная разработка](#часть-i--локальная-разработка)
  - [Этап 0 — Локальное окружение](#этап-0--локальное-окружение)
  - [Этап 1 — Мультитенантность](#этап-1--мультитенантность)
  - [Этап 2 — Универсальные категории](#этап-2--универсальные-категории)
  - [Этап 3 — Умное хранение данных](#этап-3--умное-хранение-данных)
  - [Этап 4 — Онбординг и панель владельца](#этап-4--онбординг-и-панель-владельца)
  - [Этап 5 — Монетизация и тарифы](#этап-5--монетизация-и-тарифы)
  - [Этап 6 — Подготовка к деплою](#этап-6--подготовка-к-деплою)
- [ЧАСТЬ II — Деплой и запуск](#часть-ii--деплой-и-запуск)
  - [Этап 7 — Настройка сервера TimeWeb](#этап-7--настройка-сервера-timeweb)
  - [Этап 8 — Деплой приложения](#этап-8--деплой-приложения)
  - [Этап 9 — Лендинг и публикация](#этап-9--лендинг-и-публикация)
  - [Этап 10 — Рост](#этап-10--рост)
- [Инфраструктура и расходы](#инфраструктура-и-расходы)
- [Полный технический стек](#полный-технический-стек)

---

## Рабочий процесс

```
┌─────────────────────────────────────────────────────────────────┐
│                   ЧАСТЬ I — До сервера                          │
│                   Всё делается в VS Code                        │
│                                                                 │
│  Локальная PostgreSQL  ←→  FastAPI (localhost:8001)             │
│  Локальный React       ←→  Vite dev server (localhost:5173)     │
│                                                                 │
│  Параллельно пишем:                                             │
│  • .github/workflows/deploy.yml  (CI/CD — активируем позже)     │
│  • Sentry SDK — уже в коде, DSN добавим после регистрации       │
│  • deploy.sh, nginx.conf, systemd unit-файлы                    │
└────────────────────────────┬────────────────────────────────────┘
                             │  Когда проект готов
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   ЧАСТЬ II — Деплой                             │
│                                                                 │
│  1. Арендуем TimeWeb VPS                                        │
│  2. Настраиваем сервер (nginx, PostgreSQL, systemd)             │
│  3. git push → GitHub Actions → автодеплой                      │
│  4. Публикуем в каталог VK                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Рекомендуемый сервер TimeWeb

**Тариф для старта:** Облачный сервер **Cloud-2**
```
vCPU:    2 ядра
RAM:     4 GB
SSD:     60 GB NVMe
ОС:      Ubuntu 24.04 LTS
Цена:    ~800 ₽/мес
```

**Когда арендовать:** После завершения Этапа 6 (проект полностью собран локально).

**Апгрейд при росте (100+ заведений):**
```
vCPU:    4 ядра
RAM:     8 GB
SSD:     80 GB NVMe
Цена:    ~1 600 ₽/мес
```

---

# ЧАСТЬ I — Локальная разработка

---

## Этап 0 — Локальное окружение

> **Цель:** Настроить рабочее место так, чтобы разработка была удобной и предсказуемой
> **Где работаем:** VS Code, терминал
> **Длительность:** 2–3 дня

---

### Шаг 0.1 — Установка инструментов

**Что делаем:** Убеждаемся что все необходимые инструменты установлены и обновлены.

**Чеклист установки:**
```
□ Python 3.11+          — python --version
□ Node.js 20+           — node --version
□ PostgreSQL 14+        — psql --version  (локальный сервер)
□ Git                   — git --version
□ VS Code Extensions:
    □ Python (ms-python)
    □ Pylance
    □ ESLint
    □ Prettier
    □ GitLens
    □ Thunder Client (тестирование API, замена Postman)
```

**Шаги:**
1. Установить PostgreSQL локально (для Windows: installer с postgresql.org, для Mac: `brew install postgresql@14`)
2. Создать локальную БД: `createdb shokoladnitsa_dev`
3. Убедиться что существующий проект запускается: `python start_all.py` и `npm run dev`
4. Установить VS Code расширения из чеклиста

**Итог:** Текущий проект запускается локально без ошибок.

---

### Шаг 0.2 — Настройка Git и GitHub

**Что делаем:** Настроить репозиторий и ветки для правильного рабочего процесса.

**Структура веток:**
```
main          — стабильная версия, только сюда деплоится на сервер
develop       — активная разработка, сюда мержатся фичи
feature/...   — отдельные ветки для каждого этапа
```

**Шаги:**
1. Убедиться что проект уже на GitHub
2. Создать ветку `develop`: `git checkout -b develop`
3. Настроить `.gitignore` — добавить `.env`, `*.pyc`, `node_modules`, `dist`
4. Создать шаблон `.env.example` с пустыми ключами (без реальных значений)
5. Настроить `pre-commit` хук для запуска линтеров перед каждым коммитом

**Итог:** Чистая структура репозитория, рабочий процесс через ветки.

---

### Шаг 0.3 — Локальная PostgreSQL и .env

**Что делаем:** Настроить локальную базу данных и переменные окружения для разработки.

**Файлы:** `backend/.env`, `backend/.env.example`

**Шаблон `.env` для локальной разработки:**
```env
# База данных (локальная)
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/shokoladnitsa_dev
DATABASE_URL_SYNC=postgresql+psycopg2://postgres:password@localhost:5432/shokoladnitsa_dev

# VK (тестовая группа)
VK_GROUP_TOKEN=vk1.a.test_token_here
VK_GROUP_ID=123456789
VK_CHAT_ID=1
VK_ADMIN_ID=your_vk_user_id

# Sentry (оставляем пустым до регистрации)
SENTRY_DSN=

# Платежи ЮKassa (оставляем пустым до регистрации)
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=

# Cloudflare R2 (оставляем пустым до настройки)
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=bookings-archive

# Окружение
ENV=development
```

**Шаги:**
1. Создать `backend/.env` по шаблону выше
2. Создать `backend/.env.example` (копия без реальных значений)
3. Запустить существующие миграции: `alembic upgrade head`
4. Запустить тесты: `pytest tests/ -v` — все должны пройти
5. Убедиться что `.env` добавлен в `.gitignore`

**Итог:** Локальная БД поднята, тесты проходят, секреты не попадают в git.

---

### Шаг 0.4 — Подготовка GitHub Actions (CI/CD файлы)

**Что делаем:** Написать файлы CI/CD сейчас, чтобы не делать это под давлением при деплое. Workflows будут в репозитории, но deploy не будет работать до появления сервера — CI (тесты) работает прямо сейчас.

**Файлы:** `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`

**`ci.yml` — запускается на каждый push и PR:**
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:14
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: test_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with: { python-version: '3.11' }
      - run: pip install -r backend/requirements.txt
      - run: cd backend && pytest tests/ -v
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cd vk-table-booking && npm ci && npm run lint
```

**`deploy.yml` — запускается только при push в main (активируем после аренды сервера):**
```yaml
# Добавить в GitHub Secrets перед активацией:
#   SERVER_HOST, SERVER_USER, SERVER_SSH_KEY
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            cd /var/www/app && bash deploy/deploy.sh
```

**Шаги:**
1. Создать папку `.github/workflows/`
2. Написать `ci.yml`
3. Написать `deploy.yml`
4. Закоммитить оба файла — CI запустится автоматически на GitHub

**Итог:** CI (тесты + линтер) работает прямо сейчас. Deploy ждёт сервера.

---

### Шаг 0.5 — Интеграция Sentry

**Что делаем:** Зарегистрироваться в Sentry (бесплатно) и добавить DSN в `.env`. Код интеграции уже есть в проекте.

**Шаги:**
1. Зарегистрироваться на sentry.io — бесплатный план: 5 000 событий/мес
2. Создать два проекта: `bookings-backend` (Python) и `bookings-frontend` (React)
3. Добавить DSN в `backend/.env`: `SENTRY_DSN=https://...`
4. Добавить в `vk-table-booking/.env`: `VITE_SENTRY_DSN=https://...`
5. Запустить локально, искусственно вызвать ошибку — убедиться что она в Sentry

**Итог:** Мониторинг ошибок работает локально и будет работать на сервере без изменений кода.

---

## Этап 1 — Мультитенантность

> **Цель:** Превратить систему под одно кафе в платформу для любых заведений
> **Ветка:** `feature/multitenancy`
> **Длительность:** 5–7 недель
> **Зависимости:** Этап 0 завершён

---

### Шаг 1.1 — Модель Venue

**Что делаем:** Добавляем центральную таблицу заведений — фундамент всей платформы.

**Файлы:** `backend/app/models.py`, новая миграция Alembic

**Новые модели:**
```python
class Venue(Base):
    __tablename__ = "venues"

    id              = Column(Integer, primary_key=True)
    vk_group_id     = Column(BigInteger, unique=True, nullable=False, index=True)
    name            = Column(String(200), nullable=False)
    category        = Column(String(50), nullable=False)
    # cafe | barbershop | clinic | fitness | beauty | photo_studio | coworking | other

    config          = Column(JSON, nullable=False, default={})
    # Структура конфига описана в Шаге 1.2

    timezone        = Column(String(50), default="Europe/Moscow")
    address         = Column(String(500))
    phone           = Column(String(30))
    owner_vk_id     = Column(BigInteger, nullable=False)

    plan            = Column(String(20), default="free")  # free | standard | pro
    plan_expires_at = Column(DateTime, nullable=True)

    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VenueRole(Base):
    __tablename__ = "venue_roles"

    id         = Column(Integer, primary_key=True)
    venue_id   = Column(Integer, ForeignKey("venues.id"), nullable=False, index=True)
    vk_user_id = Column(BigInteger, nullable=False)
    role       = Column(String(20), nullable=False)  # owner | manager | staff
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("venue_id", "vk_user_id"),)
```

**Шаги:**
1. Добавить модели `Venue` и `VenueRole` в `models.py`
2. Добавить поле `venue_id` (ForeignKey → venues.id) в `Reservation`, `ScheduledTask`, `ErrorLog`, `RateLimitEntry`
3. Написать Alembic-миграцию: `alembic revision --autogenerate -m "add_venue_multitenancy"`
4. Написать seed-скрипт: добавить текущее кафе «Шоколадница» как первое заведение, привязать все старые брони к `venue_id=1`
5. Применить: `alembic upgrade head`, запустить seed, убедиться что тесты проходят

**Итог:** БД поддерживает несколько заведений, старые данные не потеряны.

---

### Шаг 1.2 — Шаблоны конфигов по категориям

**Что делаем:** Для каждой категории бизнеса создать конфиг по умолчанию — структуру JSON, который хранится в `venue.config`.

**Файлы:** `backend/app/venue_templates.py` (новый)

**Единая структура config для всех категорий:**
```python
{
  # Расписание
  "time_slots": ["10:00", "11:00", ...],    # список слотов
  "slot_duration_minutes": 60,              # длительность одного слота
  "working_days": [1,2,3,4,5,6,7],         # 1=пн, 7=вс
  "working_hours": {
      "default": {"open": "10:00", "close": "22:00"},
      "sat": {"open": "11:00", "close": "23:00"},  # переопределение
  },
  "max_guests_per_slot": 1,  # сколько одновременных броней на слот

  # Поля формы
  "fields": {
      "guests":  {"enabled": True,  "required": True,  "max": 20},
      "comment": {"enabled": True,  "required": False},
      "service": {"enabled": False, "options": []},   # для барбершопа
      "master":  {"enabled": False, "options": []},   # для барбершопа
      "zone":    {"enabled": False, "options": []},   # для кафе: "зал", "терраса"
  },

  # Уведомления
  "notifications_chat_id": None,
  "vk_group_token": None,

  # Брендинг (Standard+)
  "logo_url": None,
  "accent_color": "#FF6B35",
  "welcome_text": "Онлайн-запись",
}
```

**Категории:**
| Категория | Включённые поля | Слот |
|-----------|----------------|------|
| `cafe` | guests, comment, zone | 60 мин |
| `barbershop` | service, master, comment | 30–60 мин |
| `clinic` | service (тип приёма), master (врач) | 15–30 мин |
| `fitness` | service (тренировка), master (тренер) | 60 мин |
| `beauty` | service, master, comment | 30–90 мин |
| `photo_studio` | service (зал), comment | 60–120 мин |
| `coworking` | service (тариф), comment | 60 мин |
| `other` | comment | свободно |

**Шаги:**
1. Написать `VENUE_TEMPLATES` словарь с конфигами для всех 8 категорий
2. Добавить Pydantic-схему `VenueConfig` для валидации структуры конфига
3. Написать `get_default_config(category: str) -> dict`
4. Добавить `GET /api/templates` — возвращает список шаблонов для онбординга
5. Написать тест: каждый шаблон проходит валидацию `VenueConfig`

**Итог:** Любую нишу можно подключить выбрав шаблон.

---

### Шаг 1.3 — Tenant Middleware

**Что делаем:** Каждый входящий запрос автоматически определяет своё заведение по `group_id`.

**Файлы:** `backend/app/middleware.py`, `backend/app/main.py`

**Логика:**
```
Запрос → Middleware читает X-VK-Group-ID из заголовка
                             (или ?group_id= из query params)
       ↓
   group_id есть?
   ├── НЕТ  → 400 {"error": "missing_group_id"}
   └── ДА   → проверяем LRU-кэш (TTL 5 мин, 200 заведений)
              ├── Есть в кэше → request.state.venue = venue → продолжаем
              └── Нет в кэше  → запрос в БД
                                ├── Не найдено → 404 {"error": "venue_not_found"}
                                └── Найдено   → кладём в кэш → продолжаем
```

**Шаги:**
1. Написать `TenantMiddleware` с LRU-кэшем
2. Добавить в `main.py` после CORS middleware
3. Создать FastAPI dependency `get_venue()` — извлекает venue из `request.state`
4. Обновить все эндпоинты: принимают `venue = Depends(get_venue)`
5. Написать тесты: без group_id → 400, неизвестный → 404, известный → 200

**Итог:** Все эндпоинты автоматически работают в контексте конкретного заведения.

---

### Шаг 1.4 — Изоляция данных

**Что делаем:** Гарантировать что заведение А никогда не видит данные заведения Б.

**Правило:** Каждый SQL-запрос к `Reservation` и `ScheduledTask` обязан содержать `.filter(Model.venue_id == venue.id)`.

**Файлы:** `backend/app/main.py`, `backend/app/admin/stats.py`, `backend/app/admin/export.py`

**Шаги:**
1. Создать базовый репозиторий `VenueRepository` с автофильтрацией по `venue_id`
2. Обновить `POST /api/reservation`: автоматически ставить `venue_id` при создании
3. Обновить все `GET` запросы: добавить фильтр по `venue_id`
4. Обновить `stats.py` и `export.py`: принимают `venue_id` параметром
5. Написать интеграционный тест: 2 заведения, 2 брони — каждое видит только своё

**Итог:** Полная изоляция данных подтверждена тестами.

---

### Шаг 1.5 — Эндпоинт GET /api/config

**Что делаем:** Фронтенд при запуске запрашивает этот эндпоинт и строит всю форму на его основе.

**Файлы:** `backend/app/main.py`, `backend/app/schemas.py`

**Ответ:**
```json
{
  "is_registered": true,
  "venue_id": 1,
  "name": "Шоколадница на Арбате",
  "category": "cafe",
  "timezone": "Europe/Moscow",
  "plan": "free",
  "plan_limits": {
    "bookings_per_month": 30,
    "bookings_used_this_month": 12,
    "history_days": 30
  },
  "config": {
    "time_slots": ["10:00", "11:00", "..."],
    "fields": { "guests": {"enabled": true, "max": 8}, "...": "..." },
    "accent_color": "#8B4513",
    "welcome_text": "Забронируйте столик",
    "logo_url": null
  }
}
```

> Если group_id не зарегистрирован → `{"is_registered": false}` (не 404, чтобы фронтенд мог показать онбординг)

**Шаги:**
1. Добавить Pydantic-схему `VenueConfigResponse`
2. Написать `GET /api/config` эндпоинт
3. Обновить `App.jsx`: запрашивать `/api/config` при старте
4. Если `is_registered: false` → показать онбординг-визард
5. Кэшировать конфиг на фронтенде через `sessionStorage` на 10 минут

**Итог:** Фронтенд знает всё о заведении с первого запроса.

---

### Шаг 1.6 — Мультитенантный VK Bot

**Что делаем:** Переписать бота — уведомления каждого заведения идут в свой чат по его токену.

**Файлы:** `backend/app/vk_bot.py`, `backend/app/vk_bot_server.py`

**Текущая проблема:** `VK_GROUP_TOKEN` и `VK_CHAT_ID` хардкожены в `.env`.

**После изменений:**
```python
# Все функции принимают venue объект
async def send_waiters_new_reservation(venue: Venue, reservation: Reservation):
    token   = venue.config.get("vk_group_token")
    chat_id = venue.config.get("notifications_chat_id")
    if not token or not chat_id:
        logger.warning("Venue %d: VK notifications not configured", venue.id)
        return False
    # ... отправка через токен заведения
```

**Шаги:**
1. Перенести `VK_GROUP_TOKEN` из `.env` в `venue.config["vk_group_token"]`
2. Перенести `VK_CHAT_ID` в `venue.config["notifications_chat_id"]`
3. Переписать все функции `vk_bot.py` — принимают `venue` объект
4. Обновить `vk_bot_server.py`: маршрутизация входящих сообщений по `group_id`
5. Обновить вызовы бота в `main.py` и `scheduler.py` — передавать `venue`

**Итог:** Каждое заведение имеет независимый канал уведомлений в VK.

---

### Шаг 1.7 — Тесты мультитенантности

**Файлы:** `backend/tests/test_multitenancy.py` (новый)

**Список тестов:**
```
test_two_venues_isolated           — заведение А не видит брони Б
test_tenant_middleware_no_group    — запрос без group_id → 400
test_tenant_middleware_unknown     — неизвестный group_id → 404
test_config_returns_correct_venue  — правильный конфиг для правильной группы
test_config_unregistered           — незарегистрированный → is_registered: false
test_rate_limit_per_venue          — лимиты независимы между заведениями
test_bot_routing                   — уведомления идут в правильный чат
test_admin_stats_scoped            — статистика только своего заведения
test_export_scoped                 — CSV только своих броней
```

**Итог:** 9 тестов, все зелёные.

---

## Этап 2 — Универсальные категории

> **Цель:** Поддержать кафе, барбершоп, клинику и любую другую нишу из коробки
> **Ветка:** `feature/universal-categories`
> **Длительность:** 3–4 недели
> **Зависимости:** Этап 1 завершён

---

### Шаг 2.1 — Динамическая форма бронирования

**Что делаем:** Переписать `BookingForm.jsx` — поля генерируются из `config.fields`, а не захардкожены под кафе.

**Файлы:** `vk-table-booking/src/components/BookingForm.jsx`, новый `DynamicField.jsx`

**Принцип:**
```
config.fields.guests  = { enabled: true, max: 8 }
  → рендерим <NumberInput max={8} />

config.fields.service = { enabled: true, options: ["Стрижка","Борода"] }
  → рендерим <Select options={...} />

config.fields.master  = { enabled: true, options: ["Алексей","Дмитрий"] }
  → рендерим <Select options={...} />

config.fields.comment = { enabled: false }
  → НЕ рендерим ничего
```

**Шаги:**
1. Создать `DynamicField.jsx` — рендерит поле по типу: text, number, select, textarea
2. Переписать `BookingForm.jsx` — поля берутся из `config.fields`
3. Обновить `validators.js` — валидация учитывает `required` из конфига
4. Обновить `App.jsx` — загружает конфиг при старте и передаёт в форму
5. Добавить скелетон-загрузку пока конфиг грузится
6. Протестировать вручную с конфигом барбершопа

**Итог:** Одна форма корректно рендерится для любой ниши.

---

### Шаг 2.2 — Поле extra_data в брони

**Что делаем:** Добавить `extra_data` в модель бронирования для хранения специфичных для ниши данных (мастер, услуга, зал и т.д.).

**Файлы:** `backend/app/models.py`, `backend/app/schemas.py`, новая миграция

**Шаги:**
1. Добавить `extra_data = Column(JSON, default={})` в модель `Reservation`
2. Обновить Pydantic-схему: `extra_data: dict = Field(default_factory=dict)`
3. Обновить VK-уведомления: если `extra_data` не пустой — форматировать красиво
   ```
   💈 Услуга: Стрижка + борода
   ✂️ Мастер: Алексей
   ```
4. Обновить CSV-экспорт: каждый ключ из `extra_data` — отдельная колонка
5. Написать миграцию и тесты

**Итог:** Нестандартные данные сохраняются и отображаются корректно во всех местах.

---

### Шаг 2.3 — Тесты категорий

**Файлы:** `backend/tests/test_categories.py` (новый)

```
test_cafe_booking_full_flow        — бронь с гостями и зоной
test_barbershop_booking_with_master — бронь с мастером и услугой
test_clinic_booking                — бронь с врачом и типом приёма
test_booking_without_optional_fields — только обязательные поля
test_extra_data_in_csv             — extra_data раскрывается в CSV колонки
test_vk_notification_with_extra    — красивое уведомление с нестандартными полями
```

**Итог:** Все ниши работают корректно end-to-end.

---

## Этап 3 — Умное хранение данных

> **Цель:** БД остаётся маленькой и быстрой, статистика доступна за всё время
> **Ветка:** `feature/data-lifecycle`
> **Длительность:** 2–3 недели
> **Зависимости:** Этап 1 завершён

---

### Шаг 3.1 — Таблицы архива и агрегатов

**Что делаем:** Создать структуры для Warm storage и постоянной агрегированной статистики.

**Файлы:** `backend/app/models.py`, новая миграция

```python
class VenueStatsDaily(Base):
    """Агрегат — одна строка на день на заведение. Хранится вечно.
    Вес: ~100 байт × 365 дней × 1 000 заведений = 36 МБ/год — ничтожно мало."""
    __tablename__ = "venue_stats_daily"
    id        = Column(Integer, primary_key=True)
    venue_id  = Column(Integer, ForeignKey("venues.id"), nullable=False, index=True)
    date      = Column(Date, nullable=False)
    bookings  = Column(Integer, default=0)
    guests    = Column(Integer, default=0)
    came      = Column(Integer, default=0)
    no_show   = Column(Integer, default=0)
    peak_hour = Column(String(5))  # "19:00"
    __table_args__ = (UniqueConstraint("venue_id", "date"),)


class ReservationArchive(Base):
    """Warm storage — брони 6 мес – 2 года. Без лишних индексов."""
    __tablename__ = "reservations_archive"
    id          = Column(Integer, primary_key=True)
    venue_id    = Column(Integer, ForeignKey("venues.id"), nullable=False, index=True)
    name        = Column(String(200))
    guests      = Column(Integer)
    phone       = Column(String(30))
    date        = Column(Date)
    time        = Column(Time)
    extra_data  = Column(JSON, default={})
    came        = Column(Boolean, default=False)
    created_at  = Column(DateTime)
    archived_at = Column(DateTime, default=datetime.utcnow)
```

**Шаги:**
1. Добавить модели `VenueStatsDaily` и `ReservationArchive` в `models.py`
2. Написать Alembic-миграцию
3. Обновить `stats.py`: при запросах глубже 6 мес читать из `venue_stats_daily`
4. Написать тест: агрегаты совпадают с подсчётом по raw-данным

**Итог:** Структура для трёх уровней хранения (Hot/Warm/Cold) готова.

---

### Шаг 3.2 — Ночные джобы архивирования

**Что делаем:** Добавить три автоматических процесса в `scheduler.py`.

**Файлы:** `backend/app/jobs/archiver.py` (новый), `backend/app/scheduler.py`

```
aggregate_job — каждую ночь в 03:00
  1. Найти брони старше 6 месяцев в таблице reservations
  2. Сгруппировать по (venue_id, date), посчитать агрегаты
  3. INSERT INTO venue_stats_daily (ON CONFLICT DO UPDATE)
  4. INSERT INTO reservations_archive (копия строк)
  5. DELETE FROM reservations (только перенесённые строки)
  Лог: "Archived N reservations for M venues, freed ~X KB"

cold_archive_job — 1-го числа каждого месяца в 02:00
  1. Найти записи в reservations_archive старше 2 лет
  2. Анонимизировать (152-ФЗ): телефон → хэш, имя → инициалы
  3. Сериализовать в JSON → загрузить в Cloudflare R2
     (путь: venues/{venue_id}/archive_{year}_{month}.json)
  4. DELETE FROM reservations_archive (только выгруженные)
  (До настройки R2 — только логировать, не удалять)

cleanup_job — каждую ночь в 04:00
  1. Удалить ScheduledTask (completed=true) старше 30 дней
  2. Удалить RateLimitEntry старше 24 часов
  3. Удалить ErrorLog старше 90 дней
```

**Шаги:**
1. Написать `run_aggregate_job(db)` с полным логированием каждого шага
2. Написать `run_cold_archive_job(db)` — пока только логирует что было бы выгружено
3. Написать `run_cleanup_job(db)`
4. Добавить джобы в `scheduler.py` с расписанием (cron-подобная логика)
5. Добавить в `GET /api/health` метрики: `last_archive_at`, `archived_today_count`
6. Написать тесты: создать старые данные → запустить джоб → проверить результат

**Итог:** БД автоматически очищается, статистика за всё время сохраняется.

---

### Шаг 3.3 — Тарифные ограничения на уровне данных

**Что делаем:** Реализовать ограничения тарифов в бэкенде — они должны работать независимо от UI.

**Файлы:** `backend/app/plan_limits.py` (новый)

```python
PLAN_LIMITS = {
    "free":     {"bookings_per_month": 30,   "history_days": 30,  "export": False, "locations": 1},
    "standard": {"bookings_per_month": None, "history_days": 180, "export": True,  "locations": 1},
    "pro":      {"bookings_per_month": None, "history_days": 730, "export": True,  "locations": 5},
}
```

**Шаги:**
1. Написать `check_booking_limit(venue, db) -> bool`
2. Добавить проверку в `POST /api/reservation`: превышен лимит → `402 Payment Required`
3. Написать `get_history_cutoff_date(venue) -> date`
4. Применять cutoff во всех запросах статистики и списка броней
5. Написать тесты: бесплатный план блокирует 31-ю бронь, не блокирует 30-ю

**Итог:** Тарифы работают автоматически, обойти их через UI невозможно.

---

## Этап 4 — Онбординг и панель владельца

> **Цель:** Любой владелец подключает заведение за 5 минут без техподдержки
> **Ветка:** `feature/onboarding`
> **Длительность:** 5–6 недель
> **Зависимости:** Этапы 1–3 завершены

---

### Шаг 4.1 — API для регистрации заведения

**Новые эндпоинты:**
```
POST  /api/venue/register      — создать заведение (проверка: user — admin группы VK)
PATCH /api/venue/config        — обновить конфиг (owner/manager only)
GET   /api/venue/me            — полная информация о заведении
POST  /api/venue/verify-bot    — проверить что бот добавлен и отвечает
GET   /api/admin/bookings      — список броней с фильтрами и пагинацией
PATCH /api/admin/bookings/{id} — обновить статус (пришёл / отмена)
GET   /api/admin/stats         — статистика с учётом тарифа
GET   /api/admin/export/csv    — CSV экспорт (Standard+ only)
```

**Шаги:**
1. Создать `backend/app/routers/venue.py`
2. В `POST /api/venue/register` — проверить через VK API что `owner_vk_id` является администратором `vk_group_id`
3. Создать dependency `require_role(["owner", "manager"])` для защиты admin-эндпоинтов
4. Реализовать `POST /api/venue/verify-bot` — отправляет тестовое сообщение в чат
5. Написать тесты всех новых эндпоинтов

**Итог:** Backend полностью готов к онбордингу.

---

### Шаг 4.2 — Онбординг-визард (5 экранов)

**Файлы:** `vk-table-booking/src/pages/onboarding/` (новая папка)

```
Экран 1 — Приветствие
  Логотип + "Подключите систему бронирования за 5 минут"
  [Начать настройку]

Экран 2 — Тип бизнеса
  Сетка карточек: ☕ Кафе / ✂️ Барбершоп / 🏥 Клиника /
                  💪 Фитнес / 💅 Красота / 📷 Фото / 💼 Офис / 🏢 Другое

Экран 3 — Информация о заведении
  Название · Адрес · Телефон · Часовой пояс

Экран 4 — Расписание
  Рабочие дни (чекбоксы Пн–Вс)
  Время работы (от / до)
  Интервал слотов: 15 / 30 / 60 / 90 мин
  → Превью слотов обновляется в реальном времени

Экран 5 — Уведомления
  Инструкция: добавить бота в беседу → скопировать ID → вставить
  [Поле ID беседы]
  [Проверить подключение] → зелёная галочка или ошибка
  [Готово] — активна только после успешной проверки
```

**Шаги:**
1. Создать компоненты для 5 экранов в `src/pages/onboarding/`
2. Состояние визарда через `useReducer`
3. Прогресс-бар сверху: 1/5 → 5/5
4. Сохранение данных в конце через `POST /api/venue/register`
5. Проверка бота через `POST /api/venue/verify-bot` с индикатором загрузки
6. После завершения → редирект в панель владельца

**Итог:** Новое заведение подключается за 5 минут самостоятельно.

---

### Шаг 4.3 — Панель владельца

**Файлы:** `vk-table-booking/src/pages/admin/`

**Разделы:**
```
📋 Брони
   Список с фильтрами: дата, статус (ожидает / пришёл / не пришёл)
   Действия на каждой брони: пришёл ✓ / не пришёл ✗ / отменить
   Кнопка "Экспорт CSV" (только Standard+)

📊 Статистика
   Карточки: всего броней · всего гостей · % пришли
   График броней по дням (recharts LineChart)
   Популярные часы (BarChart)
   Период: 7 дней / 30 дней / 90 дней

⚙️ Настройки
   Вкладка "Расписание": слоты, часы, дни
   Вкладка "Форма": включить/выключить поля, добавить мастеров/услуги
   Вкладка "Внешний вид": accent color, логотип, приветственный текст (Standard+)
   Вкладка "Уведомления": ID чата, кнопка проверки

💳 Тариф
   Текущий план + дата окончания
   Карточки тарифов с кнопкой оплаты
   История платежей
```

**Шаги:**
1. Добавить роутинг: при старте определять роль → гость или владелец
2. Создать layout с нижней навигацией (4 пункта)
3. Страница Броней: список, фильтры, пагинация, действия
4. Страница Статистики: подключить recharts
5. Страница Настроек: форма редактирования конфига с реальным превью

**Итог:** Полное управление заведением внутри VK без выхода из приложения.

---

### Шаг 4.4 — Кастомизация брендинга

**Что делаем:** Владелец (Standard+) настраивает внешний вид формы для гостей.

**Шаги:**
1. Добавить в конфиг поля: `logo_url`, `accent_color`, `welcome_text`
2. Фронтенд: при загрузке применять `--accent-color` как CSS переменную
3. Эндпоинт `POST /api/venue/logo` — загрузка логотипа (временно в локальную папку)
4. Color picker в настройках + превью в реальном времени
5. Ограничить feature в middleware: Standard+ only

**Итог:** Каждое заведение имеет уникальный внешний вид формы.

---

## Этап 5 — Монетизация и тарифы

> **Цель:** Стабильный ежемесячный доход начиная с первого платящего клиента
> **Ветка:** `feature/payments`
> **Длительность:** 3–4 недели
> **Зависимости:** Этап 4 завершён

---

### Шаг 5.1 — Регистрация ИП / самозанятость

**Что делаем:** Оформить юридический статус для приёма платежей.

**Шаги:**
1. Зарегистрировать самозанятость в приложении «Мой налог» (5 минут)
2. Зарегистрироваться на yookassa.ru, указать статус
3. Пройти верификацию ЮKassa (1–3 рабочих дня)
4. Получить `shop_id` и `secret_key`
5. Добавить в `.env`: `YOOKASSA_SHOP_ID` и `YOOKASSA_SECRET_KEY`

> ⚠️ Лимит самозанятости: 2.4 млн ₽/год ≈ 200 заведений на Standard.
> При росте → переоформить на ИП (УСН 6%).

**Итог:** Легальный приём платежей.

---

### Шаг 5.2 — Модель Payment и эндпоинты

**Файлы:** `backend/app/models.py`, `backend/app/routers/payments.py` (новый)

```python
class Payment(Base):
    __tablename__ = "payments"
    id           = Column(Integer, primary_key=True)
    venue_id     = Column(Integer, ForeignKey("venues.id"), nullable=False)
    yookassa_id  = Column(String(100), unique=True)
    amount       = Column(Numeric(10, 2), nullable=False)
    plan         = Column(String(20), nullable=False)   # standard | pro
    months       = Column(Integer, default=1)
    status       = Column(String(20), default="pending") # pending | succeeded | canceled
    created_at   = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
```

```
POST /api/payments/create   — создать платёж → вернуть {payment_url, payment_id}
POST /api/payments/webhook  — callback от ЮKassa (HMAC-подпись обязательна)
GET  /api/payments/history  — история платежей заведения
```

**Шаги:**
1. `pip install yookassa`
2. Написать `create_payment(venue, plan, months) -> payment_url`
3. Написать webhook-обработчик: `payment.succeeded` → обновить `venue.plan` и `venue.plan_expires_at`
4. Добавить cron в шедулер: ежедневно проверять истёкшие тарифы → понижать до free
5. Написать тест с mock ЮKassa: симулировать webhook → проверить обновление тарифа

**Итог:** Полный цикл оплаты работает автоматически.

---

### Шаг 5.3 — Экран тарифов в панели владельца

**Файлы:** `vk-table-booking/src/pages/admin/PlanPage.jsx`

**Шаги:**
1. Карточки тарифов: Free / Standard 499₽ / Pro 1299₽ с описанием фич
2. Подсветить активный тариф, показать дату окончания
3. Кнопка «Оплатить» → `POST /api/payments/create` → открыть `payment_url` через VK Bridge
4. После возврата из оплаты → показать «Тариф активирован» если статус изменился
5. История платежей с датами и суммами

**Итог:** Оплата происходит не выходя из VK.

---

## Этап 6 — Подготовка к деплою

> **Цель:** Всё необходимое для деплоя написано заранее, выгрузка на сервер пройдёт без сюрпризов
> **Ветка:** `feature/deploy-prep` → мерж в `main`
> **Длительность:** 1–2 недели
> **Зависимости:** Этапы 1–5 завершены и протестированы

---

### Шаг 6.1 — Конфиг nginx

**Файлы:** `deploy/nginx.conf`

```nginx
server {
    listen 80;
    server_name api.yourdomain.ru;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl http2;
    server_name api.yourdomain.ru;
    ssl_certificate     /etc/letsencrypt/live/api.yourdomain.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.ru/privkey.pem;
    client_max_body_size 5M;
    location /api/ {
        proxy_pass         http://127.0.0.1:8001;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_read_timeout 30s;
    }
}
```

**Шаги:**
1. Создать папку `deploy/` в корне проекта
2. Написать `deploy/nginx.conf`
3. Написать `deploy/README.md` — пошаговая инструкция по настройке сервера

---

### Шаг 6.2 — Systemd unit-файлы

**Файлы:** `deploy/systemd/app-api.service`, `app-bot.service`, `app-scheduler.service`

```ini
[Unit]
Description=Bookings API
After=network.target postgresql.service

[Service]
User=app
WorkingDirectory=/var/www/app/backend
EnvironmentFile=/var/www/app/backend/.env
ExecStart=/var/www/app/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Шаги:**
1. Написать unit-файлы для всех трёх сервисов (API, Bot, Scheduler)
2. Написать `deploy/setup-server.sh` — скрипт первичной настройки Ubuntu

---

### Шаг 6.3 — Скрипт деплоя

**Файлы:** `deploy/deploy.sh`

```bash
#!/bin/bash
set -e
echo "▶ Pulling latest code..."
git pull origin main
echo "▶ Installing Python dependencies..."
cd backend && source .venv/bin/activate && pip install -r requirements.txt --quiet
echo "▶ Running migrations..."
alembic upgrade head
echo "▶ Building frontend..."
cd ../vk-table-booking && npm ci --silent && npm run build
echo "▶ Restarting services..."
sudo systemctl restart app-api app-bot app-scheduler
echo "▶ Health check..."
sleep 3 && curl -sf http://localhost:8001/api/health
echo "✅ Deploy completed!"
```

**Шаги:**
1. Написать `deploy/deploy.sh`
2. Написать `deploy/setup-server.sh` для первого запуска на чистом сервере
3. Проверить синтаксис скриптов локально: `bash -n deploy/deploy.sh`

---

### Шаг 6.4 — Финальное тестирование перед деплоем

**Что делаем:** Полный прогон всего перед выгрузкой на сервер.

**Шаги:**
1. `pytest tests/ -v --tb=short` → 0 ошибок
2. `npm run lint` + `flake8 backend/` → 0 предупреждений
3. `alembic downgrade -1 && alembic upgrade head` → миграции работают в обе стороны
4. `npm run build` → сборка без ошибок и предупреждений
5. Вручную пройти полный сценарий: онбординг → бронирование → уведомление → статистика → оплата
6. Мержить `develop` → `main`

**Итог:** Проект готов к деплою. Ни одной известной проблемы.

---

# ЧАСТЬ II — Деплой и запуск

---

## Этап 7 — Настройка сервера TimeWeb

> **Цель:** Чистый сервер готов к приёму кода
> **Где работаем:** SSH или VS Code Remote SSH
> **Длительность:** 1–2 дня
> **Зависимости:** Этап 6 завершён, TimeWeb VPS арендован

---

### Шаг 7.1 — Аренда VPS

**Что делаем:** Арендовать и первично настроить сервер.

**Шаги:**
1. Зарегистрироваться на timeweb.com → Облачные серверы → Cloud-2 → Ubuntu 24.04 LTS
2. Войти: `ssh root@{IP_СЕРВЕРА}`
3. Создать пользователя: `adduser app && usermod -aG sudo app`
4. Настроить SSH-ключи для пользователя app
5. Обновить систему: `apt update && apt upgrade -y`
6. Установить стек: `nginx`, `python3.11`, `python3-pip`, `nodejs`, `npm`, `certbot`

**Итог:** Чистый сервер с базовым стеком.

---

### Шаг 7.2 — PostgreSQL на сервере

**Шаги:**
1. `apt install postgresql-14`
2. Создать пользователя и БД: `createuser bookings && createdb bookings_prod -O bookings`
3. Установить пароль, записать строку подключения
4. Добавить в `.env` продакшна: реальные значения DATABASE_URL
5. Настроить автобэкап через cron + `pg_dump`

---

### Шаг 7.3 — Деплой кода

**Шаги:**
1. `git clone https://github.com/.../app /var/www/app`
2. Создать venv: `python3 -m venv .venv && pip install -r requirements.txt`
3. Скопировать `.env` с реальными значениями (VK токены, ЮKassa, Sentry DSN)
4. Применить миграции: `alembic upgrade head`
5. Собрать фронтенд: `npm ci && npm run build`

---

### Шаг 7.4 — nginx, SSL, systemd

**Шаги:**
1. Скопировать `deploy/nginx.conf` → `/etc/nginx/sites-available/bookings`
2. Выпустить SSL: `certbot --nginx -d api.yourdomain.ru`
3. Скопировать systemd unit-файлы → `/etc/systemd/system/`
4. `systemctl enable --now app-api app-bot app-scheduler`
5. Проверить: `curl https://api.yourdomain.ru/api/health` → 200 OK

---

### Шаг 7.5 — Активация CI/CD и мониторинга

**Шаги:**
1. GitHub → Settings → Secrets → добавить `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`
2. Тестовый push в main → убедиться что деплой прошёл автоматически
3. Зарегистрироваться на uptimerobot.com → мониторинг `https://api.yourdomain.ru/api/health`
4. Настроить уведомления на email при падении сервера

**Итог:** Push в main = автодеплой за ~2 минуты + мониторинг доступности.

---

## Этап 8 — Деплой приложения

> Подключение внешних сервисов и финальная проверка на продакшне

### Шаг 8.1 — Cloudflare R2 для cold archive
1. Создать bucket в Cloudflare R2 (free: 10 GB)
2. Добавить ключи в `.env` продакшна
3. Активировать `cold_archive_job` в шедулере (убрать заглушку)

### Шаг 8.2 — ЮKassa на продакшне
1. Добавить реальные `YOOKASSA_SHOP_ID` и `YOOKASSA_SECRET_KEY`
2. Настроить webhook URL в кабинете ЮKassa: `https://api.yourdomain.ru/api/payments/webhook`
3. Провести тестовый платёж на 1 рубль

### Шаг 8.3 — Полная проверка
1. Сценарий от начала до конца: новое заведение → онбординг → бронирование → уведомление
2. Проверить тарифные ограничения на реальных данных
3. Убедиться что ошибки попадают в Sentry

---

## Этап 9 — Лендинг и публикация

> **Длительность:** 2–3 недели

### Шаг 9.1 — Лендинг

**Структура:**
```
Hero:          "Онлайн-бронирование для бизнеса в ВКонтакте"
Ниши:          Кафе · Барбершоп · Клиника · Фитнес · и другие
Как работает:  3 шага (иллюстрация)
Тарифы:        Free / Standard / Pro
Footer:        Документы · VK-группа · Поддержка
```

**Шаги:**
1. Сверстать на HTML + TailwindCSS (или Next.js)
2. Задеплоить на Cloudflare Pages (бесплатно) или на тот же VPS
3. Подключить Яндекс.Метрику
4. Добавить в footer ссылки на документы из `docs/legal/`

### Шаг 9.2 — Публикация в каталог VK Mini Apps
1. vk.com/apps → создать Mini App → заполнить карточку (иконка 256×256, скриншоты, описание)
2. Подать заявку на публикацию в каталоге
3. Ожидать модерацию (3–7 рабочих дней)
4. Создать VK-группу сервиса для анонсов и поддержки

### Шаг 9.3 — Первые клиенты
1. Написать лично в 30 заведений с предложением бесплатного подключения
2. Помочь первым 10 заведениям с настройкой персонально
3. Собрать фидбек → зафиксировать в GitHub Issues
4. Сделать 2–3 итерации улучшений

---

## Этап 10 — Рост

> Запускается после первых платных клиентов

### Шаг 10.1 — Реферальная программа
- Уникальная ссылка для каждого заведения
- +1 месяц Standard обоим при успешной регистрации по ссылке
- Дашборд рефералов в панели владельца

### Шаг 10.2 — Партнёрская программа для агентств
- Кабинет SMM-агентства: управление клиентами, статистика
- 25% комиссия с каждого приведённого заведения
- API для массового подключения клиентов агентства

### Шаг 10.3 — Масштабирование инфраструктуры
При 500+ заведениях:
- Апгрейд до TimeWeb Cloud-4 (4 vCPU / 8 GB RAM)
- Redis для кэширования конфигов заведений
- Celery + Redis вместо poll-шедулера (точные задачи)
- PostgreSQL read-replica для запросов статистики

### Шаг 10.4 — Новые функции (только по реальному спросу)
Добавлять когда 5+ заведений просят одно и то же:
- Waitlist — лист ожидания при заполненных слотах
- SMS-уведомления через SMSC.ru (альтернатива VK)
- Повторяющиеся бронирования (еженедельно)
- Telegram Bot как второй канал
- Интеграция с системами лояльности

---

## Инфраструктура и расходы

### Часть I — До сервера (разработка локально)
```
Расходы: 0 ₽/мес
Sentry free: 0 ₽
```

### Часть II — Старт (после деплоя)
| Сервис | Тариф | Цена |
|--------|-------|------|
| TimeWeb Cloud-2 | 2 vCPU / 4 GB / 60 GB | ~800 ₽/мес |
| Домен .ru | reg.ru / nic.ru | ~200 ₽/мес |
| Cloudflare DNS + CDN | Free план | 0 ₽ |
| Cloudflare R2 | Free 10 GB | 0 ₽ |
| Sentry | Free 5K событий | 0 ₽ |
| UptimeRobot | Free мониторинг | 0 ₽ |
| **Итого** | | **~1 000 ₽/мес** |

### При росте (100+ заведений)
| Сервис | Цена |
|--------|------|
| TimeWeb Cloud-4 | ~1 600 ₽/мес |
| Cloudflare R2 50 GB | ~75 ₽/мес |
| Sentry Team | ~2 400 ₽/мес |
| **Итого** | **~4 100 ₽/мес** |

### Точка безубыточности
```
Старт (1 000 ₽/мес):   нужно 3 заведения на Standard (499 ₽) = 1 497 ₽  ✅
Рост  (4 100 ₽/мес):   нужно 9 заведений на Standard         = 4 491 ₽  ✅
```

---

## Полный технический стек

### Бэкенд
| Компонент | Версия | Роль |
|-----------|--------|------|
| Python | 3.11+ | Рантайм |
| FastAPI | 0.128+ | HTTP API |
| SQLAlchemy | 2.0 | ORM (async + sync) |
| PostgreSQL | 14+ | База данных |
| Alembic | 1.16+ | Миграции |
| Pydantic | v2 | Валидация данных |
| yookassa | latest | Приём платежей |
| httpx | 0.25+ | HTTP-клиент (VK API) |
| Sentry SDK | 2.54+ | Мониторинг ошибок |

### Фронтенд
| Компонент | Версия | Роль |
|-----------|--------|------|
| React | 19 | UI |
| VKUI | 7 | Дизайн-система VK |
| VK Bridge | latest | Интеграция с платформой |
| Vite | 7 | Сборщик |
| recharts | latest | Графики в панели владельца |
| @sentry/react | latest | Мониторинг фронтенда |

### Инфраструктура (продакшн)
| Сервис | Роль |
|--------|------|
| TimeWeb Cloud | VPS (Ubuntu 24.04) |
| PostgreSQL | БД (self-hosted на VPS) |
| nginx | Reverse proxy + SSL |
| systemd | Process manager |
| GitHub Actions | CI (тесты) + CD (деплой) |
| Cloudflare | DNS + CDN + R2 storage |
| Sentry | Мониторинг ошибок |
| UptimeRobot | Мониторинг доступности |
| ЮKassa | Приём платежей |

---

## Текущий статус

```
ЧАСТЬ I — Локальная разработка
──────────────────────────────
[~] Этап 0  — Локальное окружение        ← ТЕКУЩИЙ ЭТАП
[ ] Этап 1  — Мультитенантность
[ ] Этап 2  — Универсальные категории
[ ] Этап 3  — Умное хранение данных
[ ] Этап 4  — Онбординг и панель владельца
[ ] Этап 5  — Монетизация и тарифы
[ ] Этап 6  — Подготовка к деплою

ЧАСТЬ II — Деплой (после аренды TimeWeb)
─────────────────────────────────────────
[ ] Этап 7  — Настройка сервера TimeWeb
[ ] Этап 8  — Деплой приложения
[ ] Этап 9  — Лендинг и публикация
[ ] Этап 10 — Рост
```

---

*Документ обновляется по ходу разработки.*
*Следующий шаг: Этап 0, Шаг 0.1 — проверка локального окружения в VS Code*
