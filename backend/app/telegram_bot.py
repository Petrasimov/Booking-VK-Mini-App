"""
===============================
TELEGRAM BOT (ЗАКОММЕНТИРОВАНО)
===============================

Этот файл содержит старый код Telegram-бота.
Вся функциональность перенесена в vk_bot.py

Код сохранён на случай, если понадобится в будущем.
"""

# import os
# from telegram import (
#     Bot,
#     InlineKeyboardButton,
#     InlineKeyboardMarkup,
#     Update
# )
# from telegram.ext import (
#     ApplicationBuilder,
#     CallbackQueryHandler,
#     MessageHandler,
#     filters,
#     ContextTypes,
#     CommandHandler
# )
#
# from app.admin.access import is_admin
# from app.admin.keyboard import admin_keyboard, stats_menu_keyboard
# from app.admin.export import export_reservations_csv
# from app.admin.stats import get_stats
# from app.admin.charts import bookings_chart, chart_guests_per_day, chart_came_vs_no_show, chart_popular_time
#
# from app.database import SessionLocal
# from app.models import Reservation
#
# BOT_TOKEN='8586731486:AAFvqsu22ESq4hxVfBJAVxFgJmtvN5gYu6M'
#
# CHAT_ID='-5040090195'
#
# bot = Bot(token=BOT_TOKEN)
#
# async def send_message(text, reply_markup=None):
#     await bot.send_message(
#         chat_id=CHAT_ID,
#         text=text,
#         reply_markup=reply_markup,
#         parse_mode="Markdown"
#     )
#
# def reservation_buttons(reservation_id: int):
#     return InlineKeyboardMarkup([
#         [
#             InlineKeyboardButton("✅ Пришёл", callback_data=f"came:{reservation_id}"),
#             InlineKeyboardButton("❌ Не пришёл", callback_data=f"no:{reservation_id}")
#         ]
#     ])
#
# async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Универсальный роутер для всех callback queries"""
#     query = update.callback_query
#     await query.answer()
#
#     # Если callback содержит ":", это кнопки резервации (came:123, no:123)
#     if ":" in query.data:
#         await handle_reservation_buttons(update, context)
#     else:
#         # Иначе это админ-кнопки
#         await admin_actions(update, context)
#
#
# async def handle_reservation_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Обработка кнопок резервации (Пришёл/Не пришёл)"""
#     query = update.callback_query
#     action, reservation_id = query.data.split(":")
#     reservation_id = int(reservation_id)
#
#     db = SessionLocal()
#     try:
#         reservation = db.get(Reservation, reservation_id)
#
#         if not reservation:
#             await query.message.reply_text("❌ Бронь не найдена")
#             return
#
#         if action == "no":
#             reservation.appeared = False
#             reservation.check = 0
#             db.commit()
#
#             await query.message.reply_text(
#                 f"❌ *Гость не пришёл*\n\n🆔 Бронь №{reservation_id}",
#                 parse_mode="Markdown"
#             )
#
#         elif action == "came":
#             context.user_data["wait_check"] = reservation_id
#             await query.message.reply_text(
#                 "✅ *Гость пришёл*\n\n💰 Введите сумму чека (₽):",
#                 parse_mode="Markdown"
#             )
#
#     finally:
#         db.close()
#
# async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if "wait_check" not in context.user_data:
#         return
#
#     reservation_id = context.user_data.pop("wait_check")
#
#     try:
#         check_amount = int(update.message.text)
#     except ValueError:
#         await update.message.reply_text(
#             "⚠️ Пожалуйста, введите *число* — сумму чека в рублях",
#             parse_mode="Markdown"
#         )
#         context.user_data["wait_check"] = reservation_id  # Возвращаем состояние ожидания
#         return
#
#     db = SessionLocal()
#     try:
#         reservation = db.get(Reservation, reservation_id)
#
#         if not reservation:
#             await update.message.reply_text("❌ Бронь не найдена")
#             return
#
#         reservation.appeared = True
#         reservation.check = check_amount
#         db.commit()
#
#         await context.bot.send_message(
#             chat_id=update.effective_chat.id,
#             text=(
#                 f"💾 *Чек сохранён*\n\n"
#                 f"💰 Сумма: {check_amount} ₽\n"
#                 f"🆔 Бронь №{reservation_id}"
#             ),
#             parse_mode="Markdown"
#         )
#
#
#     finally:
#         db.close()
#
# def start_bot():
#     app = ApplicationBuilder().token(BOT_TOKEN).build()
#
#     # Регистрируем хэндлеры
#     app.add_handler(CommandHandler("start", start))
#     app.add_handler(CallbackQueryHandler(callback_router))  # Единый роутер для всех callback
#     app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_handler))
#
#     print("🤖 Telegram bot started")
#     app.run_polling()
#
# async def start(update, context):
#     user_id = update.effective_user.id
#
#     if not is_admin(user_id):
#         await update.message.reply_text("⛔ Доступ запрещён")
#         return
#
#     # Определяем, откуда пришёл запрос: команда /start или callback
#     message = update.message if update.message else update.callback_query.message
#
#     await message.reply_text(
#         "👋 Админ-панель",
#         reply_markup=admin_keyboard()
#     )
#
# async def admin_actions(update, context):
#     query = update.callback_query
#
#     try:
#         if query.data == "export":
#             path = export_reservations_csv()
#             with open(path, "rb") as f:
#                 await query.message.reply_document(
#                     document=f,
#                     filename="reservations.csv"
#                 )
#
#         elif query.data == "stats":
#             s = get_stats()
#             await query.message.reply_text(
#                 f"""📊 *Статистика бронирований*
#
#     📌 Всего броней: {s['total']}
#     👥 Всего гостей: {s['total_guests']}
#     👥 Среднее гостей: {s['avg_guests']}
#     ✅ Пришли: {s['came']}
#     ❌ Не пришли: {s['no_show']}""",
#                 reply_markup=stats_menu_keyboard(),
#                 parse_mode="Markdown"
#             )
#
#         elif query.data == "chart_bookings":
#             path = bookings_chart()
#             with open(path, "rb") as f:
#                 await query.message.reply_photo(
#                     photo=f,
#                     caption="📈 *Бронирования по дням (последние 30 дней)*",
#                     reply_markup=InlineKeyboardMarkup([
#                         [InlineKeyboardButton("⬇️ Скачать", callback_data="dowload_bookings")]
#                     ]),
#                     parse_mode="Markdown"
#                 )
#
#         elif query.data == "dowload_bookings":
#             with open("bookings_chart.png", "rb") as f:
#                 await query.message.reply_document(
#                     document=f,
#                     filename="bookings_per_day.png"
#                 )
#
#         elif query.data == "chart_guests":
#             path = chart_guests_per_day()
#             with open(path, "rb") as f:
#                 await query.message.reply_photo(
#                     photo=f,
#                     caption="👥 *Гости по дням*",
#                     reply_markup=InlineKeyboardMarkup([
#                         [InlineKeyboardButton("⬇️ Скачать", callback_data="dowload_guests")]
#                     ]),
#                     parse_mode="Markdown"
#                 )
#
#         elif query.data == "dowload_guests":
#             with open("guests_per_day.png", "rb") as f:
#                 await query.message.reply_document(
#                     document=f,
#                     filename="guests_per_day.png"
#                 )
#
#         elif query.data == "chart_attendance":
#             path = chart_came_vs_no_show()
#             with open(path, "rb") as f:
#                 await query.message.reply_photo(
#                     photo=f,
#                     caption="🟢 *Пришли / 🔴 Не пришли*",
#                     reply_markup=InlineKeyboardMarkup([
#                         [InlineKeyboardButton("⬇️ Скачать", callback_data="dowload_attendance")]
#                     ]),
#                     parse_mode="Markdown"
#                 )
#
#         elif query.data == "dowload_attendance":
#             with open("attendance.png", "rb") as f:
#                 await query.message.reply_document(
#                     document=f,
#                     filename="attendance.png"
#                 )
#
#         elif query.data == "chart_time":
#             path = chart_popular_time()
#             with open(path, "rb") as f:
#                 await query.message.reply_photo(
#                     photo=f,
#                     caption="⏰ *Популярное время*",
#                     reply_markup=InlineKeyboardMarkup([
#                         [InlineKeyboardButton("⬇️ Скачать", callback_data="dowload_popular_times")]
#                     ]),
#                     parse_mode="Markdown"
#                 )
#
#         elif query.data == "dowload_popular_times":
#             with open("popular_times.png", "rb") as f:
#                 await query.message.reply_document(
#                     document=f,
#                     filename="popular_times.png"
#                 )
#
#         elif query.data == "admin_back":
#             await start(update, context)
#     except Exception as e:
#         logger.error(f"Error in admin_actions: {e}", exc_info=True)
#         await query.message.reply_text(
#             "❌ Произошла ошибка. Попробуйте позже.",
#             parse_mode="Markdown"
#         )
#
# if __name__ == "__main__":
#     start_bot()
