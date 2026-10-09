import asyncio
from pathlib import Path

class MetadataError(Exception):
“”“Ошибка изменения метаданных видео.”””

async def set_video_metadata(
video_path: str | Path,
title: str | None = None,
comment: str | None = None,
) -> Path:
“””
Записывает поддерживаемые поля title и comment в контейнер MP4.
Для совместимости использует FFmpeg.
“””
source = Path(video_path)

if not source.is_file():
    raise MetadataError("Видео для изменения метаданных не найдено.")
output = source.with_name(f"{source.stem}_metadata.mp4")
command = [
    "ffmpeg",
    "-hide_banner",
    "-loglevel", "error",
    "-y",
    "-i", str(source),
    "-map", "0",
    "-c", "copy",
    "-map_metadata", "0",
]
if title:
    command.extend(["-metadata", f"title={title[:200]}"])
if comment:
    command.extend(["-metadata", f"comment={comment[:500]}"])
command.extend(["-movflags", "+faststart", str(output)])
process = await asyncio.create_subprocess_exec(
    *command,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
_, stderr = await process.communicate()
if process.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
    output.unlink(missing_ok=True)
    error = stderr.decode("utf-8", errors="replace")[-1000:]
    raise MetadataError(error or "Не удалось записать метаданные.")
return output
