import asyncio
import logging
from pathlib import Path
logger = logging.getLogger(__name__)
async def set_video_metadata(
    video_path: Path,
    title: str = "Processed video",
    comment: str = "Processed using FFmpeg",
) -> Path:
    """Изменяет метаданные видео через FFmpeg."""
    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(
            f"Видео не найдено: {video_path}"
        )
    output_path = video_path.with_name(
        f"{video_path.stem}_metadata.mp4"
    )
    command = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-map", "0",
        "-c", "copy",
        "-metadata", f"title={title}",
        "-metadata", f"comment={comment}",
        "-movflags", "+faststart",
        str(output_path),
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=120,
        )
        if process.returncode != 0:
            error = stderr.decode(
                "utf-8", errors="replace"
            )[-2000:]
            raise RuntimeError(
                f"FFmpeg не смог изменить метаданные: {error}"
            )
        if not output_path.is_file():
            raise RuntimeError(
                "FFmpeg не создал выходной файл."
            )
        return output_path
    except Exception:
        if output_path.exists():
            output_path.unlink(missing_ok=True)
        logger.exception("Ошибка изменения метаданных")
        raise
