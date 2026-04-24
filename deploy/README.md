# Деплой — Booking VK Mini App

## Содержание

- [Структура папки](#структура-папки)
- [Часть II — Деплой на TimeWeb](#часть-ii--деплой-на-timeweb)
  - [Шаг 1: Аренда сервера](#шаг-1-аренда-сервера)
  - [Шаг 2: Первичная настройка](#шаг-2-первичная-настройка)
  - [Шаг 3: Настройка .env](#шаг-3-настройка-env)
  - [Шаг 4: SSL и DNS](#шаг-4-ssl-и-dns)
  - [Шаг 5: CI/CD через GitHub Actions](#шаг-5-cicd-через-github-actions)
  - [Шаг 6: Мониторинг](#шаг-6-мониторинг)
- [Управление сервисами](#управление-сервисами)
- [Обновление кода](#обновление-кода)

---

## Структура папки

```
deploy/
├── nginx.conf              ← конфигурация nginx (reverse proxy + SSL)
├── deploy.sh               ← скрипт деплоя (запускать на сервере)
├── setup-server.sh         ← первичная настройка чистого сервера
├── README.md               ← этот файл
└── systemd/
    ├── app-api.service     ← FastAPI uvicorn (порт 8001)
    ├── app-bot.service     ← VK Long Poll бот
    └── app-scheduler.service ← планировщик задач
```

---

## Часть II — Деплой на TimeWeb

### Шаг 1: Аренда сервера

1. Зарегистрироваться на [timeweb.com](https://timeweb.com)
2. Арендовать **Облачный сервер Cloud-2**:
   - 2 vCPU / 4 GB RAM / 60 GB SSD / Ubuntu 24.04 LTS
   - ~800 ₽/мес
3. Запомнить IP-адрес сервера

---

### Шаг 2: Первичная настройка

Войти на сервер и запустить скрипт:
```bash
ssh root@{IP_СЕРВЕРА}
curl -o setup-server.sh https://raw.githubusercontent.com/Petrasimov/Booking-VK-Mini-App/main/deploy/setup-server.sh
bash setup-server.sh
```

Скрипт автоматически:
- Установит nginx, Python 3.11, Node.js 20, PostgreSQL
- Создаст пользователя `app`
- Клонирует репозиторий в `/var/www/app`
- Создаст venv и установит зависимости
- Применит миграции БД
- Скопирует systemd unit-файлы
- Настроит nginx

---

### Шаг 3: Настройка .env

После запуска `setup-server.sh` отредактируй `.env`:
```bash
nano /var/www/app/backend/.env
```

Заполнить обязательно:
```env
VK_COMMUNITY_TOKEN=vk1.a.реальный_токен
VK_GROUP_ID=реальный_group_id
VK_ADMIN_ID=твой_vk_id

# После регистрации в ЮKassa:
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=

# После настройки Cloudflare R2:
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=

# После регистрации в Sentry:
SENTRY_DSN=
```

Перезапустить сервисы:
```bash
sudo systemctl restart app-api app-bot app-scheduler
```

---

### Шаг 4: SSL и DNS

1. Настроить DNS: добавить A-запись `api.yourdomain.ru → IP_СЕРВЕРА`
2. Подождать распространения DNS (5–30 минут)
3. Получить SSL сертификат:
```bash
sudo certbot --nginx -d api.yourdomain.ru
```
4. Проверить что HTTPS работает:
```bash
curl https://api.yourdomain.ru/api/health
```

---

### Шаг 5: CI/CD через GitHub Actions

В репозитории уже есть `.github/workflows/deploy.yml`. Нужно добавить секреты:

1. GitHub → репозиторий → Settings → Secrets and variables → Actions
2. Добавить три секрета:
   - `SERVER_HOST` — IP сервера
   - `SERVER_USER` — `app`
   - `SERVER_SSH_KEY` — приватный SSH ключ пользователя app

После этого **каждый push в `main` автоматически деплоится на сервер**.

Создать SSH ключ для пользователя app:
```bash
# На сервере от имени app:
ssh-keygen -t ed25519 -C "deploy@bookings"
cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/id_ed25519  # скопировать в SERVER_SSH_KEY
```

---

### Шаг 6: Мониторинг

**UptimeRobot** (бесплатно):
1. Зарегистрироваться на [uptimerobot.com](https://uptimerobot.com)
2. Add Monitor → HTTP(s)
3. URL: `https://api.yourdomain.ru/api/health`
4. Интервал: 5 минут
5. Email уведомления при падении

**Sentry** (бесплатно 5k событий/мес):
1. Зарегистрироваться на [sentry.io](https://sentry.io)
2. Создать проект `bookings-backend` (Python/FastAPI)
3. Создать проект `bookings-frontend` (React)
4. Добавить DSN в `.env`

---

## Управление сервисами

```bash
# Статус
sudo systemctl status app-api
sudo systemctl status app-bot
sudo systemctl status app-scheduler

# Перезапуск
sudo systemctl restart app-api app-bot app-scheduler

# Логи (последние 50 строк)
journalctl -u app-api -n 50
journalctl -u app-bot -n 50
journalctl -u app-scheduler -n 50

# Логи в реальном времени
journalctl -u app-api -f
```

---

## Обновление кода

**Автоматически** (при push в main через GitHub Actions):
```
git push origin main  →  GitHub Actions  →  deploy.sh на сервере
```

**Вручную** (если нужно):
```bash
ssh app@{IP_СЕРВЕРА}
bash /var/www/app/deploy/deploy.sh
```

---

## Структура сервисов на сервере

```
:443  nginx  ──→  :8001  uvicorn (FastAPI)  ──→  PostgreSQL
                                            ──→  VK API
       ↑
   Let's Encrypt SSL

Отдельные процессы:
  app-bot.service       — VK Long Poll, получает входящие сообщения
  app-scheduler.service — каждые 60с проверяет задачи в БД
```

---

## Точка безубыточности

| Расход | Сумма |
|--------|-------|
| TimeWeb Cloud-2 | ~800 ₽/мес |
| Домен .ru | ~200 ₽/год (~17 ₽/мес) |
| **Итого** | **~820 ₽/мес** |

Нужно: **2 заведения на Standard (499 ₽)** = 998 ₽ → окупаемость ✅
