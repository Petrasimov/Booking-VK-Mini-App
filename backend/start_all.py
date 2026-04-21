"""
Точка входа — запуск всех сервисов одновременно:
  1. FastAPI (HTTP-сервер на порту 8001)
  2. VK Bot (Long Poll для входящих сообщений)
  3. Scheduler (планировщик отложенных задач)
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import subprocess
import sys

# Настройка логирования для всех модулей
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def run_vk_bot():
    """Запуск VK бота (Long Poll)."""
    from app.vk_bot_server import run_long_poll
    await run_long_poll()


async def run_scheduler():
    """Запуск планировщика отложенных задач."""
    from app.scheduler import run_scheduler as scheduler_loop
    await scheduler_loop()


def run_fastapi():
    """Запуск FastAPI сервера в отдельном потоке."""
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", "0.0.0.0",
        "--port", "8001",
    ])


async def main():
    """Запуск всех сервисов."""
    logger.info("=== Shokoladnitsa Server ===")
    logger.info("FastAPI:     http://localhost:8001")
    logger.info("VK Bot:      Long Poll")
    logger.info("Scheduler:   polling every 60s")

    # FastAPI — в отдельном потоке (subprocess)
    import threading
    fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
    fastapi_thread.start()

    # VK бот и планировщик — в asyncio
    bot_task = asyncio.create_task(run_vk_bot())
    scheduler_task = asyncio.create_task(run_scheduler())

    try:
        await asyncio.gather(bot_task, scheduler_task)
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped")
