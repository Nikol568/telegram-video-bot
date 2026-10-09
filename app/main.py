import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv
from app.database.db import init_db, remember_user
from app.handlers.video import router as video_router
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
}
logging.basicConfig(level=logging.INFO)
dp = Dispatcher()
@dp.message(Command("start"))
async def start_handler(message: Message):
    if message.from_user:
        await remember_user(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )
    await message.answer(
        "👋 Привет! Я бот для обработки видео.\n\n"
        "Пришли публичную ссылку на видео с YouTube, TikTok или Instagram.\n"
        "Выбери профиль обработки, и бот попробует подготовить файл.\n\n"
        "Команды:\n"
        "/start — запуск\n"
        "/help — помощь\n"
        "/admin — панель администратора"
    )
@dp.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "📚 Как пользоваться ботом:\n\n"
        "1. Отправь HTTPS-ссылку на публичное видео.\n"
        "2. Выбери профиль обработки.\n"
        "3. Дождись результата.\n\n"
        "Доступность загрузки зависит от платформы и самого видео."
    )
@dp.message(Command("admin"))
async def admin_handler(message: Message):
    if message.from_user and message.from_user.id in ADMIN_IDS:
        await message.answer(
            "🔐 Администратор\n\n"
            "Панель статистики и рассылки подключим следующим этапом."
        )
    else:
        await message.answer("⛔ Доступ запрещён.")
async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Добавь токен в переменные окружения сервера."
        )
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    # Сначала команды, затем обработчик ссылок и выбора профиля.
    dp.include_router(video_router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Бот запускается")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
if __name__ == "__main__":
    asyncio.run(main())
