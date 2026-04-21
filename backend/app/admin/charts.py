"""
Генерация графиков статистики бронирований.

Графики сохраняются во временные файлы (tempfile).
Все функции возвращают путь к PNG-файлу.
"""

import logging
import tempfile
import os
import matplotlib
matplotlib.use("Agg")  # Неинтерактивный бэкенд (без GUI)
import matplotlib.pyplot as plt

from app.admin.stats import bookings_per_day, guests_per_day_range, came_vs_no_show, popular_times

logger = logging.getLogger(__name__)

# Директория для временных графиков
CHARTS_DIR = os.path.join(tempfile.gettempdir(), "shokoladnitsa_charts")
os.makedirs(CHARTS_DIR, exist_ok=True)


def _save_chart(filename: str) -> str:
    """Сохраняет текущий график в файл и закрывает figure."""
    path = os.path.join(CHARTS_DIR, filename)
    plt.tight_layout()
    plt.savefig(path, dpi=100)
    plt.close()
    logger.info("Chart saved: %s", path)
    return path


def bookings_chart() -> str:
    """График: количество бронирований по дням (последние 30 дней)."""
    from datetime import date as _date
    data = bookings_per_day()
    # func.date() возвращает строку 'YYYY-MM-DD' или объект date в зависимости от БД
    def _fmt(d):
        if isinstance(d, str):
            return _date.fromisoformat(d).strftime("%d.%m")
        return d.strftime("%d.%m")
    dates = [_fmt(d) for d, _ in data]
    counts = [c for _, c in data]

    plt.figure(figsize=(10, 5))
    plt.plot(dates, counts, marker="o")
    plt.title("Количество бронирований по дням")
    plt.xlabel("Дата")
    plt.ylabel("Бронирования")
    plt.grid(True)

    return _save_chart("bookings_chart.png")


def chart_guests_per_day() -> str:
    """График: количество гостей по дням (последние 30 дней)."""
    data = guests_per_day_range(30)

    plt.figure(figsize=(10, 5))
    plt.plot(data["dates"], data["guests"], marker="o")
    plt.title("Количество гостей по дням (30 дней)")
    plt.xlabel("Дата")
    plt.ylabel("Гостей")
    plt.ylim(bottom=0)
    plt.grid(True)

    return _save_chart("guests_per_day.png")


def chart_came_vs_no_show() -> str:
    """График: круговая диаграмма посещаемости."""
    data = came_vs_no_show()
    labels = ["Пришли", "Не пришли"]
    values = [data["came"], data["no_show"]]

    plt.figure(figsize=(6, 6))
    plt.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
    plt.title("Посещаемость")

    return _save_chart("attendance.png")


def chart_popular_time() -> str:
    """График: столбчатая диаграмма популярного времени бронирований."""
    data = popular_times()
    time_labels = [t.strftime("%H:%M") for t in data["time"]]

    plt.figure(figsize=(10, 5))
    plt.bar(time_labels, data["count"])
    plt.title("Популярное время бронирований")
    plt.xlabel("Время")
    plt.ylabel("Количество броней")
    plt.xticks(rotation=45)
    plt.grid(axis="y")

    return _save_chart("popular_times.png")
