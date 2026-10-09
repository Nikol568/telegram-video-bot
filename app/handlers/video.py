import asyncio
import logging
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.types import (
CallbackQuery,
InlineKeyboardButton,
InlineKeyboardMarkup,
Message,
)

from app.database.db import (
create_job,
finish_job,
remember_user,
)
from app.services.metadata import set_video_metadata
from app.services.video_downloader import (
VideoDownloadError,
download_video,
)
from app.services.video_processor import (
VideoProcessingError,
process_video,
)

router = Router()
logger = logging.getLogger(name)

URL_PATTERN = re.compile(r”https://[^\s<>]+”)

PROFILES = {
“fast”: “Быстрый”,
“balanced”: “Стандартный”,
“quality”: “Высокое качество”,
}

def profile_keyboard() -> InlineKeyboardMarkup:
return InlineKeyboardMarkup(
inline_keyboard=[
[
InlineKeyboardButton(
text=“⚡ Быстрый”,
callback_data=“profile:fast”,
),
InlineKeyboardButton(
text=“⚖️ Стандартный”,
callback_data=“profile:balanced”,
),
],
[
InlineKeyboardButton(
text=“✨ Высокое качество”,
callback_data=“profile:quality”,
)
],
]
)

@router.message(F.text)
async def handle_text(message: Message):
text = (message.text or “”).strip()

if text.startswith("/"):
    return
match = URL_PATTERN.search(text)
if not match:
    await message.answer(
        "Пришли HTTPS-ссылку на публичное видео TikTok, YouTube или Instagram."
    )
    return
url = match.group(0).rstrip(".,!?)]}")
host = (urlparse(url).hostname or "").lower()
if not any(
    host == domain or host.endswith("." + domain)
    for domain in (
        "youtube.com",
        "youtu.be",
        "tiktok.com",
        "instagram.com",
    )
):
    await message.answer("Эта платформа не поддерживается.")
    return
if not message.from_user:
    return
await remember_user(
    message.from_user.id,
    message.from_user.username,
    message.from_user.first_name,
)
await message.answer(
    "Выбери профиль экспорта для видео:",
    reply_markup=profile_keyboard(),
)
# Сохраняем ссылку в контексте Telegram-сообщения через временное
# сообщение пользователя не требуется: callback использует reply_to_message.
await message.answer(
    "Ссылка принята. После выбора профиля отправь эту же ссылку ещё раз, "
    "если бот попросит её повторно."
)

@router.callback_query(F.data.startswith(“profile:”))
async def handle_profile(callback: CallbackQuery):
await callback.answer()

if not callback.message:
    return
profile = (callback.data or "").split(":", 1)[1]
if profile not in PROFILES:
    await callback.message.answer("Неизвестный профиль экспорта.")
    return
await callback.message.answer(
    f"Выбран профиль: {PROFILES[profile]}.\n\n"
    "Теперь отправь ссылку на видео отдельным сообщением ещё раз, "
    "чтобы начать обработку."
)

async def process_link(message: Message, url: str, profile: str):
user = message.from_user
if not user:
return

job_id = await create_job(user.id, url)
await message.answer("⏳ Получаю видео и проверяю файл...")
temp_dir = Path(tempfile.mkdtemp(prefix="video_bot_"))
try:
    input_path = await download_video(url, temp_dir / "input")
    await message.answer("🎬 Обрабатываю видео...")
    output_path = temp_dir / "processed.mp4"
    await process_video(input_path, output_path, profile)
    metadata_path = await set_video_metadata(
        output_path,
        title="Processed video",
        comment="Processed using FFmpeg",
    )
    await message.answer_video(
        video=metadata_path,
        caption=f"✅ Готово! Профиль: {PROFILES[profile]}",
    )
    await finish_job(job_id, "success")
except (VideoDownloadError, VideoProcessingError, Exception) as exc:
    logger.exception("Video processing failed")
    await finish_job(job_id, "failed", str(exc)[:500])
    await message.answer(
        "❌ Не удалось обработать видео.\n"
        f"Причина: {str(exc)[:500]}"
    )
finally:
    shutil.rmtree(temp_dir, ignore_errors=True)
