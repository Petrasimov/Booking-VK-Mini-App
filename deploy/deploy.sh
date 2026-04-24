#!/bin/bash
# deploy.sh — деплой одной командой
# Запускать на сервере: bash /var/www/app/deploy/deploy.sh
#
# Что делает:
#   1. Обновляет код из GitHub (main ветка)
#   2. Устанавливает Python-зависимости
#   3. Применяет миграции БД
#   4. Собирает фронтенд
#   5. Перезапускает сервисы
#   6. Проверяет health check

set -e  # Прерываем при любой ошибке

APP_DIR="/var/www/app"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/vk-table-booking"
VENV="$BACKEND_DIR/.venv"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║  Booking VK Mini App — Deploy       ║"
echo "╚══════════════════════════════════════╝"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ── 1. Обновляем код ──────────────────────────────────────────────
echo "▶ [1/5] Pulling latest code..."
cd "$APP_DIR"
git pull origin main
echo "  ✓ Code updated"

# ── 2. Python зависимости ─────────────────────────────────────────
echo "▶ [2/5] Installing Python dependencies..."
cd "$BACKEND_DIR"
source "$VENV/bin/activate"
pip install -r requirements.txt --quiet --no-warn-script-location
echo "  ✓ Dependencies installed"

# ── 3. Миграции БД ────────────────────────────────────────────────
echo "▶ [3/5] Running database migrations..."
alembic upgrade head
echo "  ✓ Migrations applied"

# ── 4. Сборка фронтенда ───────────────────────────────────────────
echo "▶ [4/5] Building frontend..."
cd "$FRONTEND_DIR"
npm ci --silent
npm run build --silent
echo "  ✓ Frontend built"

# ── 5. Перезапуск сервисов ────────────────────────────────────────
echo "▶ [5/5] Restarting services..."
sudo systemctl restart app-api app-bot app-scheduler
echo "  ✓ Services restarted"

# ── Health check ──────────────────────────────────────────────────
echo ""
echo "  Waiting for API to start..."
sleep 4

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/health || echo "000")

if [ "$HTTP_STATUS" = "200" ]; then
    echo ""
    echo "╔══════════════════════════════════════╗"
    echo "║  ✅  Deploy completed successfully!  ║"
    echo "╚══════════════════════════════════════╝"
    curl -s http://localhost:8001/api/health | python3 -m json.tool
else
    echo ""
    echo "╔══════════════════════════════════════╗"
    echo "║  ⚠️  Deploy done but health failed!  ║"
    echo "╚══════════════════════════════════════╝"
    echo "  HTTP status: $HTTP_STATUS"
    echo "  Check logs: journalctl -u app-api -n 50"
    exit 1
fi
