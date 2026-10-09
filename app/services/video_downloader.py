import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp


MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "45"))
MAX_DURATION_SEC = int(os.getenv("MAX_DURATION_SEC", "600"))


class VideoDownloadError(Exception):
    pass


def _check_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    allowed = (
        host == "youtube.com"
        or host.endswith(".youtube.com")
        or host == "youtu.be"
        or host == "tiktok.com"
        or host.endswith(".tiktok.com")
        or host == "instagram.com"
        or host.endswith(".instagram.com")
    )

    if parsed.scheme != "https" or not allowed:
        raise VideoDownloadError(
            "Поддерживаются HTTPS-ссылки на YouTube, TikTok и Instagram."
        )


def _download(url: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / "video.%(ext)s")

    options = {
        "outtmpl": output_template,
        "format": (
            f"best[filesize<={MAX_FILE_MB * 1024 * 1024}]/best"
        ),
        "noplaylist": True,
        "max_filesize": MAX_FILE_MB * 1024 * 1024,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=False)

            duration = info.get("duration")
            if duration and duration > MAX_DURATION_SEC:
                raise VideoDownloadError(
                    f"Видео длиннее лимита {MAX_DURATION_SEC} секунд."
                )

            downloader.download([url])

        files = [
            path
            for path in output_dir.glob("video.*")
            if path.is_file() and path.stat().st_size > 0
        ]

        if not files:
            raise VideoDownloadError(
                "Скачивание завершилось, но видеофайл не найден."
            )

        result = max(files, key=lambda path: path.stat().st_size)

        if result.stat().st_size > MAX_FILE_MB * 1024 * 1024:
            result.unlink(missing_ok=True)
            raise VideoDownloadError(
                f"Видео превышает лимит {MAX_FILE_MB} МБ."
            )

        return result

    except VideoDownloadError:
        raise
    except Exception as exc:
        raise VideoDownloadError(
            f"Ошибка скачивания: {str(exc)[:300]}"
        ) from exc


async def download_video(url: str, output_path: Path) -> Path:
    _check_url(url)
    output_dir = Path(output_path).parent

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_download, url, output_dir),
            timeout=240,
        )
    except asyncio.TimeoutError as exc:
        raise VideoDownloadError(
            "Скачивание заняло слишком много времени."
        ) from exc
