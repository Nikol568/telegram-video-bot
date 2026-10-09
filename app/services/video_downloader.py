import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

MAX_FILE_MB = int(os.getenv(“MAX_FILE_MB”, “45”))

ALLOWED_HOSTS = {
“youtube.com”,
“www.youtube.com”,
“m.youtube.com”,
“youtu.be”,
“tiktok.com”,
“www.tiktok.com”,
“vm.tiktok.com”,
“instagram.com”,
“www.instagram.com”,
}

class VideoDownloadError(Exception):
“”“Понятная ошибка получения видео.”””

def validate_video_url(url: str) -> str:
url = url.strip()
parsed = urlparse(url)

if parsed.scheme != "https" or not parsed.hostname:
    raise VideoDownloadError("Пришли корректную HTTPS-ссылку на видео.")
host = parsed.hostname.lower()
allowed = any(
    host == domain or host.endswith("." + domain)
    for domain in ALLOWED_HOSTS
)
if not allowed:
    raise VideoDownloadError(
        "Поддерживаются ссылки только с YouTube, TikTok и Instagram."
    )
if parsed.username or parsed.password:
    raise VideoDownloadError("Ссылки с данными авторизации не поддерживаются.")
return url

def _download_sync(url: str, output_dir: Path) -> Path:
output_dir.mkdir(parents=True, exist_ok=True)

options = {
    "format": "best[ext=mp4]/best",
    "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "max_filesize": MAX_FILE_MB * 1024 * 1024,
    "socket_timeout": 20,
    "retries": 1,
    "fragment_retries": 1,
    "restrictfilenames": True,
}
try:
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=True)
    if not info:
        raise VideoDownloadError("Источник не предоставил информацию о видео.")
    candidates = [
        path for path in output_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {
            ".mp4", ".mkv", ".webm", ".mov"
        }
    ]
    if not candidates:
        raise VideoDownloadError(
            "Не удалось получить видео. Возможно, источник ограничил доступ."
        )
    result = max(candidates, key=lambda path: path.stat().st_mtime)
    if result.stat().st_size > MAX_FILE_MB * 1024 * 1024:
        result.unlink(missing_ok=True)
        raise VideoDownloadError(
            f"Видео превышает допустимый размер {MAX_FILE_MB} МБ."
        )
    return result
except VideoDownloadError:
    raise
except Exception as exc:
    message = str(exc).lower()
    if "private" in message or "login" in message or "sign in" in message:
        reason = "Видео закрыто или требует входа в аккаунт."
    elif "unsupported url" in message:
        reason = "Эта ссылка не поддерживается."
    elif "too large" in message or "max-filesize" in message:
        reason = f"Видео превышает лимит {MAX_FILE_MB} МБ."
    else:
        reason = (
            "Источник не разрешил загрузку либо видео недоступно. "
            "Попробуй другую публичную ссылку."
        )
    raise VideoDownloadError(reason) from exc

async def download_video(url: str, output_dir: str | Path) -> Path:
valid_url = validate_video_url(url)
folder = Path(output_dir)

try:
    return await asyncio.wait_for(
        asyncio.to_thread(_download_sync, valid_url, folder),
        timeout=180,
    )
except asyncio.TimeoutError as exc:
    raise VideoDownloadError(
        "Получение видео заняло слишком много времени. Попробуй позже."
    ) from exc
