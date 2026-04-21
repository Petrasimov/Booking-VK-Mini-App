"""
Очистка базы данных от тестовых записей.
Удаляет все данные из всех таблиц, сохраняя схему (структуру).

Запуск: python clear_db.py
"""

from dotenv import load_dotenv
load_dotenv()

import sys
from sqlalchemy import text
from app.database import SessionLocal
from app.models import Reservation, ScheduledTask, ErrorLog, RateLimitEntry


def count_all(db):
    return {
        "reservations":    db.query(Reservation).count(),
        "scheduled_tasks": db.query(ScheduledTask).count(),
        "error_logs":      db.query(ErrorLog).count(),
        "rate_limits":     db.query(RateLimitEntry).count(),
    }


def main():
    db = SessionLocal()
    try:
        counts = count_all(db)
        total = sum(counts.values())

        print("=" * 50)
        print("🗄️  ОЧИСТКА БАЗЫ ДАННЫХ — SHOKOLADNITSA")
        print("=" * 50)
        print(f"\n📊 Текущее состояние:")
        print(f"   Бронирования:     {counts['reservations']}")
        print(f"   Отложенные задачи:{counts['scheduled_tasks']}")
        print(f"   Логи ошибок:      {counts['error_logs']}")
        print(f"   Rate limit:       {counts['rate_limits']}")
        print(f"   Итого записей:    {total}")

        if total == 0:
            print("\n✅ База данных уже пустая. Ничего не удалено.")
            return

        print(f"\n⚠️  Будет удалено {total} записей. Это действие необратимо!")
        answer = input("\nВведите 'ДА' для подтверждения: ").strip()

        if answer != "ДА":
            print("\n❌ Отменено.")
            return

        # Удаляем в правильном порядке (из-за FK constraints)
        db.execute(text("DELETE FROM scheduled_task"))
        db.execute(text("DELETE FROM error_log"))
        db.execute(text("DELETE FROM rate_limit"))
        db.execute(text("DELETE FROM reservation"))

        # Сбрасываем auto-increment счётчики
        db.execute(text("ALTER SEQUENCE reservation_id_seq RESTART WITH 1"))
        db.execute(text("ALTER SEQUENCE scheduled_task_id_seq RESTART WITH 1"))
        db.execute(text("ALTER SEQUENCE error_log_id_seq RESTART WITH 1"))
        db.execute(text("ALTER SEQUENCE rate_limit_id_seq RESTART WITH 1"))

        db.commit()

        after = count_all(db)
        print(f"\n✅ База данных очищена!")
        print(f"   Бронирования:     {after['reservations']}")
        print(f"   Отложенные задачи:{after['scheduled_tasks']}")
        print(f"   Логи ошибок:      {after['error_logs']}")
        print(f"   Rate limit:       {after['rate_limits']}")
        print(f"\n🚀 Готово к работе с чистыми данными.")
        print("=" * 50)

    except Exception as e:
        db.rollback()
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
