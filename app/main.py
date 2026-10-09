import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv(“BOT_TOKEN”, “”).strip()
ADMIN_IDS = {
int(value.strip())
for value in os.getenv(“ADMIN_IDS”, “”).split(”,”)
if value.strip().isdigit()
}

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()

@dp.message(Command(“start”))
async def start_handler(message: Message):
await message.answer(
“👋 Привет! Это бот обработки видео.\n\n”
“Отправь ссылку на доступное видео TikTok, YouTube или Instagram.\n”
“Загрузка и обработка будут доступны для контента, “
“который разрешено получать и обрабатывать.”
)

@dp.message(Command(“help”))
async def help_handler(message: Message):
await message.answer(
“📚 Помощь\n\n”
“/start — запуск\n”
“/help — помощь\n”
“/admin — панель администратора\n\n”
“Следующим этапом подключим обработку видео.”
)

@dp.message(Command(“admin”))
async def admin_handler(message: Message):
if message.from_user and message.from_user.id in ADMIN_IDS:
await message.answer(“🔐 Доступ администратора подтверждён.”)
else:
await message.answer(“⛔ Доступ запрещён.”)

async def main():
if not BOT_TOKEN:
raise RuntimeError(“Не задан BOT_TOKEN в переменных окружения.”)

Path("data").mkdir(exist_ok=True)
bot = Bot(token=BOT_TOKEN)
try:
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
finally:
    await bot.session.close()

if name == “main”:
asyncio.run(main())
