"""Сканування каналів з channels.txt і додавання нових відео в чергу."""

import threading
from pathlib import Path

from config import (
    CHANNELS_FILE,
    LAST_VIDEOS_LIMIT,
    QUEUE_FILE,
    SCAN_MAX_NEW_VIDEOS_PER_RUN,
    SEEN_VIDEOS_FILE,
    YT_DLP_BIN,
)
from services.parser_service import ParserService
from services.queue_service import QueueService
from services.storage import load_queue, load_seen_videos, save_queue, save_seen_videos
from services.ytdlp_client import YtDlpClient
from utils.logger import log_blank, log_block, log_scan

_scan_lock = threading.Lock()


def _dedupe_channel_urls(urls: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        s = u.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def load_channels(file_path: Path) -> list[str]:
    if not file_path.exists():
        raise FileNotFoundError(
            f"Channels file not found: {file_path}. Create channels.txt first."
        )

    with file_path.open("r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    return _dedupe_channel_urls(lines)


def read_channels_list(file_path: Path) -> list[str]:
    """Як load_channels, але без винятку якщо файлу ще немає (порожній список)."""
    if not file_path.exists():
        return []
    with file_path.open("r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    return _dedupe_channel_urls(lines)


def save_channels_list(file_path: Path, urls: list[str]) -> None:
    """Записує channels.txt: одне посилання на рядок, без дублікатів, порядок зберігається."""
    normalized = _dedupe_channel_urls([u if isinstance(u, str) else "" for u in urls])
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("\n".join(normalized) + ("\n" if normalized else ""), encoding="utf-8")


def run_channel_scan() -> int:
    """
    Один цикл сканування. Повертає кількість нових відео, доданих у чергу за цей запуск.
    Якщо скан уже виконується — RuntimeError.
    """
    if not _scan_lock.acquire(blocking=False):
        raise RuntimeError("Сканування вже виконується. Дочекайтесь завершення.")

    try:
        log_block("SCAN START")

        channels = load_channels(CHANNELS_FILE)
        seen = load_seen_videos(SEEN_VIDEOS_FILE)
        queue = load_queue(QUEUE_FILE)

        ytdlp = YtDlpClient(yt_dlp_bin=YT_DLP_BIN)
        parser = ParserService(ytdlp_client=ytdlp)
        queue_service = QueueService()

        queue = queue_service.dedupe_queue(queue)

        log_scan(f"Channels loaded: {len(channels)}")
        log_scan(f"Seen videos: {len(seen)}")
        log_scan(f"Queue before scan: {len(queue)}")

        new_videos, updated_seen, updated_queue = parser.scan_channels(
            channel_urls=channels,
            seen_video_ids=seen,
            current_queue=queue,
            limit_per_channel=LAST_VIDEOS_LIMIT,
            max_new_total=SCAN_MAX_NEW_VIDEOS_PER_RUN,
        )

        updated_queue = queue_service.dedupe_queue(updated_queue)

        save_seen_videos(SEEN_VIDEOS_FILE, updated_seen)
        save_queue(QUEUE_FILE, updated_queue)

        log_scan(f"New videos added this scan: {len(new_videos)}")

        if new_videos:
            for idx, video in enumerate(new_videos, start=1):
                print(
                    f"  {idx}. [{video.channel_title or 'Unknown channel'}] "
                    f"{video.title} ({video.video_id})"
                )

        log_scan(f"Queue after scan: {len(updated_queue)}")
        log_blank()

        return len(new_videos)
    finally:
        _scan_lock.release()
