import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

from app.database.db import init_db, remember_user
from app.handlers.admin import router as admin_router
from app.handlers.video import router as video_router

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

logging.basicConfig(level=logging.INFO)

dp = Dispatcher(storage=MemoryStorage())


@dp.message(Command("start"))
async def start_handler(message: Message):
    if message.from_user:
        await remember_user(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )

    await message.answer(
        "👋 Привет! Я бот обработки видео.\n\n"
        "Отправь публичную HTTPS-ссылку на видео YouTube, TikTok "
        "или Instagram и выбери профиль обработки.\n\n"
        "/start — запуск\n"
        "/help — помощь\n"
        "/admin — панель администратора"
    )


@dp.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "📚 Как пользоваться ботом:\n\n"
        "1. Отправь ссылку на публичное видео.\n"
        "2. Выбери профиль обработки.\n"
        "3. Дождись результата.\n\n"
        "Загрузка зависит от доступности видео и ограничений платформы."
    )


async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "Не задан BOT_TOKEN в переменных окружения сервера."
        )

    await init_db()

    bot = Bot(token=BOT_TOKEN)

    dp.include_router(admin_router)
    dp.include_router(video_router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Бот запускается")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
