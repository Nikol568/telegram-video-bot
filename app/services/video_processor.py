import asyncio
import json
import os
from pathlib import Path


MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "45"))


class VideoProcessingError(Exception):
    pass


PROFILES = {
    "fast": {
        "crf": "28",
        "preset": "veryfast",
    },
    "balanced": {
        "crf": "23",
        "preset": "medium",
    },
    "quality": {
        "crf": "18",
        "preset": "slow",
    },
}


async def run_command(command, timeout=300):
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )

    except asyncio.TimeoutError as exc:
        raise VideoProcessingError(
            "Обработка заняла слишком много времени."
        ) from exc

    if process.returncode != 0:
        details = stderr.decode(
            "utf-8", errors="replace"
        )[-1500:]

        raise VideoProcessingError(
            "Ошибка FFmpeg: " + details
        )


async def get_duration(input_path):
    command = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(input_path),
    ]

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise VideoProcessingError(
            "Не удалось определить длительность видео."
        )

    try:
        info = json.loads(stdout.decode("utf-8"))
        return float(info["format"]["duration"])
    except (ValueError, KeyError, TypeError) as exc:
        raise VideoProcessingError(
            "Не удалось прочитать информацию о видео."
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

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    duration = await get_duration(input_path)

    max_duration = int(
        os.getenv("MAX_DURATION_SEC", "600")
    )

    if duration > max_duration:
        raise VideoProcessingError(
            f"Видео длиннее лимита {max_duration} секунд."
        )

    settings = PROFILES[profile]

    command = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx264",
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
        await run_command(command)

        if not output_path.is_file():
            raise VideoProcessingError(
                "FFmpeg не создал выходной файл."
            )

        if output_path.stat().st_size == 0:
            raise VideoProcessingError(
                "Выходной видеофайл пустой."
            )

        if output_path.stat().st_size > MAX_FILE_MB * 1024 * 1024:
            output_path.unlink(missing_ok=True)
            raise VideoProcessingError(
                f"Готовое видео превышает лимит {MAX_FILE_MB} МБ."
            )

        return output_path

    except Exception:
        output_path.unlink(missing_ok=True)
        raise
