import asyncio
import json
import os
from pathlib import Path

MAX_FILE_MB = int(os.getenv(“MAX_FILE_MB”, “45”))

class VideoProcessingError(Exception):
“”“Ошибка обработки видео.”””

async def run_command(*args: str) -> str:
process = await asyncio.create_subprocess_exec(
*args,
stdout=asyncio.subprocess.PIPE,
stderr=asyncio.subprocess.PIPE,
)
stdout, stderr = await process.communicate()

if process.returncode != 0:
    message = stderr.decode("utf-8", errors="replace")
    raise VideoProcessingError(message[-1500:] or "Ошибка FFmpeg.")
return stdout.decode("utf-8", errors="replace")

async def probe_video(path: str | Path) -> dict:
file_path = Path(path)

if not file_path.is_file():
    raise VideoProcessingError("Исходный видеофайл не найден.")
output = await run_command(
    "ffprobe",
    "-v", "error",
    "-show_format",
    "-show_streams",
    "-of", "json",
    str(file_path),
)
try:
    info = json.loads(output)
except json.JSONDecodeError as exc:
    raise VideoProcessingError("Не удалось проверить видео.") from exc
streams = info.get("streams", [])
if not any(stream.get("codec_type") == "video" for stream in streams):
    raise VideoProcessingError("В файле не найден видеопоток.")
return info

async def process_video(
input_path: str | Path,
output_path: str | Path,
profile: str = “balanced”,
) -> Path:
source = Path(input_path)
target = Path(output_path)

if not source.is_file():
    raise VideoProcessingError("Исходный файл не найден.")
size_mb = source.stat().st_size / (1024 * 1024)
if size_mb > MAX_FILE_MB:
    raise VideoProcessingError(
        f"Файл превышает лимит {MAX_FILE_MB} МБ."
    )
await probe_video(source)
profiles = {
    "fast": ["-preset", "veryfast", "-crf", "28"],
    "balanced": ["-preset", "medium", "-crf", "23"],
    "quality": ["-preset", "slow", "-crf", "18"],
}
if profile not in profiles:
    raise VideoProcessingError("Неизвестный профиль экспорта.")
target.parent.mkdir(parents=True, exist_ok=True)
await run_command(
    "ffmpeg",
    "-hide_banner",
    "-loglevel", "error",
    "-y",
    "-i", str(source),
    "-map", "0:v:0",
    "-map", "0:a?",
    "-c:v", "libx264",
    *profiles[profile],
    "-pix_fmt", "yuv420p",
    "-c:a", "aac",
    "-b:a", "128k",
    "-movflags", "+faststart",
    "-map_metadata", "-1",
    str(target),
)
if not target.is_file() or target.stat().st_size == 0:
    raise VideoProcessingError("FFmpeg не создал готовый файл.")
await probe_video(target)
return target
