"""
Экспорт данных бронирований в CSV.

Файл сохраняется во временную директорию.
"""

import csv
import os
import logging
import tempfile

from app.database import SessionLocal
from app.models import Reservation

logger = logging.getLogger(__name__)

# Директория для экспортированных файлов
EXPORT_DIR = os.path.join(tempfile.gettempdir(), "shokoladnitsa_export")
os.makedirs(EXPORT_DIR, exist_ok=True)


def export_reservations_csv() -> str:
    """
    Экспортирует все бронирования в CSV-файл.
    Возвращает путь к файлу.
    """
    path = os.path.join(EXPORT_DIR, "reservations.csv")
    db = SessionLocal()

    try:
        reservations = db.query(Reservation).order_by(Reservation.id).all()

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "ID", "Имя", "Гостей", "Телефон",
                "Дата", "Время", "Комментарий",
                "Пришёл", "Чек", "VK ID", "Создано",
            ])

            for r in reservations:
                writer.writerow([
                    r.id, r.name, r.guests, r.phone,
                    r.date, r.time, r.comment or "",
                    r.appeared, r.check, r.vk_user_id,
                    r.created_at,
                ])

        logger.info("Exported %d reservations to %s", len(reservations), path)
        return path

    finally:
        db.close()
