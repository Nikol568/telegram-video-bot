import asyncio
import json
import os
from pathlib import Path


MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "45"))
MAX_DURATION_SEC = int(os.getenv("MAX_DURATION_SEC", "600"))

FFMPEG_THREADS = int(os.getenv("FFMPEG_THREADS", "2"))


class VideoProcessingError(Exception):
    pass


PROFILES = {
    "fast": {
        "crf": "28",
        "preset": "ultrafast",
    },
    "balanced": {
        "crf": "23",
        "preset": "veryfast",
    },
    "quality": {
        "crf": "20",
        "preset": "fast",
    },
}


async def run_command(command, timeout=300):
    process = None

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )

    except asyncio.TimeoutError as exc:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()

        raise VideoProcessingError(
            "Обработка заняла больше 300 секунд. "
            "Попробуй режим «Быстрый» или более короткое видео."
        ) from exc

    except FileNotFoundError as exc:
        raise VideoProcessingError(
            "FFmpeg или FFprobe не найден на сервере. "
            "Проверь Dockerfile."
        ) from exc

    if process.returncode != 0:
        error_text = stderr.decode("utf-8", errors="replace")
        lines = [
            line.strip()
            for line in error_text.splitlines()
            if line.strip()
        ]
        details = "\n".join(lines[-20:])

        if not details:
            details = (
                f"FFmpeg завершился с кодом {process.returncode}, "
                "но не сообщил подробную ошибку."
            )

        raise VideoProcessingError(
            f"Ошибка FFmpeg (код {process.returncode}):\n"
            f"{details[-3500:]}"
        )


async def get_duration(input_path):
    command = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(input_path),
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=30,
        )

    except asyncio.TimeoutError as exc:
        if process.returncode is None:
            process.kill()
            await process.wait()

        raise VideoProcessingError(
            "Не удалось определить длительность видео за 30 секунд."
        ) from exc

    except FileNotFoundError as exc:
        raise VideoProcessingError(
            "FFprobe не найден. Проверь установку FFmpeg в Dockerfile."
        ) from exc

    if process.returncode != 0:
        details = stderr.decode("utf-8", errors="replace")[-1000:]
        raise VideoProcessingError(
            "Не удалось прочитать исходное видео через FFprobe.\n"
            + details
        )

    try:
        info = json.loads(stdout.decode("utf-8"))
        return float(info["format"]["duration"])
    except (ValueError, KeyError, TypeError) as exc:
        raise VideoProcessingError(
            "У видео не удалось определить длительность. "
            "Файл может быть повреждён или не полностью скачан."
        ) from exc


async def process_video(
    input_path: Path,
    output_path: Path,
    profile: str = "balanced",
) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.is_file():
        raise VideoProcessingError(
            "Исходный видеофайл не найден."
        )

    if profile not in PROFILES:
        raise VideoProcessingError(
            "Неизвестный профиль обработки."
        )

    if FFMPEG_THREADS < 1:
        raise VideoProcessingError(
            "FFMPEG_THREADS должен быть не меньше 1."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    duration = await get_duration(input_path)

    if duration <= 0:
        raise VideoProcessingError(
            "Длительность видео некорректна."
        )

    if duration > MAX_DURATION_SEC:
        raise VideoProcessingError(
            f"Видео длиннее лимита {MAX_DURATION_SEC} секунд."
        )

    settings = PROFILES[profile]

    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-loglevel", "warning",
        "-y",
        "-threads", str(FFMPEG_THREADS),
        "-i", str(input_path),
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-threads", str(FFMPEG_THREADS),
        "-preset", settings["preset"],
        "-crf", settings["crf"],
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-map_metadata", "-1",
        str(output_path),
    ]

    try:
        await run_command(command, timeout=300)

        if not output_path.is_file():
            raise VideoProcessingError(
                "FFmpeg не создал выходной файл."
            )

        if output_path.stat().st_size == 0:
            raise VideoProcessingError(
                "Выходной видеофайл пустой."
            )

        max_size_bytes = MAX_FILE_MB * 1024 * 1024

        if output_path.stat().st_size > max_size_bytes:
            raise VideoProcessingError(
                f"Готовое видео превышает лимит {MAX_FILE_MB} МБ. "
                "Попробуй режим «Быстрый»."
            )

        return output_path

    except Exception:
        output_path.unlink(missing_ok=True)
        raise
