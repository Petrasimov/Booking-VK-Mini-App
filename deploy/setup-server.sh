#!/bin/bash
# setup-server.sh — первичная настройка чистого Ubuntu 24.04 на TimeWeb
# Запускать один раз от root: bash setup-server.sh
#
# Что делает:
#   1. Обновляет систему
#   2. Устанавливает nginx, Python 3.11, Node.js 20, PostgreSQL
#   3. Создаёт пользователя app
#   4. Клонирует репозиторий
#   5. Настраивает PostgreSQL
#   6. Создаёт venv и устанавливает зависимости
#   7. Копирует systemd unit-файлы
#   8. Настраивает nginx
#   9. Выпускает SSL через certbot

set -e

# ── Переменные — измени перед запуском ──────────────────────────
DOMAIN="yourdomain.ru"
API_DOMAIN="api.yourdomain.ru"
REPO_URL="https://github.com/Petrasimov/Booking-VK-Mini-App.git"
APP_USER="app"
DB_NAME="booking_prod"
DB_USER="booking"
DB_PASSWORD="$(openssl rand -base64 32)"  # генерируем случайный пароль
# ──────────────────────────────────────────────────────────────────

echo "════════════════════════════════════════"
echo "  Booking VK Mini App — Server Setup"
echo "════════════════════════════════════════"

# ── 1. Обновление системы ─────────────────────────────────────────
echo "▶ [1] Updating system..."
apt update && apt upgrade -y
apt install -y curl wget git unzip build-essential software-properties-common

# ── 2. Nginx ──────────────────────────────────────────────────────
echo "▶ [2] Installing nginx..."
apt install -y nginx
systemctl enable nginx

# ── 3. Python 3.11 ────────────────────────────────────────────────
echo "▶ [3] Installing Python 3.11..."
apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# ── 4. Node.js 20 ─────────────────────────────────────────────────
echo "▶ [4] Installing Node.js 20..."
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# ── 5. PostgreSQL 16 ──────────────────────────────────────────────
echo "▶ [5] Installing PostgreSQL..."
apt install -y postgresql postgresql-contrib
systemctl enable postgresql
systemctl start postgresql

# Создаём пользователя и БД
sudo -u postgres psql << EOF
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
CREATE DATABASE $DB_NAME OWNER $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
EOF

echo "  DB_USER:     $DB_USER"
echo "  DB_PASSWORD: $DB_PASSWORD"
echo "  ⚠️  Сохрани пароль — он понадобится для .env!"

# ── 6. Certbot ────────────────────────────────────────────────────
echo "▶ [6] Installing certbot..."
apt install -y certbot python3-certbot-nginx

# ── 7. Пользователь app ───────────────────────────────────────────
echo "▶ [7] Creating app user..."
if ! id "$APP_USER" &>/dev/null; then
    adduser --disabled-password --gecos "" $APP_USER
    usermod -aG sudo $APP_USER
fi

# ── 8. Клонирование репозитория ───────────────────────────────────
echo "▶ [8] Cloning repository..."
mkdir -p /var/www
cd /var/www
if [ ! -d "app" ]; then
    git clone $REPO_URL app
    chown -R $APP_USER:$APP_USER app
fi

# ── 9. Python venv ────────────────────────────────────────────────
echo "▶ [9] Setting up Python venv..."
cd /var/www/app/backend
sudo -u $APP_USER python3.11 -m venv .venv
sudo -u $APP_USER .venv/bin/pip install -r requirements.txt --quiet

# ── 10. Systemd unit-файлы ────────────────────────────────────────
echo "▶ [10] Installing systemd services..."
cp /var/www/app/deploy/systemd/app-api.service       /etc/systemd/system/
cp /var/www/app/deploy/systemd/app-bot.service       /etc/systemd/system/
cp /var/www/app/deploy/systemd/app-scheduler.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable app-api app-bot app-scheduler

# ── 11. Nginx конфиг ──────────────────────────────────────────────
echo "▶ [11] Configuring nginx..."
cp /var/www/app/deploy/nginx.conf /etc/nginx/sites-available/bookings
sed -i "s/yourdomain.ru/$DOMAIN/g"     /etc/nginx/sites-available/bookings
sed -i "s/api.yourdomain.ru/$API_DOMAIN/g" /etc/nginx/sites-available/bookings
ln -sf /etc/nginx/sites-available/bookings /etc/nginx/sites-enabled/bookings
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ── 12. .env файл ─────────────────────────────────────────────────
echo "▶ [12] Creating .env template..."
cat > /var/www/app/backend/.env << ENVFILE
# База данных (продакшн)
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_HOST=localhost
DB_PORT=5432
DB_NAME=$DB_NAME

# VK (заполни реальные значения)
VK_COMMUNITY_TOKEN=vk1.a.YOUR_TOKEN_HERE
VK_GROUP_ID=YOUR_GROUP_ID
VK_ADMIN_ID=YOUR_ADMIN_VK_ID
VK_WAITERS_CHAT_ID=2000000001

# ЮKassa (заполни после регистрации)
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=

# Cloudflare R2 (заполни после настройки)
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=bookings-archive

# Sentry (заполни после регистрации)
SENTRY_DSN=

# CORS
CORS_ORIGIN=https://$API_DOMAIN

# Окружение
APP_ENV=production
ENVFILE

chown $APP_USER:$APP_USER /var/www/app/backend/.env
chmod 600 /var/www/app/backend/.env

# ── 13. Применяем миграции ────────────────────────────────────────
echo "▶ [13] Running migrations..."
cd /var/www/app/backend
sudo -u $APP_USER .venv/bin/alembic upgrade head

# ── 14. Сборка фронтенда ──────────────────────────────────────────
echo "▶ [14] Building frontend..."
cd /var/www/app/vk-table-booking
sudo -u $APP_USER npm ci --silent
sudo -u $APP_USER npm run build --silent

# ── 15. SSL сертификат ────────────────────────────────────────────
echo "▶ [15] Obtaining SSL certificate..."
echo "  Запусти вручную после настройки DNS:"
echo "  certbot --nginx -d $API_DOMAIN"

# ── Запускаем сервисы ─────────────────────────────────────────────
echo "▶ Starting services..."
systemctl start app-api app-bot app-scheduler

echo ""
echo "════════════════════════════════════════"
echo "  ✅  Server setup completed!"
echo "════════════════════════════════════════"
echo ""
echo "  Следующие шаги:"
echo "  1. Отредактируй /var/www/app/backend/.env (VK токены и др.)"
echo "  2. Настрой DNS: A-запись $API_DOMAIN → $(curl -s ifconfig.me)"
echo "  3. Получи SSL: certbot --nginx -d $API_DOMAIN"
echo "  4. Добавь GitHub Secrets: SERVER_HOST, SERVER_USER, SERVER_SSH_KEY"
echo ""
echo "  Логи: journalctl -u app-api -f"
echo "  Health: curl http://localhost:8001/api/health"
