import time
from pathlib import Path

from config import (
    CHANNELS_FILE,
    CURRENT_ITEM_FILE,
    LAST_VIDEOS_LIMIT,
    PLAYBACK_ERROR_DELAY_SECONDS,
    POLL_INTERVAL_MINUTES,
    QUEUE_FILE,
    SCAN_ERROR_DELAY_SECONDS,
    SEEN_VIDEOS_FILE,
    STATE_DIR,
    YT_DLP_BIN,
)
from services.parser_service import ParserService
from services.playback_service import PlaybackService
from services.queue_service import QueueService
from services.storage import (
    load_current_item,
    load_queue,
    load_seen_videos,
    save_current_item,
    save_queue,
    save_seen_videos,
)
from services.ytdlp_client import YtDlpClient
from utils.logger import (
    log_blank,
    log_block,
    log_error,
    log_play,
    log_scan,
    log_warn,
)


def load_channels(file_path: Path) -> list[str]:
    if not file_path.exists():
        raise FileNotFoundError(
            f"Channels file not found: {file_path}. Create channels.txt first."
        )

    with file_path.open("r", encoding="utf-8") as f:
        channels = [line.strip() for line in f if line.strip()]

    # прибираємо дублікати, зберігаючи порядок
    unique_channels: list[str] = []
    seen = set()

    for url in channels:
        if url in seen:
            continue
        seen.add(url)
        unique_channels.append(url)

    return unique_channels


def scan_for_new_videos() -> None:
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
    )

    updated_queue = queue_service.dedupe_queue(updated_queue)

    save_seen_videos(SEEN_VIDEOS_FILE, updated_seen)
    save_queue(QUEUE_FILE, updated_queue)

    log_scan(f"New videos found: {len(new_videos)}")

    if new_videos:
        for idx, video in enumerate(new_videos, start=1):
            print(
                f"  {idx}. [{video.channel_title or 'Unknown channel'}] "
                f"{video.title} ({video.video_id})"
            )

    log_scan(f"Queue after scan: {len(updated_queue)}")
    log_blank()


def playback_step() -> None:
    queue_service = QueueService()
    playback_service = PlaybackService()

    current_item = load_current_item(CURRENT_ITEM_FILE)
    queue = load_queue(QUEUE_FILE)
    queue = queue_service.dedupe_queue(queue)

    if current_item is not None:
        log_warn(
            f"Recovery playback detected: {current_item.title} ({current_item.video_id})"
        )
        try:
            playback_service.play(current_item)
        finally:
            save_current_item(CURRENT_ITEM_FILE, None)
        return

    next_item, new_queue = queue_service.pop_next_item(queue)

    if next_item is None:
        log_play("Queue is empty -> using filler")
        next_item = playback_service.create_filler_item()
    else:
        save_queue(QUEUE_FILE, new_queue)

    save_current_item(CURRENT_ITEM_FILE, next_item)

    try:
        playback_service.play(next_item)
    finally:
        save_current_item(CURRENT_ITEM_FILE, None)


def main() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    last_scan_time = 0.0
    scan_interval_seconds = POLL_INTERVAL_MINUTES * 60

    while True:
        now = time.time()

        if now - last_scan_time >= scan_interval_seconds:
            try:
                scan_for_new_videos()
            except Exception as e:
                log_blank()
                log_error(f"SCAN FAILED: {e}")
                log_blank()
                time.sleep(SCAN_ERROR_DELAY_SECONDS)
            finally:
                last_scan_time = now

        try:
            playback_step()
        except Exception as e:
            log_blank()
            log_error(f"PLAYBACK FAILED: {e}")
            log_blank()
            time.sleep(PLAYBACK_ERROR_DELAY_SECONDS)


if __name__ == "__main__":
    main()