import logging
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.database.db import create_job, finish_job, remember_user
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
logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r"https://[^\s<>]+")

PROFILES = {
    "fast": "Быстрый",
    "balanced": "Стандартный",
    "quality": "Высокое качество",
}


def profile_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡ Быстрый",
                    callback_data="profile:fast",
                ),
                InlineKeyboardButton(
                    text="⚖️ Стандартный",
                    callback_data="profile:balanced",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✨ Высокое качество",
                    callback_data="profile:quality",
                )
            ],
        ]
    )


@router.message(F.text.regexp(URL_PATTERN))
async def receive_video_link(message: Message, state: FSMContext):
    if not message.from_user:
        return

    match = URL_PATTERN.search(message.text or "")
    if not match:
        await message.answer("Пришли корректную HTTPS-ссылку.")
        return

    url = match.group(0).rstrip(".,!?)]}")
    host = (urlparse(url).hostname or "").lower()

    allowed = (
        host == "youtube.com"
        or host.endswith(".youtube.com")
        or host == "youtu.be"
        or host == "tiktok.com"
        or host.endswith(".tiktok.com")
        or host == "instagram.com"
        or host.endswith(".instagram.com")
    )

    if urlparse(url).scheme != "https" or not allowed:
        await message.answer(
            "Поддерживаются HTTPS-ссылки на YouTube, TikTok и Instagram."
        )
        return

    await remember_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )

    await state.update_data(video_url=url)

    await message.answer(
        "Выбери профиль обработки:",
        reply_markup=profile_keyboard(),
    )


@router.callback_query(F.data.startswith("profile:"))
async def choose_profile(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    if not callback.message:
        return

    profile = (callback.data or "").split(":", 1)[1]
    if profile not in PROFILES:
        await callback.message.answer("Неизвестный профиль.")
        return

    data = await state.get_data()
    url = data.get("video_url")

    if not url:
        await callback.message.answer(
            "Ссылка не найдена. Отправь ссылку на видео ещё раз."
        )
        return

    await state.clear()
    await process_link(callback.message, url, profile)


async def process_link(message: Message, url: str, profile: str):
    user = message.from_user
    if not user:
        return

    job_id = await create_job(user.id, url)
    status_message = await message.answer("⏳ Получаю видео...")

    temp_dir = Path(tempfile.mkdtemp(prefix="video_bot_"))

    try:
        input_path = await download_video(url, temp_dir / "input")

        await status_message.edit_text("🎬 Обрабатываю видео...")

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
        await status_message.edit_text("✅ Обработка завершена.")

    except Exception as exc:
        logger.exception("Video processing failed")

        try:
            await finish_job(job_id, "failed", str(exc)[:500])
        except Exception:
            logger.exception("Could not update job status")

        reason = str(exc)[:500] or "Неизвестная ошибка."
        await status_message.edit_text(
            f"❌ Не удалось обработать видео.\nПричина: {reason}"
        )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
